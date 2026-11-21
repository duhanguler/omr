<div align="center">

# OMRKit v2.3

**Kalibrierungsfreie OMR-Engine mit personalisiertem Klassenlisten-Seriendruck (`OMRKIT:v3`-QR), Zero-JSON-Lösungsbogen-Scan, Moodle/Canvas-Notenexport & Klassen-Sammel-PDF, 3-von-4-ArUco-Wiederherstellung, Radiergummi-Schmierfilter, Kopierversatz-Mikroausrichtung, Live-Kamera, KTT-Psychometrie und 6-sprachigem Web Studio.**

[![CI](https://github.com/duhanguler/omr/actions/workflows/ci.yml/badge.svg)](https://github.com/duhanguler/omr/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/omrkit?style=flat-square&color=0D7A52&logo=pypi&logoColor=white)](https://pypi.org/project/omrkit/)
[![Live-Demo](https://img.shields.io/badge/Live_Demo-OMRKit_Studio-1849C6?style=flat-square&logo=render&logoColor=white)](https://omrkit-studio.onrender.com/)
[![Release](https://img.shields.io/github/v/release/duhanguler/omr?style=flat-square&color=111317)](https://github.com/duhanguler/omr/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-0D7A52.svg?style=flat-square)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-111317.svg?style=flat-square)](pyproject.toml)
[![Docker GHCR](https://img.shields.io/badge/Docker-ghcr.io%2Fduhanguler%2Fomr-2496ED.svg?style=flat-square)](https://github.com/duhanguler/omr/pkgs/container/omr)

[**Live-Demo**](https://omrkit-studio.onrender.com/) · [**PyPI**](https://pypi.org/project/omrkit/) · [Deployment-Leitfaden](docs/DEPLOYMENT.md) · [Beispiele](examples/) · [Mitwirken](CONTRIBUTING.md)

[English](README.md) · [Türkçe](README.tr.md) · [简体中文](README.zh.md) · **Deutsch** · [Русский](README.ru.md) · [Español](README.es.md)

</div>

> **Öffentliche Web-Studio-Demo:** Direkt im Browser unter **[omrkit-studio.onrender.com](https://omrkit-studio.onrender.com/)** testen (**EN · TR · ZH · DE · RU · ES**). Klicken Sie oben auf **Beispieldaten**, erstellen Sie personalisierte Klassenpakete aus CSV oder scannen Sie Lösungsbögen direkt ohne JSON. *(Render Free Tier; Kaltstart ca. 20–30 s.)*

---

## Kernfunktionen (v2.3)

- **Unterrichts- & Lehrkraft-Workflows (Neu):**
  - **Klassenlisten-Seriendruck (`--roster class.csv` + `OMRKIT:v3`-QR):** Personalisierte mehrseitige PDF-Pakete mit Namen, ID, Klasse, Heftkennung und vorausgefüllten ID-Kreisen; beim Scannen automatische Schülerzuordnung ohne Kodierfehler.
  - **Zero-JSON-Lösungsbogen-Scan (`omrkit key-from-sheet`):** Ausgefüllte Musterlösungen (1–4 Hefte, inkl. Mehrfachlösungen) direkt als `AnswerKey` einlesen.
  - **Moodle & Canvas LMS-Export + Sammel-PDF & Ordnerüberwachung:** Direkter Moodle/Canvas-CSV-Import, gebündelte Klassen-Ergebnisblätter (`scorecards_pdf`) und `omrkit watch` für ADF-Scanner.
- **Praxistaugliche Computer-Vision-Pipeline:**
  - **Radiergummi-Schmierfilter (`erased_dominance_ratio`):** Unterscheidet zuverlässig zwischen verblassten Radierspuren und echten Mehrfachmarkierungen (`multi_marked`), während helle HB-Bleistiftmarkierungen sicher erkannt werden.
  - **3-von-4-ArUco-Wiederherstellung (`aruco_3pt`):** Ist eine Ecke durch Finger, Heftklammer oder Knick verdeckt, berechnet OMRKit eine exakte 12-Punkt-Homographie aus den 3 sichtbaren Markern.
  - **Block-Mikroausrichtung (`local_refinement`):** Korrigiert Druck- und Kopierversatz (`±6px`) pro Feldblock per Sobel-Kantenkorrelation auf die exakten Kreismittelpunkte.
  - **Auto-Deskew-Rastererkennung (`omrkit detect-layout`):** Richtet schief gescannte Leerformulare (`±12°`) automatisch gerade und erzeugt direkt eine `template.json`.
- **Druckfertige Unicode-PDFs & QR-Auto-Erkennung:** Erzeugt A4/Letter-Vektor-PDFs mit TrueType-Unicode-Typografie, ArUco-Markern `[0,1,2,3]` und QR-Vorlagencode; beim Scannen entfällt die manuelle Angabe von `-t template.json`.
- **Hybride Markierungserkennung & Prüfsummen:** Erkennt Vollmarkierungen ebenso wie **Häkchen (✓) und Kreuze (✗)** unter ungleichmäßigem Schatten; prüft Kennungen automatisch per **Luhn** oder **TC Kimlik No**.
- **Klassische Testtheorie (KTT) & Exporte:** Berechnet Mittelwert, Median, Standardabweichung, Schwierigkeitsindex ($p$), Trennschärfe ($D$, obere/untere 27 %), Antwortverteilung und **KR-20-Reliabilität**; Export als CSV, JSON, Excel (`.xlsx`) und individuelle **PDF-Ergebnisblätter**.
- **6-sprachiges Web Studio:**
  - **Scannen & Prüfen:** Vergrößerte Ausschnitte direkt in der Prüfwarteschlange, Live-Markierungsrahmen im Hauptbild und Tastatur-Triage (`A–E`, `Backspace`, `↑↓`).
  - **Vorlagen-Editor:** Direktes Verschieben von Blöcken auf dem Canvas, Pfeiltasten-Feinjustage (`1px` / `Shift 10px`), Rückgängig/Wiederholen (`Ctrl+Z` / `Ctrl+Shift+Z`), Live-Koordinatenanzeige und `OMRChecker`-v1-Migration.

---

## Echte Scans & Generierte Antwortbögen

<table>
  <tr>
    <td width="54%" align="center">
      <img src="https://raw.githubusercontent.com/duhanguler/omr/main/docs/assets/scan_overlay_demo.jpg" alt="OMRKit Smartphone-Scan Prüfbild" />
      <br />
      <sub><b>Smartphone-Aufnahme:</b> Grün = sicher erkannt (inkl. ✓ & ✗), Rot = Mehrfachmarkierung, Gelb = Prüfwarteschlange.</sub>
    </td>
    <td width="46%" align="center">
      <img src="https://raw.githubusercontent.com/duhanguler/omr/main/docs/assets/generated_sheet_preview.jpg" alt="OMRKit generierter ArUco + QR Antwortbogen" />
      <br />
      <sub><b>Kalibrierungsfreies Vektor-PDF:</b> A4/Letter mit ArUco [0,1,2,3], QR-Badge und exakt passender <code>template.json</code>.</sub>
    </td>
  </tr>
</table>

---

## Schnellstart (60 Sekunden)

```bash
# Installation über PyPI (empfohlen)
pip install omrkit              # CV-Kern + PDF + ArUco/QR + Generator + CLI
pip install "omrkit[all]"       # Komplettpaket inkl. Web Studio, FastAPI & Excel

# Oder direkt als offizielles Docker-Image starten
docker run -p 8000:8000 ghcr.io/duhanguler/omr:latest
```

### 1. Druckfertigen Antwortbogen erzeugen

```bash
omrkit generate --preset standard_mcq_40 -o pruefung
# Erzeugt: standard_mcq_40_sheet.pdf, template.json, answer_key.json
```

### 2. Bilder oder mehrseitige PDFs scannen & bewerten

```bash
# Automatische Vorlagenerkennung über QR-Code:
omrkit scan examples/standard_mcq_40q/scans -o outputs/auto_demo

# Mit expliziter Vorlage, Lösungsschlüssel, Excel-Report & PDF-Ergebnisblättern:
omrkit scan examples/standard_mcq_40q/scans \
  -t examples/standard_mcq_40q/template.json \
  -k examples/standard_mcq_40q/answer_key.json \
  --policy standard \
  --format csv,json,xlsx,scorecards \
  -o outputs/demo

# Vorlage automatisch aus beliebigem Leerformular erkennen (inkl. Entzerrung):
omrkit detect-layout examples/turkish_exam_50q/blank_form.jpg -o auto_template.json
```

### 3. Web Studio starten oder Python-SDK nutzen

```bash
omrkit studio
# Web Studio:   http://127.0.0.1:8000
# OpenAPI-Doku: http://127.0.0.1:8000/docs
```

```python
from omrkit import AnswerKey, ExamGrader, GradingPolicy, OMRScanner, Template

template = Template.from_file("examples/standard_mcq_40q/template.json")
batch = OMRScanner(template).scan_batch("examples/standard_mcq_40q/scans", workers=4)

key = AnswerKey.from_file("examples/standard_mcq_40q/answer_key.json")
report = ExamGrader(key, GradingPolicy.preset("standard")).grade_batch(batch.sheets)
print(f"Bewertet: {report.analytics.student_count} | Mittelwert: {report.analytics.mean_score} | KR-20: {report.analytics.kr20_reliability}")
```

---

## Lizenz

Veröffentlicht unter der [MIT-Lizenz](LICENSE). Copyright © 2026 Duhan Güler & Mitwirkende.
