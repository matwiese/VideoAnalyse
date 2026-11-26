# Modellnotizen und offene Punkte (Etappen 1–3, 5)

Dieses Dokument hält fest, wo die Implementierung Entscheidungen treffen musste, die SPEC.md
nicht eindeutig regelt. Nach CLAUDE.md gilt: bei Widerspruch SPEC.md – die Punkte unten sind
**Rückfragen an die Fachseite**, die aktuell mit einer begründeten, überschreibbaren Wahl gelöst sind.

## 1. Steifigkeit k_s(d) – Widerspruch in den Literaturkonstanten (SPEC 4.2)

`k_s(d) = m_k (d + 0,15) + c_k` mit m_k = 7551 N/m², c_k = 3597 N/m ergibt bei d = 0 nur
**4730 N/m**, die Tabelle nennt **5446 N/m** gemessen „Zehen an der Spitze“. Beides gleichzeitig
geht nicht. Umsetzung (`core/board.py`): Messwert als Achsenabschnitt, Literatur-Steigung:

    k_s(d) = k_s(7,5) + m_k · d

Damit bleibt der überschreibbare Messwert k_s(7,5) die Referenz (wichtig für die eigene
Brettkalibrierung, SPEC 9.3). **Bitte im Original (Kong, Yeadon & King) prüfen**, worauf sich d
bzw. der Offset 0,15 m bezieht (z. B. Ballen statt Zehen).

## 2. Level 1 – Bein-Aktuator und Phasen (SPEC 6.1)

- Passive Beinfeder mit Ruhelänge **l_TD** (KSP-Höhe über Zehen bei TD), damit die Kontaktkraft
  stetig bei 0 beginnt. Aktive Streckung bis **l_max** (voll gestreckt, Ballenstand, Arme hoch).
- Takeoff (F_Bein = 0) wird **erst nach dem tiefsten Punkt** gesucht. Vorher wird kurzzeitiges
  F_roh ≤ 0 (das leichte Brett federt nach dem Aufprall weg) als Kraft 0 bei bestehendem
  Fußkontakt behandelt. Ohne diese Regel „hob“ ein schwerer Springer auf weichem Fulkrum nach
  55 ms ab (Hypothesis-Fund).
- Knicke im Kraftgesetz (Clamp F ≥ 0, Passivfeder an l = l_TD) werden als nicht-terminale
  Ereignisse geortet, RK4 integriert nie über einen Knick. Ergebnis: Energiebilanz ~1e-12.
- Lastfreie Entspannung der Passivfeder während F = 0 wird als Beinverlust gebucht
  (masseloser Fuß).
- Horizontal: v_x konstant (Level 1 hat keine horizontale Kraft), Brettspitze x_b = −c z_b² nur
  kinematisch für Anzeige/Freigang.

## 3. Bekannte Grenze: Level 1 unterschätzt v_z,TO

Mit den Defaults liegt v_z,TO bei ≈ 3,8 m/s (Elite w 58 kg), also **unter v_z,TD** (≈ 4,0 m/s).
Eine Nelder-Mead-Voroptimierung des Aktivierungs-Timings brachte nur ≈ 3,9 m/s. Ursache ist
strukturell: Die Beinkraft ist bei der kleinen effektiven Brettmasse (8,9 kg) praktisch durch
die Brettfeder k_s·|z_b| begrenzt, und das Bein kann im Recoil nicht schnell genug strecken, bevor
das Brett den Springer „abwirft“. Es fehlen Armschwung, Rumpf-/Hüftstreckung und
Segmentdynamik, also genau das, was Level 2 (Etappe 3) liefert. Die App zeigt diesen Hinweis an.
**Kalibrierung der Hürden-/TD-Werte und Kraftparameter aus eigenen Videos (SPEC 9.3/9.4)
ist vor jeder fachlichen Interpretation nötig.**

## 4. Schätzwerte ohne Literaturbasis (Status „Schätzung“)

| Parameter | Default | Begründung |
| --- | --- | --- |
| l_max / l_TD / l_opt (× H) | 0,63 / 0,55 / 0,50 | KSP-Höhe ≈ 0,55·H (de Leva) + Ballenstand + Armhaltung |
| k_Bein | 400 N/m je kg | Größenordnung Landungsstudien |
| c_Bein | 200 N s/m | – |
| F_max | 3,4 BW | lineares F-v-Profil, Größenordnung 30–40 N/kg |
| v0, Γ | 4,0 m/s, 0,5 | nahezu lineares Beinstreck-F-v-Profil |
| Aktivierung | a0 0 → Rampe 0–0,30 s → Abfall ab 0,40 s auf 0,3 | Voroptimierung auf v_z,TO |
| Hürdenhöhe, Brettzustand bei Hürden-Lift-off | 0,75 m; −0,05 m; +0,6 m/s | Platzhalter → Video |
| Restlänge KSP–Fingerspitzen | 0,77·H | Reichhöhe ≈ 1,33·H |
| I_y gestreckt/gehechtet/gehockt | 0,068/0,035/0,018 · M·H² | Größenordnung Yeadon-Modelle (für Level 2) |

SPEC Kap. 8 fordert, Hürden- und TD-Werte **aus eigenen Videoanalysen** zu setzen. Die Defaults
oben sind nur Platzhalter, damit die App ohne Daten startet; sie sind in der UI gelb markiert.

## 5. Abweichungen vom Tech-Stack (SPEC 10.1)

- Diagramme: schlanke eigene SVG-Komponenten statt Plotly/visx (Bundle-Größe, volle Kontrolle
  über das Schwarz-Rot-Design, < 50 ms Reaktionszeit). Heatmap ebenfalls SVG.
- Celery/Redis, PDF-Report, MP4-Export: noch nicht umgesetzt (Etappen 5–7). Parameterstudien
  laufen für Level 1 im Web Worker.
- Python 3.12+ (getestet mit 3.13).

## 6. Level 2 – Modellentscheidungen (Etappe 3)

- **Segmente:** Zehen, Rückfuß, Unterschenkel, Oberschenkel, Rumpf+Kopf (Hals gesperrt),
  Oberarm, Unterarm+Hand – beide Körperhälften in der Sagittalebene zusammengefasst.
  12 Freiheitsgrade (Zehenspitze x/z, Zehenwinkel, 6 Gelenke, 3 Schwabbelmassen) + Brett z_b.
  SPEC 5.2 nennt „ca. 13 + 3 Brett“: Hals (1 FG) und Brett x/φ (2 FG) sind hier nicht frei,
  sondern gesperrt bzw. kinematisch an z_b gekoppelt (x_b = −c z_b², φ_b = κ z_b).
- **Brettneigung:** κ aus der Biegelinie des Kragbalkens, κ = (2L+3a)/(2a(L+a)) ≈ 0,44 rad/m
  bei Fulkrum 7,5 → bei 0,5 m Durchbiegung ≈ 12°. Die Neigung kippt die Normalkraft nach vorn;
  ohne passende Körperhaltung entsteht große Vorwärtsgeschwindigkeit. Schalter
  `contact.board_slope` = none für Vergleiche.
- **Schwabbelmassen:** Punktmasse auf der Segmentachse am Segment-KSP, 1 FG längs der Achse;
  das gesamte Segment-Trägheitsmoment bleibt beim starren Anteil. k_w, c_w werden mit dem
  Verhältnis Schwabbelmasse / Referenz-Schwabbelmasse (Kong et al.) skaliert.
- **Fuß:** de-Leva-Fuß geteilt in Zehen (15 % Masse, Schätzung) und Rückfuß; MTP bei 73 %,
  Sprunggelenk bei 25 % der Fußlänge ab Ferse und 0,039·H über der Sohle (Winter).
- **Kontakt:** Anker (Materialkoordinate entlang des Bretts) wird bei jedem Kontaktbeginn eines
  Punkts neu gesetzt (Event), damit x in F∥ = −k∥ x δ wirklich „seit Kontaktbeginn“ zählt.
- **Haltung bei TD:** Statt des Sprunggelenkwinkels wird die horizontale KSP-Lage relativ zum
  Ballen vorgegeben (`posture.com_offset`, Default −0,08 m); das Sprunggelenk wird daraus
  berechnet. Grund: Die KSP-Lage bestimmt maßgeblich v_x und H_y beim Absprung.
- **Aufprallspitze:** Beim Ballenaufsatz entsteht für ≈ 1 ms eine Kraftspitze (~11 BW), weil
  der Fuß mit ≈ 4,8 m/s Relativgeschwindigkeit auf den steifen Kontakt trifft. Sie wird als
  „Aufprallspitze 0–30 ms“ getrennt vom Hauptmaximum ausgewiesen. Ob sie real so hoch ist, kann
  erst ein Matching an Messdaten zeigen (Etappe 6).
- **Flugphase Level 2:** Haltung ab TO eingefroren, Rotation mit ω = H_y/I(TO); Saltoanzahl
  mit geschätzten Trägheitsmomenten je Haltung (flight.*).

## 7. Validierung SPEC 9.2 (Etappe 5) – Ergebnis

Siehe docs/validation/validation-9-2.md. Kurz: Beugen-dann-Strecken nach TD und längere
Kontaktzeit bei weicherem Fulkrum werden reproduziert; „geringere Knie-Streckgeschwindigkeit
bei Rotationssprüngen“ ebenfalls. **Nicht** echt reproduziert ist das höhere *aktive*
Hüftbeugemoment: Die Rotationslösung erzeugt es über Hüftüberstreckung gegen den passiven
Endanschlag. Ursache vermutlich zu steife/zu enge Hüft-ROM-Grenze (−0,3 rad) und fehlende
Lendenwirbelsäule. **Rückfrage:** gewünschte Hüft-/Rumpf-Extensionsgrenze für Springer:innen?

## 8. Gelenkgrenzen (Rückmeldung Nutzer, Etappe 6)

Vorgabe: „Überstreckung so weit wie im Springen notwendig und realistisch.“ Umsetzung:
Rumpf–Oberschenkel bis −0,7 rad (≈ −40°, Hüfte ≈ 15–20° + LWS ≈ 20–25°), Knie und Ellbogen
bis −5°. Mit der weiteren Grenze kippte der Armschwung den Rumpf auf −54°; realistisch wird das
durch Rumpfstabilisierung verhindert → Hüftbeuger-Default 30 % Ko-Aktivierung (Schätzung).

## 9. Modus B – Modellentscheidungen

- Inverse Dynamik nutzt dieselben SymPy-Gleichungen wie die Vorwärtssimulation, Schwabbelmassen
  starr (nicht messbar). Effekt im synthetischen Test: Brettkraft im Mittelteil bis ~20 % daneben,
  mit starren Schwabbelmassen < 5 % → methodische Grenze, dokumentiert in der Video-Anleitung.
- Resultierende Brettkraft + Druckpunkt auf der Sohle (Zehe–Ballen–Ferse) aus den drei
  Basis-Gleichungen; MTP-Moment wird korrigiert, wenn der Druckpunkt auf dem Rückfuß liegt.
- Filter: Butterworth 2. Ordnung phasenfrei, Residualanalyse (Winter) im Bereich 1–0,3·f_s,
  Regressionsgerade über die obere Hälfte; Ergebnis auf 4–12 Hz begrenzt.
- TD/TO: Abstand Zehe ↔ geneigte Brettoberfläche (κ aus Brettmodell); quadratischer Fit außerhalb
  der Rauschzone (0,6–15 cm), Extrapolation auf 0 → Fehler < 1 Bild bei 200 Hz.
- Startzustand fürs Matching: Polynom-Fit über 80 ms Flugphase vor TD (Winkel), ballistischer
  Fit mit bekanntem g über 150 ms (KSP-Geschwindigkeit); Zehen flach auf dem Brett, MTP gleicht aus.
- Matching-Variablen: T_max der Strecker (MTP, Sprung, Knie, Hüfte) und Schulterflexoren,
  Onsets/Anstiegszeiten, optional Anfangsbedingungs-Offsets (±3°, ±1,5 rad/s) wie bei Kong et al.
