#!/usr/bin/env bash
# 3m-Brett-Simulator – Vollversion starten (macOS: Doppelklick; Linux: ./start-mac-linux.command)
cd "$(dirname "$0")"
PY=$(command -v python3 || command -v python)
if [ -z "$PY" ]; then echo "Python 3.10 oder neuer fehlt: https://www.python.org/downloads/"; read -r; exit 1; fi
if [ ! -d .venv ]; then
  echo "Erster Start: richte Python-Umgebung ein (einmalig, ca. 1-2 Minuten) ..."
  "$PY" -m venv .venv && .venv/bin/python -m pip install --upgrade pip >/dev/null && .venv/bin/python -m pip install -e . || { read -r; exit 1; }
fi
.venv/bin/python -m api
