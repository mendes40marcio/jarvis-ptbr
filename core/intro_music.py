"""
Trilha de abertura do JARVIS: uma música baixinha no fundo enquanto ele faz o
resumo do início, que some aos poucos quando ele termina de falar.

Toca com o mpv, em processo separado. A música vem da pasta music/ do projeto:
de preferência um arquivo chamado back_in_black (qualquer formato de áudio);
se não houver, o primeiro arquivo de áudio da pasta. Sem mpv ou sem música, a
abertura acontece normalmente, só que sem trilha.

Teste isolado (dentro de ~/Documentos/Mark-LV-main, com o .venv ativo):
    python -m core.intro_music
"""
import asyncio
import json
import os
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path

# ── Ajustes ──────────────────────────────────────────────────────────────────
INTRO_ENABLED = True
MUSIC_DIR     = Path(__file__).resolve().parent.parent / "music"
PREFERRED     = "back_in_black"   # nome do arquivo preferido (sem extensão)
VOLUME        = 40                # volume do mpv, 0–100 (curva cúbica: 50 já é baixo)
FADE_IN       = 2.0               # segundos para a música entrar
FADE_OUT      = 4.0               # segundos para a música sumir
LEAD_SECONDS  = 10                 # segundos de música sozinha antes da saudação
LEAD_VOLUME   = 75                # volume da música enquanto ela está sozinha
MAX_SECONDS   = 150               # trava de segurança: nunca toca mais que isso

AUDIO_EXT = {".mp3", ".ogg", ".opus", ".flac", ".m4a", ".wav", ".webm", ".aac"}
SOCK      = "/tmp/jarvis-intro-mpv.sock"


def _pick_track() -> Path | None:
    if not MUSIC_DIR.is_dir():
        return None
    files = sorted(p for p in MUSIC_DIR.iterdir()
                   if p.is_file() and p.suffix.lower() in AUDIO_EXT)
    for p in files:
        if p.stem.lower() == PREFERRED:
            return p
    return files[0] if files else None


def _die_with_parent():
    """No Linux, o mpv é encerrado junto se o JARVIS cair (ex.: Ctrl+C)."""
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").prctl(1, signal.SIGTERM)   # PR_SET_PDEATHSIG
    except Exception:
        pass


class IntroMusic:
    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self.volume = 0

    def start(self) -> bool:
        """Inicia a música em volume 0. Retorna False se não der para tocar."""
        if not INTRO_ENABLED:
            return False
        mpv = shutil.which("mpv")
        if not mpv:
            print("[Intro] mpv não instalado — abertura sem música "
                  "(instale com: sudo apt install mpv)")
            return False
        track = _pick_track()
        if not track:
            print(f"[Intro] Nenhuma música em {MUSIC_DIR} — abertura sem música")
            return False
        try:
            os.unlink(SOCK)
        except OSError:
            pass
        self.proc = subprocess.Popen(
            [mpv, "--no-video", "--no-terminal", "--really-quiet",
             "--volume=0", f"--length={MAX_SECONDS}",
             f"--input-ipc-server={SOCK}", str(track)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=_die_with_parent if os.name == "posix" else None,
        )
        print(f"[Intro] 🎵 Trilha de abertura: {track.name}")
        return True

    def _send(self, *cmd) -> None:
        try:
            with socket.socket(socket.AF_UNIX) as s:
                s.settimeout(0.5)
                s.connect(SOCK)
                s.sendall((json.dumps({"command": list(cmd)}) + "\n").encode())
        except OSError:
            pass

    def set_volume(self, vol: float) -> None:
        self.volume = max(0, min(100, int(vol)))
        self._send("set_property", "volume", self.volume)

    async def fade(self, start: float, end: float, secs: float) -> None:
        # O socket do mpv leva um instante para aparecer na primeira vez.
        t0 = time.monotonic()
        while not os.path.exists(SOCK) and time.monotonic() - t0 < 2:
            await asyncio.sleep(0.05)
        steps = max(1, int(secs / 0.1))
        for i in range(1, steps + 1):
            if not self.playing():
                return
            self.set_volume(start + (end - start) * i / steps)
            await asyncio.sleep(secs / steps)

    def playing(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def stop(self) -> None:
        if self.playing():
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except Exception:
                self.proc.kill()
        self.proc = None
        try:
            os.unlink(SOCK)
        except OSError:
            pass


if __name__ == "__main__":
    async def _demo():
        m = IntroMusic()
        if not m.start():
            return
        print(f"Entrando em {FADE_IN}s até o volume {VOLUME}...")
        await m.fade(0, VOLUME, FADE_IN)
        print("Tocando por 8 segundos...")
        await asyncio.sleep(8)
        print(f"Saindo em {FADE_OUT}s...")
        await m.fade(VOLUME, 0, FADE_OUT)
        m.stop()
        print("Fim.")
    asyncio.run(_demo())
