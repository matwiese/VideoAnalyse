# Spezifikation: 3D-Biomechanik-Simulator Anlauf & Absprung 3m-Brett

Nov 26, 2026 · @Mathias

## 1. Ziel und Scope

Gebaut wird ein webbasierter Simulator, der den Anlauf, die Hürde und den Brettkontakt beim 3m-Kunstspringen als gekoppeltes Springer-Brett-System berechnet und in 3D darstellt. Aus Körpergröße, Körpermasse, Kraftparametern, Fulkrum-Einstellung und Technikvariablen errechnet er alle Kräfte, Geschwindigkeiten, Höhen, Energien und Drehimpulse bis zum Eintauchen.

Das Dokument ist das vollständige Lastenheft für Claude Code: Modellphysik, Parameter mit Quellen, Formeln, Architektur, Tests und fertige Prompts. Lege es als `SPEC.md` ins Repository und verweise in `CLAUDE.md` darauf (Kapitel 11).

**Drei Arbeitsmodi**

- **A – Vorwärtssimulation (prädiktiv):** Eingaben → Simulation → Absprungbedingungen und Flugbahn. Optional Optimierung der Aktivierungs-Timings auf maximale Höhe oder maximales Rotationspotenzial.
- **B – Inverse Dynamik (Analyse realer Sprünge):** Import gemessener Kinematik (Video-Tracking, z. B. Kinovea, Simi, OpenCap, IMU) → Brettkraft, Gelenkmomente, Leistung, Energiefluss.
- **C – Parameterstudien:** Sweeps über Fulkrum, Masse, Größe, Kraft, Touchdown-Geschwindigkeit → Heatmaps und Sensitivitäten.

**Nicht im Scope (Version 1):** Wassereintritt und Unterwasserphase, Ermüdung, Muskel-Sehnen-Modelle auf Einzelmuskelebene (Hill-Typ pro Muskel), Turm (10 m).

**Wissenschaftlicher Anspruch:** Jede Modellannahme ist mit Quelle oder als Kalibrierparameter gekennzeichnet. Die App zeigt zu jedem Ergebnis, aus welchem Modell-Level es stammt und welche Parameter Literaturwerte bzw. Schätzwerte sind.

## 2. Phasenmodell: vom Anlauf bis zum Eintauchen

Die Simulation läuft als Zustandsautomat mit sieben Phasen; jede Phase hat eigene aktive Kontaktkräfte und eindeutige Ereignis-Detektoren. Der wichtigste Leistungsprädiktor ist die vertikale Touchdown-Geschwindigkeit aus der Hürde: Sie erklärte in einer 3m-Studie rund 43 % der Varianz der Sprunghöhe (Walker et al., Movement & Sport Sciences 2012).

| # | Phase | Startereignis | Aktive Kräfte / Modelle | Zentrale Ausgaben |
| --- | --- | --- | --- | --- |
| P1 | Anlauf (3–5 Schritte) | Start | Gangmodell (vorgegebene Schrittlänge/-frequenz), Brett als Masse-Feder unter jedem Fußaufsatz | Anlaufgeschwindigkeit, Brettanregung vor der Hürde |
| P2 | Hürdenabsprung (letzter Schritt) | Aufsatz Sprungbein | Einbeinkontakt, Kniehub Schwungbein, Armschwung; Brett-Kopplung | Absprunggeschwindigkeit Hürde, Brettamplitude bei Lift-off |
| P3 | Hürdenflug | Lift-off Sprungbein | Ballistischer KSP; Brett schwingt frei (gedämpfte Eigenschwingung mit m\_eff) | Hürdenhöhe, Flugzeit, Brettphase bei Touchdown, v\_z,TD |
| P4 | Touchdown / Depression | Fuß-Brett-Kontakt beidbeinig | Gekoppeltes Springer-Brett-System, Fußkontakt-Federn, Gelenkmomente, Armschwung | Max. Brettdurchbiegung, Spitzenkraft, gespeicherte Energie |
| P5 | Recoil | Brettgeschwindigkeit = 0 (tiefster Punkt) | wie P4; Brett gibt Energie zurück | Brettenergie → Springer, Gelenkleistung |
| P6 | Takeoff | F\_Kontakt = 0 bzw. Fuß verlässt Brett | Kontaktverlust | v\_KSP (3D), Drehimpuls H (3D), Absprungwinkel |
| P7 | Flug bis Wasser | Takeoff | Ballistik + Drehimpulserhaltung; Brettfreigang | Max. Höhe, Flugzeit, Abstand zum Brett, Eintauchzeitpunkt |

**Ereignisdetektion:** Nulldurchgangssuche (Event-Funktionen) im Integrator, nicht per Zeitraster. Touchdown, tiefster Punkt (ż\_Brett = 0), Takeoff (Normalkraft = 0 und Fußabstand > 0) und Wasser (z\_KSP = –3,0 m + Restlänge) werden auf < 0,1 ms genau lokalisiert.

**Warum P3 wichtig ist:** Das Brett schwingt nach dem Hürdenabsprung weiter. Trifft der Springer das Brett, während es nach oben schwingt, steigt die Relativgeschwindigkeit und damit die eingetragene Energie; trifft er es abwärts schwingend, geht Energie verloren. Das Modell muss diese Phasenlage explizit ausgeben (Jones & Miller untersuchten genau diese Brettoszillation während des Hürdenflugs an 3m-Finalisten).

## 3. Koordinatensystem, Konventionen, Einheiten

Alle Berechnungen laufen in SI-Einheiten in einem rechtshändigen Inertialsystem mit Ursprung an der unbelasteten Brettspitze (Oberseite, Brettmitte).

- **x** – entlang der Brettlängsachse, positiv Richtung Wasser (anterior beim Vorwärtsanlauf)
- **y** – lateral, positiv nach links (aus Sicht des Springers)
- **z** – vertikal, positiv nach oben; Wasseroberfläche bei z = –3,00 m
- **Drehachsen:** H\_y = Salto-Achse (Somersault), H\_x = Kippachse (Tilt/Cartwheel), H\_z = Längsachse (Schraube/Twist)
- **Gelenkwinkel:** anatomische Nullstellung = 0°, Flexion positiv; Sprunggelenk Dorsalflexion positiv
- **Segment-Orientierung (3D):** Rotationsmatrizen bzw. Quaternionen intern; Ausgabe als Kardanwinkel (Reihenfolge Salto – Kippen – Schraube nach Yeadon 1990) zur Vermeidung von Gimbal-Lock bei Saltos
- **Gravitation:** g = 9,81 m/s² (konfigurierbar, Default 9,81)
- **Zeit:** t = 0 beim Touchdown (P4); negative Zeiten für Anlauf und Hürde
- **Kräfte:** Kraft des Bretts auf den Springer positiv nach oben; zusätzlich normiert auf Körpergewicht (BW) ausgeben

**3D-Logik:** Der Absprung ist primär sagittal. Die dritte Dimension wird für laterale Abweichung (Fußasymmetrie, Armschwung-Asymmetrie), Kipp-Drehimpuls und Schraubeninitiierung vom Brett sowie für die Visualisierung benötigt. Level 2 rechnet planar, Level 3 voll räumlich (Kapitel 6).

## 4. Sprungbrettmodell (Duraflex Maxiflex Model B)

Das Brett wird als ungedämpftes Masse-Feder-System mit lastort- und fulkrumabhängiger Steifigkeit modelliert und um horizontale und rotatorische Bewegung der Spitze erweitert. Das lineare Masse-Feder-Modell nach Sprigings, Stilling & Watson (1989) ist in der Literatur der allgemein akzeptierte Standard; Kong, Yeadon & King erweiterten es um horizontale Auslenkung und Rotation.

### 4.1 Geometrie und Einstellbereich

| Größe | Wert | Quelle / Status |
| --- | --- | --- |
| Länge × Breite | 4,88 m × 0,495 m | [Duraflex/Malmsten Datenblatt](https://www.klubben.no/media/multicase/documents/1123018_duraflex_maxifles_model%20b%20diving%20board.pdf) |
| Masse | 63 kg | Datenblatt |
| Bauform | Doppelt verjüngt (Fulkrum→Spitze und Fulkrum→Anker), 189 Schlitze an der Spitze | Datenblatt |
| Fulkrum-Verstellweg | ca. 0,61 m | [Wikipedia: Springboard](https://en.wikipedia.org/wiki/Springboard) |
| Fulkrum-Skala | 1 (steif) bis 9 (weich), ca. 0,075 m pro Stufe, ca. 300 N/m Steifigkeitsänderung pro Stufe | [ISB 2011 Abstract](https://isbweb.org/images/conf/2011/ScientificProgram/ISB2011_ScientificProgram_files/794.pdf) |
| Höhe über Wasser | 3,00 m | FINA/World Aquatics |

Die Maxiflex B ist deutlich weicher als die ältere Duraflex und hat ein größeres effektives Massenverhältnis; die Perforation senkt die lokale Steifigkeit im Spitzenbereich um zusätzlich rund 10 % ([Dorotich et al., 1990](https://katalog.lib.cas.cz/KNAV/EdsRecord/edsair,edsair.doi...........8bae0ce6c5c6c28bda0e08cb5c8ff98a)).

### 4.2 Vertikales Modell (Level 1 und 2)

Brettspitze als effektive Masse m\_b an einer linearen Feder, gekoppelt über die Kontaktkraft F\_c mit dem Springer:

```latex
m_b \, \ddot{z}_b = -k_s(d, F) \, z_b - F_c
```

Steifigkeit in Abhängigkeit vom Abstand d der Zehen zur Brettspitze (Sprigings et al., 1989; Kalibrierung nach Kong/Yeadon/King):

```latex
k_s(d) = m_k \,(d + 0{,}15) + c_k
```

| Parameter | Wert bei Fulkrum 7,5 | Quelle |
| --- | --- | --- |
| Effektive Masse m\_b | 8,87 kg | [Kong, Yeadon & King (Loughborough)](https://core.ac.uk/download/288388973.pdf) |
| Gemessene Steifigkeit, Zehen an der Spitze | 5446 N/m | ebd. |
| m\_k (Steigung) | 7551 N/m² | ebd. (Matching-Konstanten) |
| c\_k (Achsenabschnitt) | 3597 N/m | ebd. |
| Dämpfung | keine (0) | ebd. |

**Gravitationsoffset:** Die statische Durchbiegung durch das Eigengewicht ist im Nullpunkt enthalten; z\_b = 0 entspricht dem unbelasteten Ruhezustand. Deshalb enthält die Gleichung keinen Term m\_b g; F\_c ist die volle Kontaktkraft aus den Fußfedern. Ein Test prüft, dass das leere Brett in Ruhe bei z\_b = 0 bleibt.

### 4.3 Fulkrum-Abhängigkeit

Die Literaturwerte gelten für Fulkrum 7,5. Für andere Stellungen bietet die App zwei Varianten an:

**Variante A – empirisch linear (Default):**

```latex
k_s(F) = k_s(7{,}5) + \Delta k \,(7{,}5 - F), \quad \Delta k \approx 300\ \mathrm{N/m}
```

**Variante B – Balkentheorie mit Kalibrierung:** Brett als Kragbalken mit Lager am Anker und Auflager am Fulkrum. Mit Spannweite L\_s (Anker–Fulkrum) und Überhang a (Fulkrum–Lastpunkt) gilt für einen prismatischen Balken:

```latex
k(a, L_s) = \frac{3\,EI_{\mathrm{eff}}}{a^2 \,(L_s + a)}
```

EI\_eff wird so kalibriert, dass k bei Fulkrum 7,5 und d = 0 dem Messwert entspricht. Die Verjüngung steckt damit pauschal in EI\_eff. Prüfrechnung: Mit L\_s ≈ 1,88 m und a ≈ 3,0 m ändert eine Stufe von 0,075 m die Steifigkeit um rund 5 %, also etwa 250–300 N/m – konsistent mit Variante A.

**Effektive Masse:** steigt bei weicherem Fulkrum (Miller et al., 1998). Default: m\_b(F) = 8,87 kg · \[k\_s(7,5) / k\_s(F)\]^0,5 als Platzhalter, klar als Schätzung markiert und überschreibbar. Beste Lösung: eigene Messung (Kapitel 9.3).

### 4.4 Horizontale und rotatorische Bewegung (Level 2 und 3)

Die Spitze bewegt sich auf einer Kurvenbahn; daraus entsteht eine horizontale Reaktionskraft, die für Drehimpuls und Brettfreigang wichtig ist. Kong et al. (ISBS 2004) fanden empirisch:

```latex
x_b = -0{,}194 \, z_b^2 , \qquad \varphi_b = f(z_b)\ \text{(Regression, kubisch)}
```

Die Spitze wird als 0,3 m langer Stab mit drei Freiheitsgraden (z, x, φ) und Trägheitsmoment eines homogenen Stabs modelliert. Achtung: Diese Regression stammt aus 1m-Daten und muss für 3m als Kalibrierparameter geführt werden. Physikalische Alternative für Variante B: Neigungswinkel aus der Biegelinie des Kragbalkens.

### 4.5 Freie Brettschwingung (Hürdenflug P3)

Ohne Springer schwingt das Brett mit der Eigenkreisfrequenz ω\_0 = √(k\_s/m\_b). Mit kleiner Strukturdämpfung ζ (Default 0,02, Kalibrierparameter) verhindert das Modell unrealistisch ewiges Nachschwingen. Mit Springer sinkt die Frequenz auf etwa √(k\_s/(m\_b + m\_Springer)) – die App zeigt beide Werte an.

## 5. Athletenmodell

Der Springer ist ein drehmomentgetriebenes Mehrkörpersystem, dessen Segmentparameter aus Körpergröße, Körpermasse und Geschlecht skaliert und optional individuell überschrieben werden. Das Referenzmodell der Literatur ist ein planares 8-Segment-Modell (Kopf, Oberarm, Unterarm, Rumpf, Oberschenkel, Unterschenkel, zweiteiliger Fuß) mit Schwabbelmassen in Rumpf, Oberschenkel und Unterschenkel ([Kong, Yeadon & King](https://core.ac.uk/download/288388973.pdf)).

### 5.1 Anthropometrie

- **Default:** Segmentmassen, Schwerpunktlagen und Trägheitsradien nach de Leva (1996, J Biomech 29:1223–1230), getrennte Tabellen für Frauen und Männer. Claude Code implementiert die vollständige Tabelle aus dem Originalpaper als JSON-Datei mit Quellenangabe.
- **Segmentlängen:** proportional zur Körpergröße H (Winter-Proportionen) oder direkt eingegeben (Maßband bzw. Video).
- **Individuell (empfohlen für Kaderathlet:innen):** Yeadon-Geometriemodell (1990) aus ca. 95 anthropometrischen Maßen → Segmentmassen und Trägheitstensoren in 3D. Import als CSV.

Orientierung de Leva, Massenanteile in % der Körpermasse (vor Implementierung gegen das Original prüfen):

| Segment | Frauen % | Männer % |
| --- | --- | --- |
| Kopf + Hals | 6,68 | 6,94 |
| Rumpf | 42,57 | 43,46 |
| Oberarm | 2,55 | 2,71 |
| Unterarm | 1,38 | 1,62 |
| Hand | 0,56 | 0,61 |
| Oberschenkel | 14,78 | 14,16 |
| Unterschenkel | 4,81 | 4,33 |
| Fuß | 1,29 | 1,37 |

### 5.2 Segmentierung je Modell-Level

| Level | Segmente | Freiheitsgrade | Zweck |
| --- | --- | --- | --- |
| 1 | Punktmasse + aktives Bein (Feder-Dämpfer-Aktuator) | 1 (vertikal) + Brett | Echtzeit-Slider, Grundverständnis |
| 2 | 8 Segmente planar (Fuß 2-teilig, Unterschenkel, Oberschenkel, Rumpf, Kopf, Oberarm, Unterarm) + 3 Schwabbelmassen | ca. 13 + 3 Brett | Wissenschaftlicher Standard, Absprungoptimierung |
| 3 | 15 Segmente räumlich (bilateral Extremitäten) | ca. 40 + 3 Brett | 3D-Asymmetrien, Kipp- und Schraubendrehimpuls |

### 5.3 Muskel-Drehmoment-Generatoren

Jedes aktive Gelenk (MTP, Sprunggelenk, Knie, Hüfte, Schulter, Ellbogen) hat je einen Extensor- und Flexor-Generator:

```latex
T(t) = a(t)\, T_{\max}\, f(\theta)\, h(\omega)
```

- **Aktivierung a(t) ∈ \[0, 1\]:** stetige Rampen mit Onset-Zeit, Anstiegszeit und Plateau (z. B. quintische Polynome), Anstiegsgeschwindigkeit begrenzt (Cheng & Hubbard 2005: Aktivierung fällt beim nachgiebigen Untergrund vor dem Takeoff ab, anders als beim festen Boden).
- **Kraft-Länge f(θ):** quadratische Funktion um den optimalen Gelenkwinkel.
- **Kraft-Geschwindigkeit h(ω):** konzentrisch nach Selbie & Caldwell (1996), exzentrisch mit Plateau 1,4–1,8 · T\_max (Yeadon, King & Wilson 2006, 9-Parameter-Modell):

```latex
h(\omega) = \frac{\omega_0 - \omega}{\omega_0 + \Gamma \omega} \quad (0 \le \omega < \omega_0)
```

- **Default-Kraftwerte:** Literatur-Orientierung für trainierte Springer:innen als Startwerte, klar als „Schätzung“ markiert. Subjektspezifisch per isokinetischer Dynamometrie bestimmen (Kong et al. zeigten, dass generische Werte die Matching-Qualität deutlich verschlechtern).
- **Passive Gelenkmomente:** exponentielle Endanschläge an den ROM-Grenzen, damit keine anatomisch unmöglichen Winkel entstehen.

### 5.4 Fuß-Brett-Kontakt

Zehen-, Ballen- und Fersenpunkt erhalten je ein Paar nichtlinearer, gedämpfter Federn (senkrecht und parallel zur Brettoberfläche). Werte aus Kong et al., gleich für alle drei Punkte:

```latex
F_\perp = -k_\perp z - c_\perp z \dot{z}, \qquad F_\parallel = -k_\parallel x z - c_\parallel z \dot{x}
```

| Parameter | Wert |
| --- | --- |
| k\_⊥ | 0,26 · 10⁶ N/m |
| c\_⊥ | 0,73 · 10⁶ N s/m² |
| k\_∥ | 87,9 · 10⁶ N/m² |
| c\_∥ | 11,1 · 10⁶ N s/m³ |

z ist hier die Eindringtiefe (> 0 nur bei Kontakt), x die tangentiale Verschiebung seit Kontaktbeginn. Die Federn sind steif → kleine Zeitschritte oder impliziter Integrator (Kapitel 6).

### 5.5 Schwabbelmassen (Wobbling Masses)

Weichteile in Rumpf, Oberschenkel und Unterschenkel werden als zweite Masse elastisch an den starren Knochenanteil gekoppelt (kubische Feder + Dämpfer). Das dämpft Kraftspitzen beim Touchdown realistisch.

```latex
F_w = -k_w x_w^3 - c_w v_w
```

| Segment | Schwabbelmasse (kg) | Feste Masse (kg) | k\_w (N/m³) | c\_w (N s/m) |
| --- | --- | --- | --- | --- |
| Unterschenkel | 6,03 | 2,10 | 1718 · 10⁶ | 148 |
| Oberschenkel | 16,74 | 2,14 | 691 · 10⁶ | 117 |
| Rumpf | 21,86 | 3,96 | 101 · 10⁶ | 76 |

Die Massen gelten für den untersuchten Elite-Springer; die App skaliert sie über das Verhältnis Schwabbel- zu Gesamtsegmentmasse auf die eingegebene Körpermasse.

## 6. Bewegungsgleichungen und Numerik

Die App rechnet drei aufeinander aufbauende Modell-Levels; jedes Level wird gegen das vorige und gegen analytische Fälle getestet, bevor das nächste gebaut wird.

### 6.1 Level 1 – Zwei-Massen-Modell (Echtzeit im Browser)

KSP-Masse M auf einem aktiven Bein (Länge l = z\_c – z\_b), Brettmasse m\_b auf der Brettfeder. Koordinaten relativ zur statischen Ruhelage:

```latex
M \ddot{z}_c = F_{\mathrm{Bein}} - M g
```

```latex
m_b \ddot{z}_b = -k_s z_b - F_{\mathrm{Bein}}
```

```latex
F_{\mathrm{Bein}} = \max\!\big(0,\; k_l (l_0 - l) - c_l \dot{l} + a(t)\, F_{\max}\, h(\dot{l})\big)
```

k\_l und c\_l beschreiben die passive Beinsteifigkeit, der aktive Term die Streckkraft. Takeoff, wenn F\_Bein = 0 und l ≥ l\_0. Optional: Arme als zweite Punktmasse mit vorgegebenem Schwungprofil (Armschwung erhöht die Brettbelastung in der Depression).

### 6.2 Level 2 – Planares Mehrkörpermodell

```latex
\mathbf{M}(\mathbf{q})\,\ddot{\mathbf{q}} + \mathbf{C}(\mathbf{q},\dot{\mathbf{q}})\,\dot{\mathbf{q}} + \mathbf{G}(\mathbf{q}) = \boldsymbol{\tau}_{\mathrm{Muskel}} + \boldsymbol{\tau}_{\mathrm{passiv}} + \mathbf{J}^{T}(\mathbf{q})\,\mathbf{F}_{\mathrm{Kontakt}}
```

- **Herleitung:** symbolisch mit SymPy (`sympy.physics.mechanics`, Kane-Methode), Code-Generierung nach NumPy/C. Nie von Hand abtippen.
- **Generalisierte Koordinaten:** KSP-Position (x, z) bzw. Fußposition, Rumpfwinkel, relative Gelenkwinkel, Schwabbelmassen-Verschiebungen, Brett (z\_b, x\_b, φ\_b).

### 6.3 Level 3 – Räumliches Modell

- Featherstone Articulated-Body-Algorithm mit räumlicher Vektoralgebra, Segment-Orientierung als Quaternion. Bibliothek: Pinocchio (Python) oder eigene getestete Implementierung.
- Kontaktkräfte wie Level 2, aber pro Fuß getrennt (links/rechts) und zusätzlich lateral (y) → Asymmetrien erzeugen Kipp- und Schraubendrehimpuls.

### 6.4 Integration

| Modell | Integrator | Schrittweite / Toleranz |
| --- | --- | --- |
| Level 1 (Browser) | RK4, fest | 0,1 ms |
| Level 2/3 (Backend) | `solve_ivp` Radau oder LSODA mit Event-Funktionen | rtol 1e-8, atol 1e-10, max. Schritt 0,5 ms |
| Flugphase | analytisch (Parabel + Drehimpulserhaltung) bzw. Euler-Gleichungen für Mehrkörper-Flug | – |

Die Fußkontaktfedern machen das System steif; deshalb implizite Integratoren im Backend. Jede Ausgabe wird auf 1 kHz resampelt.

### 6.5 Flugphase (analytisch)

```latex
z(t) = z_{TO} + v_{z,TO}\, t - \tfrac{1}{2} g t^2, \qquad h_{\max} = z_{TO} + \frac{v_{z,TO}^2}{2g}
```

```latex
t_{\mathrm{Wasser}} = \frac{v_{z,TO} + \sqrt{v_{z,TO}^2 + 2 g\,(z_{TO} - z_{\mathrm{Wasser}})}}{g}
```

Der Drehimpuls um den KSP bleibt im Flug konstant; die Winkelgeschwindigkeit ändert sich mit dem Trägheitsmoment (gestreckt, gehechtet, gehockt). Rotationspotenzial = H\_y · t\_Flug (Maß aus Kong et al. und Sayyah et al.).

### 6.6 Optimierung (Modus A)

- **Variablen:** Onset, Anstiegszeit, Plateau-Level je Aktivierung (ca. 4 pro Generator).
- **Zielfunktionen:** max. h\_max; max. Rotationspotenzial; gewichtete Kombination; Mindest-Brettfreigang als Nebenbedingung.
- **Verfahren:** Simulated Annealing (Standard der Loughborough-Gruppe) oder CMA-ES; parallelisiert.
- **Robustheit:** Kong, Yeadon & King (ISBS 2006) zeigten, dass anatomische Constraints und Robustheit gegen Timing-Störungen die Optimierung realistisch halten. Umsetzung: Lösung wird mit ±10 ms Störung je Onset neu simuliert, Leistungsverlust fließt als Strafterm ein.

### 6.7 Matching an reale Sprünge (Modus B)

Score = gewichtetes RMS der prozentualen Abweichung zwischen Simulation und Messung in Gelenkwinkeln, Orientierung, linearem Impuls, Drehimpuls und Kontaktdauer (Methode Kong/Yeadon/King). Daraus werden subjektspezifische Kraft- und Brettparameter geschätzt.

## 7. Ausgabegrößen

Jede Größe gibt es als Zeitverlauf (1 kHz) und als Kennwert an den Ereignissen Touchdown (TD), tiefster Punkt (LP) und Takeoff (TO); Kräfte zusätzlich in BW, Leistungen zusätzlich in W/kg.

| Kategorie | Größe | Einheit | Berechnung |
| --- | --- | --- | --- |
| Kräfte | Brett-Reaktionskraft F\_z, F\_x, F\_y (Verlauf, Peak, Mittelwert) | N, BW | Summe der Fußkontaktkräfte |
| Kräfte | Kraftanstiegsrate (RFD) nach TD | N/s | dF/dt, Maximum in 0–50 ms |
| Kräfte | Brett-Federkraft k\_s · z\_b | N | Brettmodell |
| Kräfte | Gelenkreaktionskräfte MTP, Sprunggelenk, Knie, Hüfte | N, BW | Inverse Dynamik |
| Momente | Gelenkmomente (aktiv, passiv, netto) | Nm, Nm/kg | Generatoren bzw. inverse Dynamik |
| Impuls | Vertikaler und horizontaler Kraftstoß (Depression / Recoil getrennt) | N s | ∫ F dt |
| Geschwindigkeiten | KSP v\_x, v\_y, v\_z bei TD, LP, TO | m/s | Kinematik |
| Geschwindigkeiten | Brettspitze ż\_b (max. abwärts, bei TO) | m/s | Brettmodell |
| Geschwindigkeiten | Gelenkwinkelgeschwindigkeiten, Segmentwinkelgeschwindigkeiten | rad/s, °/s | Kinematik |
| Höhen / Wege | Hürdenhöhe, max. Brettdurchbiegung, KSP-Höhe bei TO, max. Flughöhe über Brett und über Wasser | m | Kapitel 6.5 |
| Höhen / Wege | Horizontaler Abstand zum Brett beim Passieren der Brettebene (Freigang) | m | Flugbahn + Segmentgeometrie |
| Zeiten | Hürdenflugzeit, Depressions-, Recoil-, Kontaktzeit, Flugzeit bis Wasser | s | Events |
| Energie | Kinetisch (Translation + Rotation), potenziell, Brett-Federenergie ½ k\_s z\_b², Gesamtbilanz | J | Zustand |
| Energie | Energieübertrag Springer → Brett (Depression) und Brett → Springer (Recoil), Wirkungsgrad | J, % | Leistungsintegrale |
| Leistung | Gelenkleistung T · ω je Gelenk, positive/negative Arbeit | W, J | Generatoren |
| Rotation | Drehimpuls H um KSP (H\_x, H\_y, H\_z) bei TO; Beitrag je Segment | kg m²/s | Σ (r × m v + I ω) |
| Rotation | Rotationspotenzial H\_y · t\_Flug, mögliche Saltoanzahl je Körperhaltung | –, Umdrehungen | Kapitel 6.5 |
| Brett | Eigenfrequenz leer und belastet, Phasenlage bei TD | Hz, ° | Kapitel 4.5 |

**Energiebilanz als Pflicht-Ausgabe:** Jede Simulation zeigt eine Bilanz (Muskelarbeit + Anfangsenergie = Endenergie + Dämpfungsverluste). Abweichung > 0,5 % wird als Warnung angezeigt – das ist der wichtigste Selbsttest des Modells.

## 8. Eingabeparameter

Alle Parameter stehen in einer typisierten Konfiguration (Pydantic im Backend, Zod im Frontend) mit Default, Bereich, Einheit und Status „Literatur“, „Schätzung“ oder „Gemessen“. Schätzwerte sind in der UI farblich markiert.

| Gruppe | Parameter | Default | Bereich | Status |
| --- | --- | --- | --- | --- |
| Athlet:in | Körpergröße | 1,70 m | 1,30–2,05 m | Eingabe |
| Athlet:in | Körpermasse | 62 kg | 30–110 kg | Eingabe |
| Athlet:in | Geschlecht (Anthropometrie-Tabelle) | w | w / m | Eingabe |
| Athlet:in | Individuelle Segmentlängen / Yeadon-Maße | aus Größe skaliert | – | optional gemessen |
| Kraft | T\_max je Gelenk und Richtung | generisch | 0,5–2,0 × Default | Schätzung → Dynamometrie |
| Kraft | ω\_0, Γ, exzentrischer Faktor | generisch | – | Schätzung |
| Brett | Fulkrum-Stellung | 7,5 | 1–9 (0,5er-Schritte) | Eingabe |
| Brett | k\_s(7,5), m\_b(7,5) | 5446 N/m, 8,87 kg | ±50 % | Literatur → eigene Messung |
| Brett | Fulkrum-Modell | Variante A | A / B | Auswahl |
| Brett | Strukturdämpfung ζ | 0,02 | 0–0,1 | Schätzung |
| Brett | Horizontal-Koeffizient (x\_b = –c z\_b²) | 0,194 1/m | 0–0,5 | Literatur (1m) |
| Technik | Anlaufschritte | 3 | 3–5 | Eingabe |
| Technik | Anlaufgeschwindigkeit | Schätzwert | einstellbar | Schätzung → Video |
| Technik | Fußposition: Abstand Zehen–Spitze bei TD | 0,05 m | 0–0,30 m | Eingabe |
| Technik | Touchdown-Geschwindigkeit v\_z,TD (bei direktem Start in P4) | Schätzwert | einstellbar | Schätzung → Video |
| Technik | Gelenkwinkel bei TD (Sprung-, Knie-, Hüftgelenk, Schulter) | Literatur-Mittel | ROM | Eingabe |
| Technik | Armschwung: Start relativ TD, Amplitude | Profil | – | Eingabe |
| Technik | Aktivierungs-Timing je Generator | optimiert | – | Optimierung oder Eingabe |
| Technik | Sprungart | Vorwärts | Vorwärts / Rückwärts / Auerbach / Delfin / Schraube | Auswahl (Level 2/3) |
| 3D | Fuß-Asymmetrie (Kraftanteil links/rechts, Versatz) | 50/50, 0 m | 40/60, ±0,05 m | Eingabe (Level 3) |
| 3D | Arm-Asymmetrie, Rumpfrotation bei TO | 0 | – | Eingabe (Level 3) |
| Numerik | Modell-Level, Integrator, Toleranzen | Level 2, Radau | – | Experten-Panel |

Hürden- und Touchdown-Werte sind bewusst ohne festen Default-Zahlenwert angegeben: Claude Code soll sie aus deinen eigenen Videoanalysen setzen (Kapitel 9.3), nicht aus Schätzungen.

**Presets:** „Jugend w 45 kg“, „Elite w 58 kg“, „Elite m 70 kg“, „Schwer m 85 kg“ plus beliebig viele gespeicherte Athletenprofile (JSON-Export/-Import).

## 9. Validierung und Kalibrierung

Das Modell gilt erst als einsatzbereit, wenn es alle analytischen Tests besteht und an mindestens fünf eigenen, gefilmten 3m-Sprüngen mit einer RMS-Abweichung unter 10 % gematcht wurde.

### 9.1 Automatisierte Tests (pytest, CI)

1. **Freie Brettschwingung:** Frequenz = √(k/m\_b)/2π auf 0,1 % genau.
2. **Passiver Springer auf Brett (keine Muskeln, keine Dämpfung):** Gesamtenergie konstant auf 1e-6 relativ.
3. **Level 1 vs. analytische Lösung** des gekoppelten Zwei-Massen-Schwingers.
4. **Level 2 auf Level 1 reduziert** (alle Gelenke gesperrt) → identische Ergebnisse.
5. **Flugphase:** Drehimpuls um KSP konstant auf 1e-9; KSP-Bahn exakt parabolisch.
6. **Symmetrie:** Level 3 mit symmetrischen Eingaben liefert H\_x = H\_z = 0 und y = 0.
7. **Skalierung:** doppelte Masse bei gleicher Steifigkeit → Eigenfrequenz × 1/√2.
8. **Konvergenz:** halbierte Schrittweite ändert v\_z,TO um < 0,1 %.

### 9.2 Plausibilitätsprüfung gegen Literatur

- Horizontale KSP-Geschwindigkeit bei TD um 0,5 m/s (Greg Louganis, 3m-Vorwärtsabsprunge; Miller 2008).
- Nach TD flektieren Sprung-, Knie- und Hüftgelenk noch bis zu ca. 100 ms, dann folgt kräftige Streckung während der Depression (Miller 1974; Martikkala et al. 1995).
- Weicheres Fulkrum → längere Absprungdauer, mehr Kniebeugung bei TD, höhere Brettgeschwindigkeit abwärts bei TD (Jones & Miller 1996).
- Optimierte Simulationen sollen das bekannte Muster reproduzieren: Rotationssprünge haben geringere Kniewinkelgeschwindigkeit und gebäugte Knie bei TO, mehr Hüftbeugemoment (Cheng & Hubbard 2005, ISBS).
- Die Fulkrum-Höhen-Beziehung aus Experimenten muss qualitativ vorhergesagt werden (Cheng & Hubbard 2005, J Biomech).

### 9.3 Eigene Brettkalibrierung (empfohlen)

Die Literaturwerte stammen von einzelnen Brettern und Fulkrum-Stellungen. Für deine Anlage misst du so:

1. **Statisch:** Gewichte (z. B. 20/40/60 kg) an der Spitze, Durchbiegung per Video (≥ 240 fps, Maßstab) oder Laser → k\_s als Steigung der Kraft-Weg-Geraden. Für Fulkrum 1, 3, 5, 7, 9 und Lastorte d = 0 / 0,15 / 0,30 m.
2. **Dynamisch (Methode nach Miller & Jones):** Brett mit bekannter Zusatzmasse m\_add anschwingen, Frequenz messen. Aus zwei Massen folgen k\_s und m\_b:

```latex
\omega_i^2 = \frac{k_s}{m_b + m_{\mathrm{add},i}} \;\Rightarrow\; m_b = \frac{\omega_2^2 m_{\mathrm{add},2} - \omega_1^2 m_{\mathrm{add},1}}{\omega_1^2 - \omega_2^2}
```

3. **Horizontalbahn:** Spitze seitlich filmen, x\_b gegen z\_b² regressieren → 3m-spezifischer Koeffizient.
4. Werte als Brettprofil („Schwimmhalle X, Brett links“) in der App speichern.

### 9.4 Athletenkalibrierung

Video von TD bis TO (≥ 200 Hz, seitlich, bei Level 3 zwei Kameras oder markerloses 3D), Digitalisierung, Import, Matching (Kapitel 6.7). Ergebnis: subjektspezifische T\_max-Faktoren, mit denen Modus A realistische Prognosen für diese Athletin/diesen Athleten liefert.

## 10. App-Architektur, UI und Design

Die Physik läuft in einem getesteten Python-Kern, die Oberfläche ist eine React-App mit 3D-Ansicht; nur Level 1 wird zusätzlich nach TypeScript portiert, damit Slider in Echtzeit reagieren.

### 10.1 Tech-Stack

| Schicht | Technologie | Aufgabe |
| --- | --- | --- |
| Physik-Kern | Python 3.12, NumPy, SciPy, SymPy, optional Pinocchio | Modelle, Integration, Optimierung, inverse Dynamik |
| API | FastAPI, Pydantic, WebSocket für Fortschritt | Simulationsjobs, Parameter-Validierung |
| Rechenjobs | Prozess-Pool bzw. Celery + Redis | Optimierung und Parameterstudien parallel |
| Frontend | React 18, TypeScript, Vite, Zustand | UI, State |
| 3D | three.js über react-three-fiber + drei | Springer, Brett, Kraftvektoren, Trajektorien |
| Diagramme | Plotly.js oder visx | Zeitverläufe, Heatmaps |
| Level-1-Live | TypeScript-Port im Web Worker | Echtzeit bei Slider-Änderung |
| Export | CSV, JSON, PDF-Report, PNG/MP4 der 3D-Szene | Weitergabe an Athlet:innen und Trainerteam |
| Tests | pytest + hypothesis, Vitest, Playwright | Physik-, UI- und End-to-End-Tests |

### 10.2 Repository-Struktur

```markdown
diving-sim/
  SPEC.md            ← dieses Dokument
  CLAUDE.md          ← Arbeitsregeln für Claude Code
  core/              ← Python-Paket: board.py, athlete.py, anthropometry/, muscles.py,
                        contact.py, models/level1.py level2.py level3.py,
                        events.py, flight.py, optimize.py, inverse.py, energy.py
  core/tests/        ← Tests aus Kapitel 9.1
  api/               ← FastAPI-App
  web/               ← React-App (src/scene, src/panels, src/charts, src/sim-live)
  data/              ← de-Leva-Tabellen, Brettprofile, Presets (JSON, mit Quellen)
  docs/validation/   ← Validierungsberichte als Notebooks
```

### 10.3 Bildschirmaufbau

- **Links – Parameter-Panel:** Athlet:in, Brett, Technik, 3D, Numerik (eingeklappt). Schätzwerte mit Markierung, Literaturwerte mit Quellen-Tooltip.
- **Mitte – 3D-Szene:** Brett mit realer Biegung (Biegelinie skaliert), Springer als Segmentmodell, Bodenreaktionskraft als roter Pfeil am Kraftangriffspunkt, KSP-Bahn, Brettfreigang-Linie, Wasseroberfläche bei –3 m. Kamera frei, Presets: seitlich, frontal, Brettperspektive.
- **Zeitleiste unten:** Scrubber mit Phasenmarken P1–P7, Zeitlupe 0,05×–1×, Einzelbild.
- **Rechts – Kennwerte:** Karten für v\_z,TO, h\_max, Peak-F (BW), max. Durchbiegung, Kontaktzeit, H\_y, Rotationspotenzial, Freigang, Energiebilanz-Status.
- **Tabs unter der Szene:** Kraft-Zeit, Brettweg/-geschwindigkeit, Gelenkwinkel, Gelenkmomente/-leistung, Energiefluss (Sankey), Drehimpuls je Segment.
- **Vergleichsmodus:** zwei bis vier Simulationen überlagert (z. B. Fulkrum 6 vs. 8), Differenzen hervorgehoben.
- **Parameterstudie:** 1D-Sweep als Linie, 2D-Sweep als Heatmap (z. B. Fulkrum × Körpermasse → h\_max).

### 10.4 Design: Schwarz-Rot

| Token | Wert | Verwendung |
| --- | --- | --- |
| Hintergrund | #0B0B0D | App-Fläche |
| Fläche 2 | #16161A | Panels, Karten |
| Linien | #2A2A30 | Raster, Trenner |
| Text primär | #F4F4F5 | Werte, Überschriften |
| Text sekundär | #A1A1AA | Einheiten, Labels |
| Akzent Rot | #E10600 | Kraftvektor, aktive Auswahl, Hauptkennwert |
| Rot hell | #FF4D4D | Hover, zweite Kurve |
| Warnung | #F59E0B | Schätzwerte, Energiebilanz-Warnung |

Schrift: Inter (UI) und JetBrains Mono (Zahlen, tabellarische Ziffern). Rot nur für das Wichtigste; zusätzliche Kurven in Graustufen, damit der Akzent lesbar bleibt. Farbunabhängige Unterscheidung (Linienstil) für Barrierefreiheit.

## 11. Umsetzungsplan und Prompts für Claude Code

Baue in sieben Etappen und lass Claude Code jede Etappe erst abschließen, wenn ihre Tests grün sind; so bleibt die Physik nachprüfbar, bevor UI darauf aufsetzt.

### 11.1 Inhalt für CLAUDE.md

```markdown
# Projektregeln: 3m-Brett-Simulator
- Fachliche Grundlage ist SPEC.md. Bei Widerspruch gilt SPEC.md; frag nach, statt zu raten.
- SI-Einheiten intern, Koordinaten nach SPEC Kap. 3. Jede Funktion dokumentiert Einheiten.
- Jeder physikalische Parameter liegt in data/ als JSON mit Feldern value, unit, source, status.
- Keine Physik ohne Test. Tests aus SPEC Kap. 9.1 müssen vor jedem Commit laufen.
- Bewegungsgleichungen Level 2/3 werden symbolisch erzeugt (SymPy), nie von Hand abgetippt.
- Schätzwerte niemals stillschweigend als Fakten ausgeben: Status in API und UI mitführen.
- Design: Schwarz-Rot-Tokens aus SPEC Kap. 10.4.
```

### 11.2 Etappen

| Etappe | Inhalt | Fertig, wenn |
| --- | --- | --- |
| 1 | Repo, Datenmodell, Parameter-JSON, Brettmodell, Level 1, Flugphase | Tests 9.1 Nr. 1, 2, 3, 5, 7, 8 grün |
| 2 | Web-UI-Grundgerüst, Level 1 live im Web Worker, 2D-Plots | Slider ändern Ergebnis < 50 ms |
| 3 | Anthropometrie (de Leva), Level 2 planar mit Kontakt, Muskeln, Schwabbelmassen | Test Nr. 4 grün, Energiebilanz < 0,5 % |
| 4 | 3D-Szene (react-three-fiber), Zeitleiste, Kraftvektoren, Vergleichsmodus | Szene synchron mit Kennwerten |
| 5 | Optimierung (SA/CMA-ES, Robustheit), Parameterstudien, Heatmaps | Reproduziert Muster aus 9.2 |
| 6 | Modus B: Import, Filterung, inverse Dynamik, Matching | Matching-RMS < 10 % an Testdaten |
| 7 | Level 3 räumlich, Asymmetrien, PDF-Report, Brettkalibrier-Assistent | Test Nr. 6 grün |

### 11.3 Start-Prompt (Etappe 1)

```text
Lies SPEC.md und CLAUDE.md vollständig. Erstelle die Repository-Struktur aus SPEC Kap. 10.2.
Implementiere in core/: das Brettmodell (Kap. 4.2, 4.3 Variante A und B, 4.5),
Level 1 (Kap. 6.1) mit Event-Detektion (Kap. 2) und die analytische Flugphase (Kap. 6.5).
Lege alle Parameter mit value/unit/source/status in data/ ab.
Schreibe zuerst die Tests aus Kap. 9.1 (Nr. 1, 2, 3, 5, 7, 8), dann den Code, bis alle grün sind.
Gib am Ende eine Tabelle der Ausgabegrößen aus Kap. 7 für das Preset "Elite w 58 kg, Fulkrum 7,5"
und markiere jeden Wert, der auf Schätzparametern beruht.
```

### 11.4 Folge-Prompts

```text
Etappe 2: Baue web/ nach SPEC Kap. 10.1, 10.3 und 10.4. Portiere Level 1 nach TypeScript
in einen Web Worker und prüfe per Vitest, dass TS- und Python-Ergebnis auf 1e-6 übereinstimmen.

Etappe 3: Erzeuge mit sympy.physics.mechanics (Kane) das planare 8-Segment-Modell aus Kap. 5 und 6.2,
inklusive Fußkontakt (5.4), Schwabbelmassen (5.5) und Drehmoment-Generatoren (5.3).
Implementiere die de-Leva-Tabellen vollständig aus dem Originalpaper als JSON mit Quelle.
Teste Reduktion auf Level 1 und die Energiebilanz.

Etappe 4: 3D-Szene mit react-three-fiber nach Kap. 10.3; Brettbiegung aus Biegelinie,
Kraftvektor in #E10600, Zeitleiste mit Phasenmarken, Vergleich von bis zu vier Läufen.

Etappe 5: Optimierung nach Kap. 6.6 inkl. Robustheitsterm, Parameterstudien als 1D/2D-Sweep.
Validiere qualitativ gegen Kap. 9.2 und dokumentiere das in docs/validation/.

Etappe 6: Modus B nach Kap. 6.7: CSV-Import (Kinovea, OpenCap), Butterworth-Filter mit
Residualanalyse, inverse Dynamik, Matching-Score, Ausgabe subjektspezifischer Parameter.

Etappe 7: Level 3 mit Featherstone/Pinocchio nach Kap. 6.3, bilaterale Kontakte, Asymmetrie-
Parameter aus Kap. 8, Brettkalibrier-Assistent nach Kap. 9.3, PDF-Report im Schwarz-Rot-Design.
```

**Arbeitsweise:** Pro Etappe eine neue Claude-Code-Session mit Plan-Modus starten, den Plan prüfen, dann ausführen lassen. Nach jeder Etappe prüfst du die Kennwerte fachlich gegen deine eigenen Videodaten.

## 12. Modellgrenzen und Literatur

Die größten Unsicherheiten liegen bei Brettparametern für 3m und anderen Fulkrum-Stellungen sowie bei generischen Kraftwerten – beides löst die Kalibrierung aus Kapitel 9.3 und 9.4.

**Bekannte Grenzen**

- Brettsteifigkeit, effektive Masse und Kontaktparameter stammen aus wenigen Studien, teils vom 1m-Brett und bei Fulkrum 7,5.
- Die Fulkrum-Abhängigkeit der effektiven Masse ist in Version 1 eine Schätzformel.
- Drehmoment-Generatoren bilden Muskelgruppen ab, nicht Einzelmuskeln; biartikuläre Kopplung (z. B. Gastrocnemius) ist nur indirekt enthalten.
- Räumliche (3D-)Absprungmodelle vom Brett sind in der Literatur kaum validiert; Level 3 ist daher als explorativ zu kennzeichnen.
- Keine Ermüdung, keine Sehnenelastizität als eigener Speicher, kein Wassereintritt.

**Literatur (Kern)**

- Sprigings, E. J., Stilling, D. S. & Watson, L. G. (1989). Development of a model to represent an aluminum springboard in diving. Int J Sport Biomech 5.
- [Dorotich, P. D., Stilling, D. S., Sprigings, E. J. & Watson, L. G. (1990). Measurement of the modeling parameters for a Maxiflex ‚B‘ springboard. Int J Sport Biomech 6:325–335.](https://katalog.lib.cas.cz/KNAV/EdsRecord/edsair,edsair.doi...........8bae0ce6c5c6c28bda0e08cb5c8ff98a)
- Jones, I. C. & Miller, D. I. (1996). Influence of fulcrum position on springboard response and takeoff performance in the running approach. J Appl Biomech 12:383–408.
- Miller, D. I. et al. (1998). J Sports Sci 16:571–583 (Brettparameter über Fulkrum-Stellungen).
- [Miller, D. I. (2008). Springboard and platform diving. In: Biomechanics in Sport, 326–348.](https://www.researchgate.net/publication/229495572_Springboard_and_Platform_Diving)
- [Cheng, K. B. & Hubbard, M. (2005). Optimal compliant-surface jumping: a multi-segment model of springboard standing jumps. J Biomech 38:1822–1829.](https://lida.sport-iat.de/twm/Record/4012670?lng=en)
- [Cheng, K. B. & Hubbard, M. (2005). Differences between jumping and somersaulting from a diving springboard. ISBS Beijing.](https://ojs.ub.uni-konstanz.de/cpa/article/view/1153)
- Cheng, K. B. & Hubbard, M. (2008). Role of arms in somersaulting from compliant surfaces. Hum Mov Sci 27:80–95.
- [Kong, P. W., Yeadon, M. R. & King, M. A. (2004). A new model of the springboard in diving. ISBS Ottawa.](https://ojs.ub.uni-konstanz.de/cpa/article/view/1282)
- [Kong, P. W., Yeadon, M. R. & King, M. A. – Parameterbestimmung Springer-Brett-Modell mit Schwabbelmassen (Loughborough).](https://core.ac.uk/download/288388973.pdf)
- [Kong, P. W., Yeadon, M. R. & King, M. A. (2006). Constraints and robustness considerations in the optimisation of springboard diving takeoff technique. ISBS.](https://ojs.ub.uni-konstanz.de/cpa/article/view/226/185)
- [Sayyah, M. et al. (2020). Functional variability in the takeoff phase of one metre springboard forward dives.](https://repository.lboro.ac.uk/articles/journal_contribution/Functional_variability_in_the_takeoff_phase_of_one_metre_springboard_forward_dives/12619256)
- [Walker, C. et al. (2012). Kinematic determinants of dive height in springboard diving. Movement & Sport Sciences.](https://stm.cairn.info/revue-movement-and-sport-sciences-2012-1-page-107?lang=en)
- [Ferrier, B., Burnett, A. & Sanders, R. Effect of the timing of hip torque on height in forward somersault dives on the 3m springboard. ISBS.](https://ojs.ub.uni-konstanz.de/cpa/article/view/658)
- Sanders, R. H. & Wilson, B. D. (1988). Factors contributing to maximum height of dives after takeoff from the 3m springboard. Int J Sport Biomech 4.
- Miller, D. I. & Munro, C. F. (1984). Body segment contributions to height achieved during the flight of a springboard dive. Med Sci Sports Exerc.
- de Leva, P. (1996). Adjustments to Zatsiorsky-Seluyanov’s segment inertia parameters. J Biomech 29:1223–1230.
- Yeadon, M. R. (1990). The simulation of aerial movement II: A mathematical inertia model of the human body. J Biomech 23:67–74.
- Yeadon, M. R., King, M. A. & Wilson, C. (2006). Modelling the maximum voluntary joint torque/angular velocity relationship in human movement. J Biomech 39:476–482.
- Selbie, W. S. & Caldwell, G. E. (1996). A simulation study of vertical jumping from different starting postures. J Biomech 29:1137–1146.
- [Duraflex/Malmsten: Datenblatt Maxiflex Model B.](https://www.klubben.no/media/multicase/documents/1123018_duraflex_maxifles_model%20b%20diving%20board.pdf)

Titel ohne Link wurden nicht geöffnet und sind aus Sekundärzitaten bzw. Fachwissen ergänzt; Seitenzahlen vor Publikation prüfen.
