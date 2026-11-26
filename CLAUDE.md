# Projektregeln: 3m-Brett-Simulator
- Fachliche Grundlage ist SPEC.md. Bei Widerspruch gilt SPEC.md; frag nach, statt zu raten.
- SI-Einheiten intern, Koordinaten nach SPEC Kap. 3. Jede Funktion dokumentiert Einheiten.
- Jeder physikalische Parameter liegt in data/ als JSON mit Feldern value, unit, source, status.
- Keine Physik ohne Test. Tests aus SPEC Kap. 9.1 müssen vor jedem Commit laufen.
- Bewegungsgleichungen Level 2/3 werden symbolisch erzeugt (SymPy), nie von Hand abgetippt.
- Schätzwerte niemals stillschweigend als Fakten ausgeben: Status in API und UI mitführen.
- Design: Schwarz-Rot-Tokens aus SPEC Kap. 10.4.

## Befehle
- Physik-Tests: `python -m pytest` (Repo-Root)
- Web: `cd web && npm run dev` · Tests `npm test` · Typecheck `npm run typecheck`
- TS-Referenz nach Level-1-Änderungen: `python -m scripts.export_fixtures`
- Vollversion lokal: `python -m api` (Web-App + Backend auf Port 8000)
- Level-2-Gleichungen neu erzeugen: `python -m scripts.generate_level2` (nie level2_generated.py von Hand ändern)
- Nach Web-Änderungen: `cd web && npm run build:standalone` (aktualisiert api/static/index.html)
- Beispieldatensatz Modus B neu erzeugen: `python -m scripts.make_example` (synthetisch!)
- Langläufer-Tests (Matching, Generator): `RUN_SLOW=1 python -m pytest`
- Offene Modellentscheidungen und Rückfragen: docs/validation/model-notes.md
