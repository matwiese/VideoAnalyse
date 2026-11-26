# 3m-Brett-Simulator – Anlauf & Absprung

Webbasierter Biomechanik-Simulator für Hürde, Brettkontakt und Flug beim 3m-Kunstspringen
(Duraflex Maxiflex B). Fachliche Grundlage: [SPEC.md](SPEC.md), Arbeitsregeln: [CLAUDE.md](CLAUDE.md).

**Stand: Etappe 1 + 2 umgesetzt** (dazu Teile von Etappe 4 und 5: 3D-Szene, Zeitleiste, Vergleichsmodus, Parameterstudien).

| Etappe | Inhalt | Status |
| --- | --- | --- |
| 1 | Datenmodell, Parameter-JSON, Brettmodell (A/B), Level 1, Flugphase, Tests 9.1 Nr. 1, 2, 3, 5, 7, 8 | ✅ grün |
| 2 | Web-UI, Level 1 live im Web Worker (TS ↔ Python 1e-6), 2D-Plots, Slider < 50 ms | ✅ |
| 3 | de Leva, Level 2 planar (SymPy/Kane), Kontakt, Muskeln, Schwabbelmassen | offen |
| 4 | 3D-Szene, Zeitleiste, Kraftvektor, Vergleichsmodus | ✅ Grundversion (Level-1-Figur) |
| 5 | Optimierung (SA/CMA-ES), Parameterstudien, Heatmaps | Studien ✅, Optimierung offen |
| 6 | Modus B: Import, inverse Dynamik, Matching | offen |
| 7 | Level 3, Asymmetrien, PDF-Report, Brettkalibrier-Assistent | offen |

## Schnellstart

```bash
pip install -e ".[dev]"
```

```bash
python -m pytest
```

```bash
cd web && npm install && npm run dev
```

Dann <http://localhost:5173> öffnen. Optional die API (Referenzrechner, Basis für Level 2/3):

```bash
uvicorn api.main:app --reload
```

Kennwert-Tabelle mit Status-Markierung (SPEC 11.3):

```bash
python -m scripts.report_level1 elite_w_58 7.5
```

Nach Änderungen an Level 1 die TS-Referenz neu erzeugen und vergleichen:

```bash
python -m scripts.export_fixtures && cd web && npm test
```

## Struktur

```
core/            Python-Physikkern: board.py, muscles.py, events.py, flight.py, models/level1.py, report.py
core/tests/      Tests SPEC 9.1 + Energiebilanz (hypothesis) + Plausibilität 9.2
api/             FastAPI (Parameter, Presets, Simulation Level 1)
web/             React 18 + TS + Vite + Zustand + react-three-fiber; src/sim-live = Level-1-Port im Web Worker
data/            parameters.json (value/unit/source/status), presets.json, metrics.json
docs/validation/ Modellnotizen, offene Rückfragen, Kennwert-Tabellen
```

## Wichtige Hinweise

- Jede Ausgabe trägt einen Status. **Gelb (S)** = beruht auf mindestens einem Schätzparameter.
  Klick auf ein Status-Badge im Parameter-Panel markiert einen Wert als „Gemessen“.
- Level 1 ist ein Zwei-Massen-Modell ohne Gelenke, Arme und Rotation. H_y und
  Rotationspotenzial erscheinen erst mit Level 2.
- Offene fachliche Rückfragen (u. a. Widerspruch in k_s(d)) stehen in
  [docs/validation/model-notes.md](docs/validation/model-notes.md).
