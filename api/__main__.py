"""Vollversion starten: python -m api  -> oeffnet den Browser, sobald der Server antwortet.

Robust fuer Windows: Browser erst nach erfolgreichem Health-Check, freier Port wird automatisch
gesucht, Fehler werden mit Hinweisen ausgegeben (nur ASCII-Ausgaben, damit alte Konsolen-
Codepages nicht stoeren).
"""
from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _already_running(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def _open_when_ready(url: str, timeout: float = 180.0) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=2) as r:
                if r.status == 200:
                    print(f"  Bereit nach {time.time() - t0:.0f} s - Browser wird geoeffnet: {url}", flush=True)
                    webbrowser.open(url)
                    return
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    print("  Server antwortet nicht. Bitte Fehlermeldung oben pruefen.", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="3m-Brett-Simulator (Web-App + Rechenkern)")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    print("\n  3m-Brett-Simulator - Rechenkern wird gestartet (erster Start kann 10-60 s dauern) ...", flush=True)
    port = args.port
    if _already_running(port):
        url = f"http://127.0.0.1:{port}"
        print(f"  Laeuft bereits auf {url} - Browser wird geoeffnet.", flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        return
    if not _port_free(port):
        for p in range(port + 1, port + 50):
            if _port_free(p):
                print(f"  Port {port} ist belegt - verwende Port {p}.", flush=True)
                port = p
                break
    url = f"http://127.0.0.1:{port}"
    try:
        import uvicorn

        from api.main import app  # Importfehler hier sichtbar machen, bevor der Server startet
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        print("\n  FEHLER beim Laden des Rechenkerns. Haeufige Ursachen:\n"
              "   - Installation unvollstaendig: Ordner .venv loeschen und Start-Skript erneut ausfuehren\n"
              "   - Python zu alt: mindestens Python 3.10 noetig (python.org)\n", flush=True)
        sys.exit(1)
    if not args.no_browser:
        threading.Thread(target=_open_when_ready, args=(url,), daemon=True).start()
    print(f"  Adresse: {url}   (Fenster offen lassen, Beenden mit Strg+C)\n", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
