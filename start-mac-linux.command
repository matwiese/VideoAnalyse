#!/usr/bin/env bash
# 3m-Brett-Simulator - Start (macOS: Doppelklick bzw. Rechtsklick > Oeffnen; Linux: ./start-mac-linux.command)
cd "$(dirname "$0")" || exit 1
echo
echo "  3m-Brett-Simulator - Start"
echo
PY=$(command -v python3 || command -v python)
if [ -z "$PY" ] || ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "  FEHLER: Python 3.10 oder neuer fehlt: https://www.python.org/downloads/"
  read -r -p "  Enter zum Schliessen"; exit 1
fi
if [ ! -f .venv/installiert.ok ]; then
  echo "  Erster Start: Einrichtung laeuft (1-3 Minuten, Internet noetig) ..."
  rm -rf .venv
  if "$PY" -m venv .venv && .venv/bin/python -m pip install --upgrade pip && .venv/bin/python -m pip install -e .; then
    echo ok > .venv/installiert.ok
  else
    echo "  FEHLER bei der Einrichtung. Internet pruefen und erneut starten."
    read -r -p "  Enter zum Schliessen"; exit 1
  fi
fi
.venv/bin/python -m api
