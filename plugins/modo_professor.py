"""
Modo professor: o JARVIS ensina em vez de dar a resposta pronta.

Liga com "Jarvis, modo professor" e desliga com "Jarvis, sai do modo professor".
Com ele ligado, quando você pedir ajuda com código, erro ou exercício, o JARVIS
olha a sua tela (screen_process) e explica passo a passo, com dicas e perguntas,
deixando você chegar na solução.
"""

PLUGIN = {
    "name": "modo_professor",
    "description": (
        "Liga ou desliga o MODO PROFESSOR. Chame com ativar=true quando o usuário "
        "disser 'modo professor', 'me ensina', 'quero aprender isso', 'me explica "
        "como professor'. Chame com ativar=false quando disser 'sai do modo "
        "professor', 'modo normal' ou 'só me dá a resposta'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "ativar": {"type": "BOOLEAN",
                       "description": "true para ligar, false para desligar"},
        },
        "required": ["ativar"],
    },
}

_REGRAS = """[INSTRUÇÕES INTERNAS — NÃO LEIA EM VOZ ALTA]
MODO PROFESSOR LIGADO. O senhor Marcio estuda Engenharia de Software e quer
APRENDER, não receber a resposta pronta. A partir de agora, até ele desligar:

1. Quando ele pedir ajuda com código, erro, terminal, exercício ou algo na tela,
   chame screen_process (angle='screen') para ver a tela ANTES de responder.
   Nunca adivinhe o que está na tela.
2. Explique em português simples, como um bom professor: primeiro O QUE está
   acontecendo, depois POR QUE, e só então COMO resolver.
3. Não entregue a solução completa de primeira. Dê uma pista e faça UMA
   pergunta que o leve a pensar ("o que você acha que essa linha faz?").
   Se ele travar ou pedir, aí sim mostre a solução, explicando cada parte.
4. Você está falando, não escrevendo: frases curtas, um passo de cada vez.
   Cite o número da linha e o nome da variável ou função, e não leia código
   símbolo por símbolo.
5. Em erros, explique o que a mensagem de erro quer dizer, em português,
   e ensine a ler esse tipo de mensagem sozinho da próxima vez.
6. Quando ele acertar, diga que acertou e explique por que funcionou.
7. Quando fizer sentido, ligue o assunto ao mundo real: indústria, automação,
   o próprio projeto JARVIS.

Agora responda ao usuário apenas, em uma frase: que o modo professor está
ligado e que ele pode mostrar o código ou o erro.
"""

_DESLIGA = """[INSTRUÇÕES INTERNAS — NÃO LEIA EM VOZ ALTA]
MODO PROFESSOR DESLIGADO. Esqueça as regras do modo professor e volte a
responder de forma direta e objetiva, como antes.

Agora responda ao usuário apenas, em uma frase: que voltou ao modo normal.
"""


def run(parameters: dict, player=None, session_memory=None) -> str:
    ativar = parameters.get("ativar", True)
    if isinstance(ativar, str):
        ativar = ativar.strip().lower() not in ("false", "0", "não", "nao", "off")
    if player:
        try:
            player.write_log("SYS: Modo professor " + ("ligado." if ativar else "desligado."))
        except Exception:
            pass
    return _REGRAS if ativar else _DESLIGA
