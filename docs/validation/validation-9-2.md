# Validierung SPEC 9.2 – qualitative Plausibilität (Etappe 5)

Preset „Elite w 58 kg“, Level 2, generische (geschätzte) Kraftwerte. Alle Zahlen sind
Modellergebnisse mit Status **Schätzung** – sie zeigen Muster, keine individuellen Prognosen.
Rohdaten: `docs/validation/data/*.json`, Skripte: `scripts/validate_9_2.py`,
`scripts/validate_fulcrum.py`.

## Übersicht

| SPEC 9.2 Aussage | Ergebnis | Bewertung |
| --- | --- | --- |
| v_x bei TD ≈ 0,5 m/s (Miller 2008) | Eingabeparameter (`technique.v_x` = 0,5 m/s) | nicht prüfbar, als Literaturwert gesetzt |
| Gelenke beugen nach TD bis ca. 100 ms, dann Streckung (Miller 1974; Martikkala 1995) | max. Kniebeugung ≈ 120–130 ms nach TD, danach Streckung (automatischer Test) | ✅ reproduziert |
| Weicheres Fulkrum → längere Absprungdauer (Jones & Miller 1996) | Level 1 und Level 2 (optimiert): Kontaktzeit steigt mit Fulkrum, siehe Tabelle | ✅ reproduziert |
| Weicheres Fulkrum → mehr Kniebeugung bei TD, höhere Brett-Abwärtsgeschw. bei TD | TD-Haltung ist Eingabe; ż_b bei TD hängt von der (festen) Hürde und der Brettphase ab | ⚪ nicht prüfbar (Hürdentechnik fest) |
| Rotationssprünge: geringere Knie-Winkelgeschw. bei TO (Cheng & Hubbard 2005) | Knie-Streckgeschw. bei TO: Höhe -0,32 rad/s, Rotation -2,58 rad/s (Knie beugt bereits) | ✅ reproduziert |
| Rotationssprünge: gebeugte Knie bei TO | Kniewinkel bei TO: Höhe -7,6°, Rotation -4,8° | ⚠ Tendenz richtig, Effekt klein |
| Rotationssprünge: mehr Hüftbeugemoment | Aktives Hüftbeugemoment: Höhe 5 Nm, Rotation 12 Nm; passiv (Endanschlag) Rotation 1242 Nm | ❌ nur passiv über Hüftüberstreckung – **nicht** echt reproduziert |
| Fulkrum-Höhe-Beziehung qualitativ (Cheng & Hubbard 2005, J Biomech) | flache Kurve mit Maximum bei mittlerem Fulkrum (Tabelle) | ⚪ offen – Budget zu klein, Vergleich mit Originaldaten fehlt |

## Optimierung Höhe vs. Rotation (CMA-ES, 10 Generationen × 10, Robustheit ±10 ms)

| Kennwert | Ausgang | Optimum Höhe | Optimum Rotation |
| --- | --- | --- | --- |
| h_max über Brett [m] | 1,84 | 2,01 | 1,20 |
| v_z,TO [m/s] | 4,08 | 4,35 | 2,46 |
| H_y [kg m²/s] (+ vorwärts) | 5,5 | -22,1 | 35,0 |
| Rotationspotenzial [kg m²] | 7,0 | -29,1 | 35,9 |
| Freigang Körper [m] | 0,55 | 0,59 | 1,47 |
| Kontaktzeit [s] | 0,415 | 0,422 | 0,433 |

Beobachtungen:
- Das Höhen-Optimum erzeugt **Rückwärts**-Drehimpuls (H_y < 0). Für Vorwärtssprünge braucht die
  Optimierung eine Nebenbedingung H_y ≥ H_min (Erweiterung für Etappe 5b).
- Rotation kostet Höhe (≈ −0,6 m) – qualitativ wie in der Literatur (Zielkonflikt).
- Die Rotationslösung überstreckt die Hüfte auf ≈ −30° und nutzt den passiven Endanschlag. Das
  ist ein Modellartefakt der Hüft-ROM-Grenze (−0,3 rad) bzw. der fehlenden Lendenwirbelsäule.

## Fulkrum-Stellung → max. Flughöhe

| Fulkrum | Level 1 h_max [m] | Level 2, Timing fest [m] | Level 2, Timing je Fulkrum optimiert [m] | Kontaktzeit L2 opt. [s] |
| --- | --- | --- | --- | --- |
| 1,0 | 1,77 | 0,38 | 1,80 | 0,334 |
| 3,0 | 1,81 | 0,82 | 1,85 | 0,347 |
| 5,0 | 1,81 | 1,94 | 1,94 | 0,395 |
| 7,5 | 1,73 | 1,84 | 1,84 | 0,415 |
| 9,0 | 1,72 | 1,53 | 1,85 | 0,430 |

- Mit **fester** (auf 7,5 abgestimmter) Technik bricht Level 2 bei steifem Brett ein – realistisch:
  Springer:innen passen Timing und Hürde an. Faire Aussagen nur mit Optimierung je Einstellung.
- Optimiert (6 Generationen × 8, ohne Robustheit) liegt h_max zwischen 1,80 und 1,94 m; bei 7,5
  fand dieses kleine Budget keine Verbesserung (der längere Lauf oben erreichte 2,01 m). Die
  Unterschiede liegen damit im Bereich der Optimierungsunsicherheit.
- Die Hürde ist fest; mit dem Fulkrum ändert sich die Brett-Phasenlage bei TD und damit die
  Energieeinbringung (SPEC Kap. 2). Für eine belastbare Fulkrum-Kurve: Hürdenparameter mit
  optimieren und eigene Hürdendaten aus Video einsetzen.
