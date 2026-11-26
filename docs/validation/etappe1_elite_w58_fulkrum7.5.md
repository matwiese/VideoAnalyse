# Level 1 – Elite w 58 kg, Fulkrum 7.5

| Kategorie | Größe | Wert | Einheit | Status |
| --- | --- | --- | --- | --- |
| Brett | Brettsteifigkeit k_s am Lastort | 5824 | N/m | Literatur |
| Brett | Effektive Brettmasse m_b | 8.87 | kg | Literatur |
| Brett | Eigenfrequenz leer | 4.08 | Hz | Literatur |
| Brett | Eigenfrequenz belastet √(k/(m_b+M)) | 1.49 | Hz | Literatur |
| Brett | Brett-Phasenlage bei TD (180–360° = aufwärts) | 296 | ° | ⚠ Schätzung |
| Zeiten | Hürdenflugzeit | 0.798 | s | ⚠ Schätzung |
| Geschwindigkeiten | v_z KSP bei TD | -4.00 | m/s | ⚠ Schätzung |
| Geschwindigkeiten | ż_b Brett bei TD | 0.83 | m/s | ⚠ Schätzung |
| Geschwindigkeiten | Relativgeschwindigkeit Springer–Brett bei TD | -4.83 | m/s | ⚠ Schätzung |
| Geschwindigkeiten | ż_b max. abwärts | -5.10 | m/s | ⚠ Schätzung |
| Geschwindigkeiten | v_z KSP am tiefsten Punkt | 0.20 | m/s | ⚠ Schätzung |
| Geschwindigkeiten | v_z KSP bei TO | 3.79 | m/s | ⚠ Schätzung |
| Geschwindigkeiten | v_x KSP bei TO (Level 1: konstant) | 0.50 | m/s | ⚠ Schätzung |
| Geschwindigkeiten | ż_b Brett bei TO | 2.34 | m/s | ⚠ Schätzung |
| Geschwindigkeiten | Absprungwinkel (zur Horizontalen) | 82.5 | ° | ⚠ Schätzung |
| Kräfte | Spitzenkraft Brett F_z | 2516 | N | ⚠ Schätzung |
| Kräfte | Spitzenkraft Brett F_z | 4.42 | BW | ⚠ Schätzung |
| Kräfte | Mittlere Kontaktkraft | 2.81 | BW | ⚠ Schätzung |
| Kräfte | Max. Kraftanstiegsrate 0–50 ms | 86285 | N/s | ⚠ Schätzung |
| Kräfte | Max. Brett-Federkraft k_s·|z_b| | 2791 | N | ⚠ Schätzung |
| Impuls | Vertikaler Kraftstoß Depression | 367.4 | N s | ⚠ Schätzung |
| Impuls | Vertikaler Kraftstoß Recoil | 333.1 | N s | ⚠ Schätzung |
| Höhen / Wege | Max. Brettdurchbiegung | 0.479 | m | ⚠ Schätzung |
| Höhen / Wege | KSP-Höhe bei TO | 0.999 | m | ⚠ Schätzung |
| Höhen / Wege | KSP-Steigung nach TO | 0.731 | m | ⚠ Schätzung |
| Höhen / Wege | Max. Flughöhe KSP über Brett | 1.730 | m | ⚠ Schätzung |
| Höhen / Wege | Max. Flughöhe KSP über Wasser | 4.730 | m | ⚠ Schätzung |
| Höhen / Wege | Freigang: KSP-Abstand zur Spitze in Brettebene | 0.659 | m | ⚠ Schätzung |
| Zeiten | Depressionszeit | 0.217 | s | ⚠ Schätzung |
| Zeiten | Recoilzeit | 0.220 | s | ⚠ Schätzung |
| Zeiten | Kontaktzeit | 0.438 | s | ⚠ Schätzung |
| Zeiten | Flugzeit bis Wasser | 1.228 | s | ⚠ Schätzung |
| Energie | Kinetische Energie bei TO | 423 | J | ⚠ Schätzung |
| Energie | Max. Brett-Federenergie ½k_s z_b² | 669 | J | ⚠ Schätzung |
| Energie | Energie Springer → Brett (Depression) | 679 | J | ⚠ Schätzung |
| Energie | Energie Brett → Springer (Recoil) | 633 | J | ⚠ Schätzung |
| Energie | Wirkungsgrad Brett (Recoil/Depression) | 93.1 | % | ⚠ Schätzung |
| Leistung | Netto-Muskelarbeit Bein | 137 | J | ⚠ Schätzung |
| Leistung | Netto-Muskelarbeit Bein | 2.36 | J/kg | ⚠ Schätzung |
| Leistung | Max. Beinleistung F·l̇ | 24.3 | W/kg | ⚠ Schätzung |
| Energie | Dämpfungsverlust Bein | 88.3 | J | ⚠ Schätzung |
| Energie | Dämpfungsverlust Brett | 31.0 | J | ⚠ Schätzung |
| Energie | Energiebilanz-Abweichung | 0.0000 | % | Berechnet |
| Rotation | Drehimpuls H_y um KSP bei TO | – (ab Level 2) | kg m²/s | n/a |
| Rotation | Rotationspotenzial H_y·t_Flug | – (ab Level 2) | kg m² | n/a |

Erzeugt mit `python -m scripts.report_level1 elite_w_58 7.5`. Status je Wert aus `core/report.py`:
eine Größe ist „Schätzung“, sobald mindestens ein Eingangsparameter Status „Schätzung“ hat
(hier: Bein-/Muskelparameter, Aktivierungs-Timing, Hürdenwerte, Strukturdämpfung).
Nur reine Brettkennwerte bei Fulkrum 7,5 beruhen ausschließlich auf Literaturwerten.
