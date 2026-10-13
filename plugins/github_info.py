"""
JARVIS ligado ao seu GitHub.

Exemplos de pedidos:
  "Jarvis, o que eu fiz no GitHub essa semana?"     -> acao=resumo
  "Jarvis, o que eu fiz no último mês?"             -> acao=resumo, dias=30
  "Jarvis, quais são meus repositórios?"            -> acao=repos
  "Jarvis, tem projeto meu parado?"                 -> acao=parados
  "Jarvis, como está o MARCIO.SYS?"                 -> acao=repo, nome=...

Sem token, enxerga só os repositórios públicos. Para incluir os privados,
coloque um token de SÓ LEITURA em ⚙ → PLUGIN SETTINGS → GitHub.
"""
from __future__ import annotations

import difflib
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("America/Sao_Paulo")
except Exception:
    _TZ = timezone(timedelta(hours=-3))

API = "https://api.github.com"
USUARIO_PADRAO = "mendes40marcio"

PLUGIN = {
    "name": "github_info",
    "description": (
        "Consulta o GitHub do usuário (repositórios e commits). Use quando ele "
        "perguntar o que fez no GitHub, quantos commits fez na semana ou no mês, "
        "quais são os repositórios dele, se tem projeto parado/abandonado, ou como "
        "está um repositório específico. acao: 'resumo' (commits dos últimos dias), "
        "'repos' (lista de repositórios), 'parados' (sem mexer há muito tempo), "
        "'repo' (detalhes de um repositório; passe o nome)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "acao": {"type": "STRING",
                     "description": "'resumo', 'repos', 'parados' ou 'repo'. Padrão: resumo."},
            "dias": {"type": "INTEGER",
                     "description": "Período em dias. Resumo: padrão 7. Parados: padrão 14."},
            "nome": {"type": "STRING",
                     "description": "Nome (ou parte do nome) do repositório, para acao='repo'."},
        },
        "required": [],
    },
}

PLUGIN_SETTINGS = {
    "namespace": "github",
    "title": "GitHub",
    "fields": [
        {"key": "usuario", "label": "Usuário do GitHub", "type": "text",
         "default": USUARIO_PADRAO},
        {"key": "token", "label": "Token só leitura (opcional, para repositórios privados)",
         "type": "password"},
    ],
}


# ── acesso à API ────────────────────────────────────────────────────────────

def _config() -> tuple[str, str]:
    try:
        from memory.config_manager import get_plugin_config
        cfg = get_plugin_config("github")
    except Exception:
        cfg = {}
    usuario = (cfg.get("usuario") or USUARIO_PADRAO).strip()
    token = (cfg.get("token") or "").strip()
    return usuario, token


def _get(caminho: str, token: str, **params):
    import requests
    headers = {"Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "JARVIS-Mark-LV"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.get(API + caminho, headers=headers, params=params, timeout=10)
    if r.status_code == 409:          # repositório vazio
        return []
    if r.status_code == 404:
        raise LookupError("não encontrado")
    if r.status_code in (401, 403):
        resto = r.headers.get("X-RateLimit-Remaining")
        if resto == "0":
            raise PermissionError("limite de consultas do GitHub atingido; tente daqui a uma hora "
                                  "ou configure um token")
        raise PermissionError("o GitHub recusou o acesso; confira o token nas configurações")
    r.raise_for_status()
    return r.json()


def _repos(usuario: str, token: str) -> list[dict]:
    if token:
        dados = _get("/user/repos", token, sort="pushed", per_page=100, affiliation="owner")
    else:
        dados = _get(f"/users/{usuario}/repos", token, sort="pushed", per_page=100)
    return [r for r in dados if not r.get("fork")]


def _commits(usuario: str, repo: str, token: str, desde: datetime) -> list[dict]:
    return _get(f"/repos/{usuario}/{repo}/commits", token,
                since=desde.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                per_page=100) or []


# ── utilidades de data e texto ──────────────────────────────────────────────

def _data(iso: str | None) -> datetime | None:
    if not iso:
        return None
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(_TZ)


def _ha(dt: datetime | None, agora: datetime) -> str:
    if not dt:
        return "nunca"
    d = (agora.date() - dt.date()).days
    if d <= 0:
        return "hoje"
    if d == 1:
        return "ontem"
    if d < 30:
        return f"há {d} dias"
    if d < 365:
        m = d // 30
        return f"há {m} {'mês' if m == 1 else 'meses'}"
    a = d // 365
    return f"há {a} {'ano' if a == 1 else 'anos'}"


def _msg(c: dict) -> str:
    return (c.get("commit", {}).get("message") or "").strip().splitlines()[0][:80]


def _num(n: int, um: str, varios: str) -> str:
    return f"{n} {um if n == 1 else varios}"


# ── ações ───────────────────────────────────────────────────────────────────

def _resumo(usuario, token, dias, agora) -> str:
    desde = agora - timedelta(days=dias)
    repos = [r for r in _repos(usuario, token)
             if (_data(r.get("pushed_at")) or desde) >= desde]
    por_repo, dias_ativos, total = [], set(), 0
    for r in repos:
        cs = _commits(usuario, r["name"], token, desde)
        if not cs:
            continue
        total += len(cs)
        for c in cs:
            dt = _data(c.get("commit", {}).get("author", {}).get("date"))
            if dt:
                dias_ativos.add(dt.date())
        por_repo.append((r["name"], len(cs), _msg(cs[0])))
    periodo = "na última semana" if dias == 7 else f"nos últimos {dias} dias"
    if not total:
        return (f"Nenhum commit {periodo} nos repositórios "
                f"{'' if token else 'públicos '}de {usuario}.")
    por_repo.sort(key=lambda x: -x[1])
    linhas = [f"{_num(total, 'commit', 'commits')} {periodo}, em "
              f"{_num(len(por_repo), 'repositório', 'repositórios')}, "
              f"com atividade em {_num(len(dias_ativos), 'dia', 'dias')} diferentes."]
    for nome, n, ultimo in por_repo[:6]:
        linhas.append(f"- {nome}: {_num(n, 'commit', 'commits')}; último: \"{ultimo}\"")
    seq, dia = 0, agora.date()
    if dia not in dias_ativos:
        dia -= timedelta(days=1)
    while dia in dias_ativos:
        seq += 1
        dia -= timedelta(days=1)
    if seq >= 2:
        linhas.append(f"Sequência atual: {seq} dias seguidos com commit.")
    return "\n".join(linhas)


def _lista(usuario, token, agora) -> str:
    repos = _repos(usuario, token)
    if not repos:
        return f"Não encontrei repositórios {'' if token else 'públicos '}de {usuario}."
    linhas = [f"{_num(len(repos), 'repositório', 'repositórios')} de {usuario}, "
              f"do mais recente para o mais antigo:"]
    for r in repos[:12]:
        extra = f" ({r['language']})" if r.get("language") else ""
        priv = " [privado]" if r.get("private") else ""
        linhas.append(f"- {r['name']}{extra}{priv}: atualizado "
                      f"{_ha(_data(r.get('pushed_at')), agora)}")
    if len(repos) > 12:
        linhas.append(f"... e mais {len(repos) - 12}.")
    return "\n".join(linhas)


def _parados(usuario, token, dias, agora) -> str:
    limite = agora - timedelta(days=dias)
    repos = [r for r in _repos(usuario, token)
             if (_data(r.get("pushed_at")) or limite) < limite]
    if not repos:
        return f"Nenhum repositório parado há mais de {dias} dias. Tudo em movimento."
    repos.sort(key=lambda r: r.get("pushed_at") or "")
    linhas = [f"{_num(len(repos), 'repositório', 'repositórios')} sem mexer há mais de {dias} dias:"]
    for r in repos[:10]:
        linhas.append(f"- {r['name']}: última vez {_ha(_data(r.get('pushed_at')), agora)}")
    return "\n".join(linhas)


def _detalhe(usuario, token, nome, agora) -> str:
    repos = _repos(usuario, token)
    if not repos:
        return f"Não encontrei repositórios de {usuario}."
    alvo = nome.lower().replace(" ", "").replace(".", "").replace("-", "").replace("_", "")
    def chave(r):
        n = r["name"].lower().replace(".", "").replace("-", "").replace("_", "")
        return 1.0 if alvo and alvo in n else difflib.SequenceMatcher(None, alvo, n).ratio()
    melhor = max(repos, key=chave)
    if chave(melhor) < 0.5:
        nomes = ", ".join(r["name"] for r in repos[:8])
        return f"Não achei um repositório parecido com \"{nome}\". Os seus são: {nomes}."
    cs = _get(f"/repos/{usuario}/{melhor['name']}/commits", token, per_page=5) or []
    linhas = [f"{melhor['name']}" + (f": {melhor['description']}" if melhor.get("description") else "")]
    info = [f"atualizado {_ha(_data(melhor.get('pushed_at')), agora)}"]
    if melhor.get("language"):
        info.append(f"linguagem principal {melhor['language']}")
    info.append(_num(melhor.get("stargazers_count", 0), "estrela", "estrelas"))
    if melhor.get("open_issues_count"):
        info.append(_num(melhor["open_issues_count"], "issue aberta", "issues abertas"))
    linhas.append(", ".join(info) + ".")
    if cs:
        linhas.append("Últimos commits:")
        for c in cs:
            dt = _data(c.get("commit", {}).get("author", {}).get("date"))
            linhas.append(f"- {_ha(dt, agora)}: \"{_msg(c)}\"")
    return "\n".join(linhas)


def run(parameters: dict, player=None, session_memory=None) -> str:
    acao = str(parameters.get("acao") or "resumo").strip().lower()
    nome = str(parameters.get("nome") or "").strip()
    try:
        dias = int(parameters.get("dias") or 0)
    except (TypeError, ValueError):
        dias = 0
    usuario, token = _config()
    agora = datetime.now(_TZ)
    try:
        if acao in ("repos", "lista", "repositorios", "repositórios"):
            texto = _lista(usuario, token, agora)
        elif acao in ("parados", "parado", "abandonados"):
            texto = _parados(usuario, token, dias or 14, agora)
        elif acao in ("repo", "repositorio", "repositório", "detalhe") or nome:
            texto = _detalhe(usuario, token, nome, agora)
        else:
            texto = _resumo(usuario, token, max(1, min(dias or 7, 90)), agora)
    except ImportError:
        texto = "O pacote requests não está instalado no JARVIS."
    except (LookupError, PermissionError) as e:
        texto = f"Não consegui consultar o GitHub: {e}."
    except Exception as e:
        texto = f"Não consegui consultar o GitHub agora ({type(e).__name__}). Confira a internet."
    if player:
        try:
            player.write_log(f"[GitHub] {texto.splitlines()[0]}")
        except Exception:
            pass
    return texto
