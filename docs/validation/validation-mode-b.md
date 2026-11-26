# Validierung Modus B (Etappe 6) – an synthetischen Daten

Echte Videodaten liegen noch nicht vor. Geprüft wird deshalb an **synthetischen Messdaten**
(`core/synthetic.py`, Beispieldatei `data/examples/synthetic_elite_w58_200Hz.trc`): ein
Level-2-Sprung „Elite w 58 kg“ mit bekannten, von den Defaults abweichenden Kraftwerten
(Knie-Strecker ×1,15, Hüft-Strecker ×0,85, Plantarflexoren ×1,10), abgetastet mit 200 Hz,
3 mm Markerrauschen, OpenCap-ähnliche Markernamen, Einheit mm. Rohdaten der Läufe:
`docs/validation/data/matching_synthetic.json`.

## Ereigniserkennung (automatisch)

| Rauschen | TD-Fehler | Kontaktzeit-Fehler |
| --- | --- | --- |
| 0 mm | 0,0 ms | −4,8 ms |
| 3 mm | −2,3 … +2,4 ms | +1,5 … +6,5 ms |
| 6 mm | −3,7 … +3,0 ms | +5,9 … +12,6 ms |

→ TD auf < 1 Bild (5 ms) genau (Test `test_event_detection_within_one_frame`).

## Filter (Residualanalyse nach Winter)

Testsignal 1,5 + 4 Hz mit 10 mm Rauschen: Achsenabschnitt = 0,0109 m (≈ Rausch-RMS 0,010 m),
gewählte Grenzfrequenz 7 Hz. Synthetischer Sprung: 7 Hz (Einzelwerte 3–12 Hz).

## Inverse Dynamik

| Prüfung | Ergebnis |
| --- | --- |
| Algebra (ohne Rauschen, starre Schwabbelmassen, glatte Kontaktphase) | Brettkraft < 5 % RMS, Kniewinkel exakt, H_y ±5 % ✅ |
| Mit realen Schwabbelmassen (Marker sehen keine Weichteile) | Brettkraft im Mittelteil bis ~20 % daneben ⚠ methodische Grenze |
| 3 mm Rauschen, 6–7 Hz: F_z | ±0,5 BW RMS; Hauptmaximum 4,91 BW (wahr 4,87 BW) ✅ |
| 3 mm Rauschen, 6 Hz: Knie-/Hüftmoment | ≈ 10–12 % des Verlaufsbereichs ✅ |
| 3 mm Rauschen: MTP-/Sprunggelenkmoment | 40–80 % → als **unsicher** gekennzeichnet ⚠ |
| Residualkraft im Flug | 0,47–0,68 BW (Gütemaß; Warnung ab 0,5 BW) |
| Aufprallspitze (~1 ms) | aus 200-Hz-Video nicht auflösbar |

## Matching (CMA-ES 20 × 14, mit Anfangsbedingungs-Offsets)

| | Start (generische Werte) | Ergebnis |
| --- | --- | --- |
| **Score (gewichtetes RMS)** | 41,7 % | **9,99 %** ✅ (SPEC: < 10 %) |
| Gelenkwinkel | – | 17,8 % (≙ °) |
| Rumpforientierung | – | 9,9 % |
| Linearimpuls TO | – | 6,9 % |
| Drehimpuls TO | – | 4,2 % |
| Kontaktdauer | – | 4,4 % |

Geschätzte Kraftfaktoren gegenüber den generischen Werten:

| Generator | geschätzt | wahr | Bewertung |
| --- | --- | --- | --- |
| Knie-Strecker | ×1,30 | ×1,15 | Richtung richtig |
| Plantarflexoren | ×1,76 | ×1,10 | überschätzt |
| Hüft-Strecker | ×1,21 | ×0,85 | **falsche Richtung** |

**Bewertung:** Das Matching reproduziert die Bewegung innerhalb des SPEC-Kriteriums, die einzelnen
Kraftparameter sind aus *einem* Sprung aber nicht eindeutig identifizierbar – Gelenke
kompensieren sich gegenseitig (bekanntes Problem, vgl. Kong et al.: generische Werte
verschlechtern das Matching, subjektspezifische Dynamometrie verbessert es). Empfehlung:
mehrere Sprünge gemeinsam matchen (Etappe 6b) und mindestens Knie/Hüfte isokinetisch messen;
gemessene T_max dann als „Gemessen“ fixieren und nur Timings matchen.
Ein Score knapp unter 10 % an synthetischen Daten ist keine Garantie für echte Videos (dort
kommen Perspektivfehler, Marker-Verschiebung und Modellfehler hinzu).
