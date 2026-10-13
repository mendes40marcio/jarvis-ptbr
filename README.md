# JARVIS — edição pt-BR para Linux

Assistente de voz no estilo do JARVIS dos filmes, em português do Brasil, rodando no Ubuntu (Wayland). Ele conversa por voz em tempo real, enxerga a tela, pesquisa na web, controla o computador e tem plugins próprios, como um **modo professor** que ensina programação olhando o seu código.

> **Base do projeto:** este repositório é uma versão modificada do **[Mark-LV](https://github.com/FatihMakes/Mark-LV)**, criado por **FatihMakes** e distribuído sob a licença **[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)** (uso não comercial). O crédito pela arquitetura original — sessão de voz com o Gemini Live, interface, sistema de ações e de plugins — é do autor original. O README original está em [`README.original.md`](README.original.md). Abaixo estão as modificações que **eu** fiz.

---

## O que eu mudei

### Correções
- **Conversa caindo a cada ~10 minutos.** A API do Gemini Live avisa antes de encerrar a sessão (mensagem *GoAway*), mas o aviso era ignorado. A causa era uma comparação de texto: a mensagem de erro do Python (`unhandled errors in a TaskGroup`) contém a palavra `handle`, e o código confundia toda desconexão com "token de retomada rejeitado", descartando o contexto da conversa. Agora a sessão é renovada no aviso e a conversa continua.
- **Visão de tela no Wayland.** A captura usava `mss`, que só funciona no X11; no Wayland a imagem saía toda preta e o assistente ficava "cego". Agora, no Wayland, a captura é pedida ao sistema pelo **xdg-desktop-portal** (`core/tela_portal.py`), o caminho oficial e com permissão do usuário. Se o portal falhar, volta ao método antigo.
- **Transcrição em outros idiomas.** A voz em português às vezes era transcrita em francês ou espanhol. A transcrição foi fixada em `pt-BR`.
- **Hora errada.** O horário entrava no prompt só ao abrir o programa, e a sessão continuava por horas com ele; o modelo chegava a "corrigir" o fuso por conta própria. Agora existe a ferramenta `hora_atual`, que lê o relógio do sistema no momento da pergunta.
- **Segurança e bugs em ações:** *path traversal* no `dev_agent.py` (escrita fora da pasta permitida), detector de erro com falso positivo no `code_helper.py` e abertura do VS Code no Linux.

### Recursos novos
- **Modo professor** (`plugins/modo_professor.py`): ao ser ativado ("Jarvis, modo professor"), ele olha a tela antes de responder e ensina em vez de entregar a resposta — explica o que o erro significa, dá uma pista e faz uma pergunta. Confere a tela de novo a cada dica, para não citar variáveis de memória.
- **Integração com o GitHub** (`plugins/github_info.py`): "o que eu fiz essa semana?", lista de repositórios, projetos parados e detalhes de um repositório. Funciona sem token para repositórios públicos; com um token **só leitura**, inclui os privados.
- **Jogos do time** (`plugins/football_schedule.py`): próximos jogos pela API pública da ESPN (com TheSportsDB como reserva), calculados em código em vez de busca na web.
- **Abertura personalizada** (`core/briefing_extras.py`): saudação por horário, clima da cidade (Open-Meteo, grátis e sem chave), manchetes de tecnologia em português e do mercado de games (RSS).
- **Trilha de abertura** (`core/intro_music.py`): uma música toca sozinha no início e desce para o fundo enquanto o JARVIS fala ("ducking"), controlada pelo `mpv` via IPC. A música não acompanha o repositório: cada um coloca a sua na pasta `music/`.
- **Personalização:** português do Brasil, tratamento formal ("senhor") e interface de reator.

### Princípio que segui
Sempre que possível, as melhorias são **plugins** (um arquivo em `plugins/`), sem alterar o núcleo. Cada mudança foi feita num ramo próprio do git, testada e só então integrada.

---

## Como rodar (Ubuntu)

```bash
sudo apt install mpv python3-gi        # mpv: trilha de abertura | python3-gi: captura de tela no Wayland
git clone https://github.com/mendes40marcio/<este-repositorio>.git
cd <este-repositorio>
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Na primeira execução, a própria interface pede a chave da API do Gemini. Na primeira captura de tela, o Ubuntu pergunta se permite capturas — é preciso aceitar para a visão funcionar.

### Configuração (`config/api_keys.json`, criado na primeira execução e fora do git)
| Chave | Para quê |
|---|---|
| `briefing_city` | Cidade do clima na abertura, por exemplo `"Curitiba"`. Sem ela, a abertura segue sem o clima. |
| `briefing_lat`, `briefing_lon`, `briefing_timezone` | Opcionais, para fixar as coordenadas à mão. |

O usuário e o token do GitHub são configurados em **⚙ → PLUGIN SETTINGS → GitHub**.

---

## Segurança
- Chaves, certificados, memória do assistente e arquivos enviados ficam fora do repositório (`.gitignore`).
- O painel de controle pelo celular escuta só na rede local e exige um código de uso único; não faça redirecionamento de portas no roteador.
- O assistente pode rodar código e controlar teclado e mouse. Não peça para ele "seguir instruções" de páginas ou repositórios desconhecidos, e só coloque em `plugins/` arquivos que você leu.

---

## Sobre mim
Sou o **Marcio**, operador de máquinas industriais há cerca de 20 anos, em transição para a área de software. Estudo Engenharia de Software e meu objetivo é trabalhar com **Engenharia de IA e Indústria 4.0**. Este projeto é parte do meu aprendizado: diagnosticar bugs reais, entender o que acontece por baixo dos panos (como a diferença entre X11 e Wayland) e construir em cima do trabalho de outra pessoa com responsabilidade.

GitHub: [@mendes40marcio](https://github.com/mendes40marcio)

## Licença
Mesma do projeto original: **[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)** — veja [`LICENSE`](LICENSE). Uso **não comercial**, com crédito ao autor original (FatihMakes) e indicação das modificações.
