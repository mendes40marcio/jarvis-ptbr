"""
Contexto extra da abertura do JARVIS: clima da cidade e notícias do mercado gamer.

Só usa a biblioteca padrão do Python e serviços gratuitos sem chave de API:
  - Clima: Open-Meteo (https://open-meteo.com)
  - Games: feeds RSS públicos, com busca na web como reserva

Teste isolado (dentro de ~/Documentos/Mark-LV-main, com o .venv ativo):
    python -m core.briefing_extras
"""
import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

# ── Cidade ───────────────────────────────────────────────────────────────────
CITY = "Campina Grande do Sul"
LAT, LON = -25.3058, -49.0550
TIMEZONE = "America/Sao_Paulo"

# ── Feeds do mercado gamer ───────────────────────────────────────────────────
# Tentados em ordem; um feed fora do ar é só pulado. Pode trocar ou adicionar.
GAMES_FEEDS = [
    "https://dropsdejogos.uai.com.br/feed/",   # foco em indústria e mercado
    "https://br.ign.com/feed.xml",
    "https://adrenaline.com.br/feed/",
    "https://www.gamesindustry.biz/feed",      # inglês, mercado global
]
GAMES_LIMIT    = 5   # manchetes no total
PER_FEED_LIMIT = 3   # no máximo por feed, para variar as fontes

TIMEOUT = 6  # segundos por requisição

# Códigos de tempo da OMM usados pelo Open-Meteo
_WMO = {
    0: "céu limpo", 1: "predominantemente limpo", 2: "parcialmente nublado",
    3: "nublado", 45: "neblina", 48: "neblina com geada",
    51: "garoa fraca", 53: "garoa", 55: "garoa forte",
    56: "garoa congelante", 57: "garoa congelante forte",
    61: "chuva fraca", 63: "chuva", 65: "chuva forte",
    66: "chuva congelante", 67: "chuva congelante forte",
    71: "neve fraca", 73: "neve", 75: "neve forte", 77: "grãos de neve",
    80: "pancadas de chuva fracas", 81: "pancadas de chuva",
    82: "pancadas de chuva fortes", 85: "pancadas de neve",
    86: "pancadas de neve fortes", 95: "trovoadas",
    96: "trovoadas com granizo", 99: "trovoadas com granizo forte",
}


def _get(url: str) -> bytes:
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (JARVIS Mark-LV briefing)"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def fetch_weather() -> str:
    """Uma linha com o clima de hoje na cidade. Retorna "" se falhar."""
    params = {
        "latitude": LAT, "longitude": LON, "timezone": TIMEZONE,
        "forecast_days": 1,
        "current": "temperature_2m,weather_code",
        "daily": ("temperature_2m_max,temperature_2m_min,"
                  "precipitation_probability_max,weather_code"),
    }
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    try:
        data = json.loads(_get(url))
        cur = data.get("current") or {}
        day = data.get("daily") or {}

        def hoje(campo):
            valores = day.get(campo) or [None]
            return valores[0]

        partes = [f"Clima em {CITY} hoje:"]
        t_agora = cur.get("temperature_2m")
        if t_agora is not None:
            cond = _WMO.get(cur.get("weather_code"), "")
            partes.append(f"agora {round(t_agora)}°C" + (f", {cond}" if cond else "") + ";")
        t_min, t_max = hoje("temperature_2m_min"), hoje("temperature_2m_max")
        if t_min is not None and t_max is not None:
            partes.append(f"mínima de {round(t_min)}°C e máxima de {round(t_max)}°C;")
        cond_dia = _WMO.get(hoje("weather_code"))
        if cond_dia:
            partes.append(f"previsão de {cond_dia};")
        chuva = hoje("precipitation_probability_max")
        if chuva is not None:
            partes.append(f"chance de chuva de {round(chuva)}%.")
        texto = " ".join(partes).rstrip(";")
        return texto if len(partes) > 1 else ""
    except Exception as e:
        print(f"[Briefing] Clima indisponível: {e!r}")
        return ""


def _clean(txt: str) -> str:
    txt = html.unescape(re.sub(r"<[^>]+>", "", txt or ""))
    return " ".join(txt.split())


def _parse_feed(raw: bytes) -> list[tuple[str, str]]:
    """(título, link) de um feed RSS ou Atom."""
    root = ET.fromstring(raw)
    itens = []
    for item in root.iter("item"):                       # RSS
        titulo = _clean(item.findtext("title", ""))
        link = (item.findtext("link") or "").strip()
        if titulo:
            itens.append((titulo, link))
    if not itens:                                        # Atom
        ns = "{http://www.w3.org/2005/Atom}"
        for entry in root.iter(f"{ns}entry"):
            titulo = _clean(entry.findtext(f"{ns}title", ""))
            el = entry.find(f"{ns}link")
            link = el.get("href", "") if el is not None else ""
            if titulo:
                itens.append((titulo, link))
    return itens


def fetch_games_news() -> str:
    """Manchetes do mercado gamer, numeradas. Retorna "" se nada funcionar."""
    manchetes, vistos = [], set()
    for url in GAMES_FEEDS:
        if len(manchetes) >= GAMES_LIMIT:
            break
        try:
            itens = _parse_feed(_get(url))
        except Exception as e:
            print(f"[Briefing] Feed de games falhou ({url}): {e!r}")
            continue
        for titulo, link in itens[:PER_FEED_LIMIT]:
            chave = titulo.lower()
            if chave in vistos:
                continue
            vistos.add(chave)
            manchetes.append((titulo, link))
            if len(manchetes) >= GAMES_LIMIT:
                break

    if manchetes:
        linhas = []
        for i, (titulo, link) in enumerate(manchetes, 1):
            linhas.append(f"{i}. {titulo}" + (f"\n   Source: {link}" if link else ""))
        return "\n".join(linhas)

    # Reserva: a mesma busca na web que as notícias de tecnologia usam.
    try:
        from actions.web_search import _news
        texto = _news("notícias mercado de games indústria de jogos hoje")
        if texto and not texto.startswith(("No news found", "Search failed")):
            return texto
    except Exception as e:
        print(f"[Briefing] Busca de games falhou: {e!r}")
    return ""


if __name__ == "__main__":
    print("── CLIMA ──")
    print(fetch_weather() or "(indisponível)")
    print("\n── MERCADO GAMER ──")
    print(fetch_games_news() or "(indisponível)")
