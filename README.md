# 3m-Brett-Simulator – Anlauf & Absprung

Webbasierter Biomechanik-Simulator für Hürde, Brettkontakt und Flug beim 3m-Kunstspringen
(Duraflex Maxiflex B). Fachliche Grundlage: [SPEC.md](SPEC.md), Arbeitsregeln: [CLAUDE.md](CLAUDE.md).

**Stand: Etappen 1–6 umgesetzt** (Etappe 6 an synthetischen Testdaten validiert, echte Videodaten folgen).

| Etappe | Inhalt | Status |
| --- | --- | --- |
| 1 | Datenmodell, Parameter-JSON, Brettmodell (A/B), Level 1, Flugphase, Tests 9.1 Nr. 1, 2, 3, 5, 7, 8 | ✅ grün |
| 2 | Web-UI, Level 1 live im Web Worker (TS ↔ Python 1e-6), 2D-Plots, Slider < 50 ms | ✅ |
| 3 | de Leva, Level 2 planar (SymPy/Kane), Fußkontakt, Drehmoment-Generatoren, Schwabbelmassen, Test Nr. 4, Energiebilanz | ✅ grün |
| 4 | 3D-Szene, Zeitleiste, Kraftvektor, Vergleichsmodus, Segmentfigur Level 2 | ✅ |
| 5 | Optimierung (CMA-ES, Robustheit ±10 ms, Freigang-Nebenbedingung), Parameterstudien 1D/2D (Level 1 + 2), Validierung 9.2 | ✅ (siehe docs/validation) |
| 6 | Modus B: Import (TRC/CSV), Butterworth + Residualanalyse, inverse Dynamik, Matching | ✅ an synthetischen Daten, siehe docs/validation/validation-mode-b.md |
| 7 | Level 3, Asymmetrien, PDF-Report, Brettkalibrier-Assistent | offen |

## Wo öffne ich das Programm?

Es gibt zwei Varianten:

| | Browser-Version (Einzeldatei) | **Vollversion (empfohlen)** |
| --- | --- | --- |
| Öffnen | `3m-Brett-Simulator.html` doppelklicken | Start-Skript doppelklicken → Browser öffnet <http://127.0.0.1:8000> |
| Voraussetzung | nur ein Browser | Python 3.10+ (einmalig installieren) |
| Level 1 (live) | ✅ | ✅ |
| Level 2 (Mehrkörper, Gelenke, Drehimpuls, Saltos) | – | ✅ |
| Optimierung, Level-2-Studien | – | ✅ |
| Video-Tracker (Punkte im Browser verfolgen, CSV) | ✅ | ✅ |
| Analyse eigener Videos (Modus B) | – | ✅ |

### Vollversion starten

1. Python installieren (einmalig): <https://www.python.org/downloads/> – unter Windows beim Installieren
   **„Add python.exe to PATH“** anhaken.
2. Dieses Repository herunterladen: auf GitHub **Code → Download ZIP**, entpacken (oder `git clone`).
3. Starten:
   - **Windows:** `start-windows.bat` doppelklicken.
   - **macOS:** `start-mac-linux.command` doppelklicken (beim ersten Mal ggf. Rechtsklick → Öffnen).
   - **Linux:** `./start-mac-linux.command`
4. Beim ersten Start wird die Python-Umgebung eingerichtet (1–2 Minuten). Danach öffnet sich der
   Browser automatisch auf <http://127.0.0.1:8000>. Fenster offen lassen; beenden mit Strg+C.

Oben rechts zeigt ein grüner Punkt „Vollversion“; dann ist **Level 2** anwählbar. Alles läuft
lokal auf deinem Rechner, es werden keine Daten verschickt. Am schnellsten ist Chrome oder Edge auf
einem Rechner mit mehreren CPU-Kernen (Optimierung nutzt alle Kerne).

### Für Entwicklung

```bash
pip install -e ".[dev]"
```

```bash
python -m pytest
```

```bash
python -m api --no-browser
```

```bash
cd web && npm install && npm run dev
```

Der Dev-Server (<http://localhost:5173>) leitet `/api` an das Backend auf Port 8000 weiter.
Nach Änderungen an der Web-App `npm run build:standalone` ausführen – das aktualisiert die
Einzeldatei und `api/static/index.html` der Vollversion.

Kennwert-Tabelle mit Status-Markierung (SPEC 11.3):

```bash
python -m scripts.report_level1 elite_w_58 7.5
```

Level-2-Gleichungen neu erzeugen (SymPy/Kane, ~30 s):

```bash
python -m scripts.generate_level2
```

## Einzeldatei zum Herunterladen

Die komplette App (ohne Python-Backend) als eine HTML-Datei, die per Doppelklick im Browser läuft:

```bash
cd web && npm run build:standalone
```

Ergebnis: `web/dist-standalone/index.html` (≈ 1,1 MB). Nur die Schriften Inter/JetBrains Mono werden online nachgeladen; offline greifen Systemschriften.

## Struktur

```
core/            Python-Physikkern: board.py, muscles.py, events.py, flight.py, athlete.py, optimize.py, report.py
core/models/     level1.py, level2.py, level2_generated.py (SymPy-Code, nicht von Hand ändern)
core/tests/      Tests SPEC 9.1 + Energiebilanz (hypothesis) + Plausibilität 9.2
api/             FastAPI: Level 1/2, Optimierungs- und Studien-Jobs, liefert die Web-App aus (python -m api)
web/             React 18 + TS + Vite + Zustand + react-three-fiber; src/sim-live = Level-1-Port im Web Worker
data/            parameters.json (value/unit/source/status), presets.json, metrics.json, anthropometry_de_leva.json
docs/validation/ Modellnotizen, offene Rückfragen, Kennwert-Tabellen
```

## Eigene Videos auswerten

**Schritt-für-Schritt-Handbuch (PDF):** [docs/Anleitung_Videoanalyse_3m-Brett.pdf](docs/Anleitung_Videoanalyse_3m-Brett.pdf)

Anleitung zu Aufnahme, Tracking (Kinovea/OpenCap) und Export: [docs/video-anleitung.md](docs/video-anleitung.md).
Punkte lassen sich direkt in der App tracken (Menü „Video-Tracker“, auch für sehr große Videos – kein Upload).
Ohne eigenes Video: in der App „Analyse (Video)“ → „Beispieldatensatz laden“ (synthetisch).

## Wichtige Hinweise

- Jede Ausgabe trägt einen Status. **Gelb (S)** = beruht auf mindestens einem Schätzparameter.
  Klick auf ein Status-Badge im Parameter-Panel markiert einen Wert als „Gemessen“.
- Level 1 ist ein Zwei-Massen-Modell ohne Gelenke, Arme und Rotation. H_y,
  Rotationspotenzial und Saltoanzahl liefert Level 2.
- Level 2 nutzt generische, geschätzte Kraftwerte. Absolute Zahlen erst nach Kalibrierung
  (SPEC 9.3/9.4) fachlich interpretieren; Trends und Vergleiche sind aussagekräftiger.
- Offene fachliche Rückfragen (u. a. Widerspruch in k_s(d)) stehen in
  [docs/validation/model-notes.md](docs/validation/model-notes.md).
