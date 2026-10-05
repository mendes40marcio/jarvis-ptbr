"""
football_schedule — upcoming matches of a football team, from structured data.

WHY THIS EXISTS
    Asked "when is Palmeiras' next match?", the assistant used web_search and
    read whatever snippet came back. The snippet was a ticket-sales page that
    listed one match three weeks away, and the model answered with it, skipping
    five earlier fixtures. Instructions in the prompt did not fix that: the model
    cannot know a snippet is incomplete.

    So the choosing is done here, in code: fetch the full fixture lists, drop
    finished matches, sort by kick-off, convert to Brasília time. The model only
    reads the answer.

SOURCES
    1. ESPN's public site API (no key). Unofficial and undocumented: it can
       change without notice, which is why every field is read defensively.
       Brasileirão and Libertadores were checked against the club's official
       calendar on 2026-10-04 and matched match for match.
    2. TheSportsDB, free test key, as a fallback. It returns only the NEXT
       match, but that is enough to answer the commonest question.
"""
from __future__ import annotations

import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

PLUGIN = {
    "name": "football_schedule",
    "description": (
        "Upcoming football (soccer) matches of a team: the next match and the "
        "list after it, with weekday, date, Brasília kick-off time, opponent, "
        "competition and stadium. Use it for ANY question about when a team "
        "plays — 'quando é o próximo jogo do Palmeiras', 'o Corinthians joga "
        "essa semana?', 'jogos do Flamengo em outubro'. Always prefer it to "
        "web_search for fixtures: its answer is already sorted and the first "
        "match listed IS the next one. Covers the Brasileirão and the "
        "Libertadores (Copa do Brasil and Sul-Americana when available). Not for "
        "past results or scores — use web_search for those."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "team": {
                "type": "STRING",
                "description": "Team name as the user said it, e.g. 'Palmeiras', "
                               "'Corinthians', 'São Paulo'. Default: Palmeiras.",
            },
            "count": {
                "type": "INTEGER",
                "description": "How many upcoming matches to list (1-10). Default 5.",
            },
        },
        "required": [],
    },
}

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
TSDB_BASE = "https://www.thesportsdb.com/api/v1/json/3"

# (ESPN league code, name to show). bra.1 and conmebol.libertadores were
# verified; the other two are best-effort and simply skipped if ESPN refuses.
LEAGUES = [
    ("bra.1",                 "Brasileirão"),
    ("conmebol.libertadores", "Libertadores"),
    ("bra.copa_do_brazil",    "Copa do Brasil"),
    ("conmebol.sudamericana", "Sul-Americana"),
]

# Known ids skip a lookup request. Anything else is found by name.
KNOWN_ESPN_IDS = {"palmeiras": "2029"}
KNOWN_TSDB_IDS = {"palmeiras": "134465"}

_TIMEOUT = 5.0
_UA = "Mozilla/5.0 (X11; Linux x86_64) JARVIS-football/1.0"
_WEEKDAYS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
_IN_PROGRESS_GRACE = timedelta(hours=2, minutes=30)   # a match still being played

try:
    from zoneinfo import ZoneInfo
    _BRT = ZoneInfo("America/Sao_Paulo")
except Exception:                                    # no tz database: Brazil has
    _BRT = timezone(timedelta(hours=-3))            # had no DST since 2019

_team_cache: dict[str, tuple[float, dict]] = {}       # league -> (time, {name: id})


# ── helpers ───────────────────────────────────────────────────────────────────

def _norm(text: str) -> str:
    """'São Paulo FC' -> 'saopaulofc'. Accent-, case- and space-insensitive."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _get_json(url: str):
    import requests
    resp = requests.get(url, timeout=_TIMEOUT, headers={"User-Agent": _UA})
    resp.raise_for_status()
    return resp.json()


def _parse_utc(raw: str) -> datetime | None:
    """ESPN '2026-10-09T00:30Z' / TheSportsDB '2026-10-09T00:30:00' -> aware UTC."""
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ── ESPN ──────────────────────────────────────────────────────────────────────

def _espn_teams(league: str) -> dict[str, str]:
    """{normalised name or alias: team id} for one league, cached for a day."""
    hit = _team_cache.get(league)
    if hit and time.time() - hit[0] < 86400:
        return hit[1]
    data = _get_json(f"{ESPN_BASE}/{league}/teams")
    names: dict[str, str] = {}
    for sport in data.get("sports", []) or []:
        for lg in sport.get("leagues", []) or []:
            for entry in lg.get("teams", []) or []:
                team = entry.get("team", {}) or {}
                tid = str(team.get("id", "")).strip()
                if not tid:
                    continue
                for key in ("displayName", "shortDisplayName", "name",
                            "nickname", "location", "abbreviation"):
                    if team.get(key):
                        names.setdefault(_norm(team[key]), tid)
                slug = (team.get("slug") or "").split(".")[-1]
                if slug:
                    names.setdefault(_norm(slug), tid)
    _team_cache[league] = (time.time(), names)
    return names


def _espn_team_id(team: str) -> str | None:
    key = _norm(team)
    if key in KNOWN_ESPN_IDS:
        return KNOWN_ESPN_IDS[key]
    for league in ("bra.1", "bra.2"):
        try:
            names = _espn_teams(league)
        except Exception:
            continue
        if key in names:
            return names[key]
        # 'sao paulo' should find 'saopaulofc'; require 4+ chars to avoid noise
        if len(key) >= 4:
            for name, tid in names.items():
                if name.startswith(key) or key.startswith(name):
                    return tid
    return None


def _espn_league_matches(team_id: str, league: str, label: str) -> list[dict]:
    try:
        data = _get_json(f"{ESPN_BASE}/{league}/teams/{team_id}/schedule?fixture=true")
    except Exception:
        return []                       # league the team is not in, or ESPN down
    out = []
    for ev in data.get("events", []) or []:
        when = _parse_utc(ev.get("date"))
        comps = ev.get("competitions") or [{}]
        comp = comps[0] if isinstance(comps, list) and comps else {}
        state = (((comp.get("status") or {}).get("type") or {}).get("state")
                 or ((ev.get("status") or {}).get("type") or {}).get("state") or "")
        home = away = ""
        for c in comp.get("competitors", []) or []:
            name = ((c.get("team") or {}).get("displayName") or "").strip()
            if c.get("homeAway") == "home":
                home = name
            elif c.get("homeAway") == "away":
                away = name
        if not (when and home and away):
            continue
        out.append({
            "when": when, "home": home, "away": away, "competition": label,
            "venue": ((comp.get("venue") or {}).get("fullName") or "").strip(),
            "state": str(state).lower(),
        })
    return out


def _from_espn(team: str) -> tuple[str, list[dict]] | None:
    team_id = _espn_team_id(team)
    if not team_id:
        return None
    with ThreadPoolExecutor(max_workers=len(LEAGUES)) as pool:
        lists = pool.map(lambda lg: _espn_league_matches(team_id, *lg), LEAGUES)
        matches = [m for lst in lists for m in lst]
    return ("ESPN", matches) if matches else None


# ── TheSportsDB (next match only) ─────────────────────────────────────────────

def _from_tsdb(team: str) -> tuple[str, list[dict]] | None:
    key = _norm(team)
    tid = KNOWN_TSDB_IDS.get(key)
    if not tid:
        found = (_get_json(f"{TSDB_BASE}/searchteams.php?t={quote(team)}") or {}).get("teams") or []
        soccer = [t for t in found if (t.get("strSport") or "").lower() == "soccer"]
        brazil = [t for t in soccer if (t.get("strCountry") or "").lower() == "brazil"]
        pick = (brazil or soccer or [None])[0]
        if not pick:
            return None
        tid = pick.get("idTeam")
    events = (_get_json(f"{TSDB_BASE}/eventsnext.php?id={tid}") or {}).get("events") or []
    out = []
    for ev in events:
        when = _parse_utc(ev.get("strTimestamp")
                          or f"{ev.get('dateEvent', '')}T{ev.get('strTime', '')}")
        if not (when and ev.get("strHomeTeam") and ev.get("strAwayTeam")):
            continue
        league = ev.get("strLeague") or ""
        out.append({
            "when": when, "home": ev["strHomeTeam"], "away": ev["strAwayTeam"],
            "competition": "Brasileirão" if league == "Brazilian Serie A" else league,
            "venue": ev.get("strVenue") or "", "state": "pre",
        })
    return ("TheSportsDB", out) if out else None


# ── selection and wording ─────────────────────────────────────────────────────

def upcoming(matches: list[dict], now: datetime | None = None) -> list[dict]:
    """Not finished, not long past, one entry per fixture, soonest first."""
    now = now or datetime.now(timezone.utc)
    keep, seen = [], set()
    for m in matches:
        if m["state"] == "post":
            continue
        if m["when"] < now - _IN_PROGRESS_GRACE:
            continue
        key = (m["when"], _norm(m["home"]), _norm(m["away"]))
        if key in seen:
            continue
        seen.add(key)
        keep.append(m)
    keep.sort(key=lambda m: m["when"])
    return keep


def _line(m: dict) -> str:
    local = m["when"].astimezone(_BRT)
    day = f"{_WEEKDAYS[local.weekday()]} {local:%d/%m}"
    clock = f"{local:%H}h{local:%M}"
    live = " (em andamento)" if m["state"] == "in" else ""
    venue = f" — {m['venue']}" if m["venue"] else ""
    return f"{day} {clock} — {m['home']} x {m['away']} — {m['competition']}{venue}{live}"


def describe(team: str, matches: list[dict], source: str, count: int,
             now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(_BRT)
    if not matches:
        return f"No upcoming matches found for {team}."
    lines = [
        f"Upcoming matches for {team} — Brasília time, sorted by date "
        f"(today is {_WEEKDAYS[today.weekday()]} {today:%d/%m/%Y}).",
        f"NEXT MATCH: {_line(matches[0])}",
    ]
    if len(matches) > 1 and count > 1:
        lines.append("After that:")
        lines += [f"- {_line(m)}" for m in matches[1:count]]
    if source == "TheSportsDB":
        lines.append("(Backup source: only the next match is available.)")
    return "\n".join(lines)


def run(parameters: dict, player=None, session_memory=None) -> str:
    params = parameters or {}
    team = str(params.get("team") or "Palmeiras").strip() or "Palmeiras"
    try:
        count = max(1, min(10, int(params.get("count") or 5)))
    except (TypeError, ValueError):
        count = 5

    result = None
    for fetch in (_from_espn, _from_tsdb):
        try:
            got = fetch(team)
        except Exception as e:
            print(f"[Football] {fetch.__name__}: {type(e).__name__}: {str(e)[:100]}")
            got = None
        if got:
            src, raw = got
            future = upcoming(raw)
            if future:
                result = (src, future)
                break

    if not result:
        return (f"Could not get the fixture list for {team} right now. Say so "
                "plainly; do not guess a date.")

    source, matches = result
    text = describe(team, matches, source, count)
    print(f"[Football] {team}: {len(matches)} upcoming matches via {source}")
    if player is not None:
        try:
            player.show_content(f"JOGOS — {team}", text)
        except Exception:
            pass
    return text
