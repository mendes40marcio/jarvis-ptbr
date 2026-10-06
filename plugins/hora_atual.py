"""Hora e data exatas de agora, lidas do relógio do computador."""
from datetime import datetime

FUSO = "America/Sao_Paulo"   # horário de Brasília

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo(FUSO)
except Exception:
    _TZ = None

_DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
         "sexta-feira", "sábado", "domingo"]
_MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
          "agosto", "setembro", "outubro", "novembro", "dezembro"]

PLUGIN = {
    "name": "hora_atual",
    "description": (
        "Retorna a hora e a data exatas de AGORA, do relógio do computador "
        "(horário de Brasília). Use SEMPRE que perguntarem que horas são, que dia "
        "é hoje, o dia da semana, ou para calcular quanto tempo falta para algo. "
        "Nunca diga a hora de cabeça: o horário recebido no início da sessão está "
        "desatualizado. O relógio do computador está certo; nunca abra ajustes de "
        "data, hora ou fuso por causa disso."
    ),
    "parameters": {"type": "OBJECT", "properties": {}, "required": []},
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        agora = datetime.now(_TZ) if _TZ else datetime.now()
        return (f"Agora são {agora:%H:%M} de {_DIAS[agora.weekday()]}, "
                f"{agora.day} de {_MESES[agora.month - 1]} de {agora.year} "
                f"(horário de Brasília).")
    except Exception as e:
        return f"Não consegui ler o relógio do computador: {e}"
