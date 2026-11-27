@echo off
chcp 65001 >nul
title 3m-Brett-Simulator
cd /d "%~dp0"
echo.
echo   3m-Brett-Simulator - Start
echo   ==========================
echo.

REM --- Python suchen ---
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo   FEHLER: Python wurde nicht gefunden.
  echo   Bitte Python 3.10 oder neuer installieren: https://www.python.org/downloads/
  echo   Beim Installieren unbedingt "Add python.exe to PATH" anhaken.
  echo.
  pause
  exit /b 1
)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>nul
if errorlevel 1 (
  echo   FEHLER: Python ist zu alt oder nicht richtig installiert. Mindestens Python 3.10 noetig.
  echo   Download: https://www.python.org/downloads/
  echo.
  pause
  exit /b 1
)

REM --- Einmalige Einrichtung (wird wiederholt, falls sie abgebrochen wurde) ---
if not exist ".venv\installiert.ok" (
  echo   Erster Start: Einrichtung laeuft, das dauert 1-3 Minuten. Internet wird benoetigt.
  if exist ".venv" rmdir /s /q ".venv"
  %PY% -m venv .venv
  if errorlevel 1 goto fehler
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -e .
  if errorlevel 1 goto fehler
  echo ok> ".venv\installiert.ok"
  echo.
  echo   Einrichtung fertig.
  echo.
)

".venv\Scripts\python.exe" -m api
echo.
echo   Der Simulator wurde beendet.
pause
exit /b 0

:fehler
echo.
echo   FEHLER bei der Einrichtung. Bitte Internetverbindung pruefen und das Skript erneut starten.
echo   Falls es wieder scheitert: ein Foto dieses Fensters schicken.
echo.
pause
exit /b 1
