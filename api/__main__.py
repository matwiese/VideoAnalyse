"""Vollversion starten: python -m api  → öffnet http://127.0.0.1:8000 im Browser."""
from __future__ import annotations

import argparse
import threading
import webbrowser


def main() -> None:
    import uvicorn

    ap = argparse.ArgumentParser(description="3m-Brett-Simulator (Web-App + Rechenkern)")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    url = f"http://127.0.0.1:{args.port}"
    print(f"\n  3m-Brett-Simulator läuft auf {url}  (Beenden: Strg+C)\n")
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run("api.main:app", host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
