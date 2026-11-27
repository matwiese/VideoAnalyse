# Videoaufnahme und Export für die Analyse (Modus B)

Damit die App aus einem Video Brettkraft, Gelenkmomente und subjektspezifische Kraftparameter
schätzen kann, braucht sie die 2D-Bahnen einiger Körperpunkte in der Seitenansicht.

## 1. Aufnahme

| Punkt | Empfehlung | Warum |
| --- | --- | --- |
| Kameraposition | exakt seitlich zur Brettachse, auf Höhe Brettspitze, 6–10 m entfernt, Stativ | Planares Modell (Level 2); Perspektivfehler klein halten |
| Bildrate | **≥ 200 Bilder/s** (SPEC 9.4), Belichtung ≤ 1/1000 s | Kontakt dauert ~0,4 s; Aufsetzen/Abheben auf < 5 ms genau |
| Bildausschnitt | Brettspitze und ganzer Körper von Hürden-Lift-off bis ~0,3 s nach dem Absprung | Anfangszustand wird aus der Flugphase **vor** dem Aufsetzen bestimmt |
| Maßstab | Brettbreite ist bekannt (0,495 m) – besser: Maßstab (1–2 m) in der Brettebene filmen | Umrechnung px → m |
| Brettspitze | gut sichtbar, idealerweise Klebepunkt an der Brettkante | Ursprung, Brettdurchbiegung, Kontakterkennung |
| Körperseite | zur Kamera gewandte Seite (rechts oder links) konsequent tracken | Modell fasst beide Körperhälften zusammen |
| Marker (optional) | Klebepunkte auf Zehenspitze, Ferse, Knöchel, Knie, Trochanter, Schulter, Ellbogen, Handgelenk | Tracking in Kinovea deutlich genauer |

Mehrere Sprünge derselben Athletin/desselben Athleten filmen – SPEC 9 verlangt mindestens fünf
gematchte Sprünge mit RMS < 10 %, bevor Prognosen als kalibriert gelten.

## 2. Tracking

### Variante A (empfohlen): Video-Tracker in der App

Menü **„Video-Tracker“**. Das Video wird nur lokal im Browser geöffnet (kein Upload) – auch
Dateien mit mehreren GB funktionieren, weil der Browser direkt von der Festplatte liest.

1. **Bildrate:** Die App misst die Bildrate der Datei. Bei Handy-Zeitlupen (z. B. 240 Bilder/s
   aufgenommen, als 30 Bilder/s gespeichert) unbedingt die **echte Aufnahme-Bildrate** eintragen.
2. **Bereich:** zum Hürden-Lift-off springen → „Aktuelles = Start“, bis ~0,3 s nach dem Absprung →
   „Aktuelles = Ende“. Bei sehr hoher Bildrate ggf. nur jedes 2. Bild tracken (≥ 200 Hz echt bleiben).
3. **Kalibrierung:** „Maßstab: 2 Punkte klicken“ an einem Meterstab/bekannter Strecke in der
   Brettebene, Länge eintragen (waagrechte Strecke → Haken für Neigungskorrektur);
   „Brettspitze in Ruhe klicken“ in einem Bild ohne Springer:in auf dem Brett; Wasserseite wählen.
4. **Punkte:** Punkt links wählen, mit dem Mausrad hineinzoomen (bis 16×, Ziehen verschiebt, „Ansicht folgt Punkt“ führt mit), im Bild anklicken, dann
   **„Automatisch weiter“** – die App verfolgt den Punkt per Bildvergleich und hält an, sobald sie
   unsicher ist (dann Punkt anklicken und erneut starten). Tasten: ← → Bild, Enter = Vorschlag
   übernehmen, Entf = löschen. Klebepunkte machen die Automatik deutlich zuverlässiger.
5. **Export:** „An Analyse übergeben“ (Vollversion) oder „CSV speichern“.
   Der Stand wird automatisch im Browser gespeichert; „Projekt sichern“ für ein Backup.

Getestet mit einem gerenderten Zeitlupen-Testvideo (1280×720, 222 Bilder): 11 Punkte mit
53 Klicks, Genauigkeit 3–11 mm (Zehenspitze 16 mm); Analyse danach: Kontaktzeit +12 ms,
Brettkraft-Hauptmaximum −7 %, H_y bei TO ±1 % gegenüber der Wahrheit
(`scripts/make_test_video.py`, `web/e2e/tracker.e2e.cjs`).

Falls das Video nicht lädt (häufig HEVC/.mov in Chrome/Firefox): in Safari/Edge öffnen oder umwandeln:

```bash
ffmpeg -i aufnahme.mov -c:v libx264 -crf 18 -an aufnahme.mp4
```

### Variante B: externe Programme

**Kinovea (kostenlos, 2D):** je Körperpunkt eine Trajektorie anlegen, Namen wie unten vergeben,
Koordinatensystem kalibrieren (Ursprung Brettspitze, Maßstab per Linie bekannter Länge),
Export „Trajektorien → CSV“. Erwartetes Format: eine Zeitspalte und je Punkt zwei Spalten
`Name X` / `Name Y` (Einheit in Klammern erlaubt, z. B. `Knie X (m)`).

**OpenCap (markerlos, 3D):** TRC-Datei herunterladen; die Markernamen (`r_knee_study`, …) werden
automatisch erkannt. Achsen in der App setzen: horizontal = Achse Richtung Wasser, vertikal = y.

## 3. Punktnamen

Die App erkennt deutsche und englische Namen (Groß-/Kleinschreibung egal), Zuordnung ist in der
App änderbar:

| Modellpunkt | Pflicht | Beispiele für Namen |
| --- | --- | --- |
| Zehenspitze | ✔ | `Zehe`, `toe`, `r_toe_study` |
| Ferse | ✔ | `Ferse`, `heel`, `r_calc_study` |
| Sprunggelenk | ✔ | `Knöchel`, `ankle` |
| Knie | ✔ | `Knie`, `knee` |
| Hüfte | ✔ | `Hüfte`, `hip`, `trochanter` |
| Schulter | ✔ | `Schulter`, `shoulder` |
| Ellbogen | ✔ | `Ellbogen`, `elbow` |
| Handgelenk | ✔ | `Handgelenk`, `wrist` |
| Ballen (MTP) | – | `Ballen`, `mtp` (sonst aus Ferse–Zehe geschätzt) |
| Hals, Kopf, Fingerspitze | – | `C7`, `Kopf`, `Finger` |
| Brettspitze | empfohlen | `Brettspitze`, `board_tip` |

## 4. In der App

1. Vollversion starten, Körpergröße, -masse und Geschlecht im Parameter-Panel setzen.
2. „Analyse (Video)“ → Datei wählen → Koordinaten/Einheiten prüfen → „Analysieren“.
3. Plausibilität prüfen: **Residualkraft im Flug** sollte < 0,5 BW sein (sonst Maßstab, Achsen,
   Körpermasse oder Markerzuordnung prüfen); Kontaktzeit realistisch (≈ 0,35–0,5 s).
4. „Matching starten“ → Ergebnis übernehmen → als Athletenprofil („Profil ↓“) speichern.

## 5. Grenzen

- MTP- und Sprunggelenkmomente sind aus Video unsicher (kurze Fußsegmente).
- Marker auf der Haut sehen keine Weichteilbewegung; die inverse Dynamik nimmt starre Segmente an
  (Schwabbelmassen nicht messbar) – das verschiebt die Brettkraft um bis zu ~20 % (synthetischer Test).
- Ein 2D-Video erfasst keine Verdrehungen (Schrauben, Kippen) – dafür ist Level 3 vorgesehen.
