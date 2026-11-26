@echo off
REM 3m-Brett-Simulator – Vollversion starten (Windows). Doppelklick genuegt.
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
if not exist .venv (
  echo Erster Start: richte Python-Umgebung ein ^(einmalig, ca. 1-2 Minuten^) ...
  %PY% -m venv .venv || (echo Python 3.10 oder neuer fehlt: https://www.python.org/downloads/ & pause & exit /b 1)
  .venv\Scripts\python -m pip install --upgrade pip >nul
  .venv\Scripts\python -m pip install -e . || (pause & exit /b 1)
)
.venv\Scripts\python -m api
pause
