import random, shutil, sys, urllib.parse, urllib.request
import gi
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

destino = sys.argv[1] if len(sys.argv) > 1 else "/tmp/tela_portal.png"
bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
token = f"jarvis{random.randint(0, 999999)}"
sender = bus.get_unique_name()[1:].replace(".", "_")
handle = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
loop, res = GLib.MainLoop(), {}

def resposta(conn, nome, caminho, iface, sinal, params):
    codigo, dados = params.unpack()
    res["codigo"], res["uri"] = codigo, dados.get("uri")
    loop.quit()

bus.signal_subscribe("org.freedesktop.portal.Desktop", "org.freedesktop.portal.Request",
                     "Response", handle, None, Gio.DBusSignalFlags.NONE, resposta)
bus.call_sync("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
              "org.freedesktop.portal.Screenshot", "Screenshot",
              GLib.Variant("(sa{sv})", ("", {"handle_token": GLib.Variant("s", token),
                                             "interactive": GLib.Variant("b", False)})),
              None, Gio.DBusCallFlags.NONE, -1, None)
GLib.timeout_add_seconds(60, loop.quit)
loop.run()
if res.get("codigo") != 0 or not res.get("uri"):
    sys.exit(f"falhou: {res or 'sem resposta'}")
origem = urllib.parse.unquote(urllib.parse.urlparse(res["uri"]).path)
shutil.move(origem, destino)
print("ok", destino)
