<div align="center">

# OMRKit v2.3

**Движок OMR без ручной калибровки: персонализированные пакеты бланков из CSV-списка класса (`OMRKIT:v3` QR), сканирование ключа ответов с бланка учителя (Zero-JSON), экспорт в Moodle/Canvas и сводный PDF карточек, восстановление по 3 из 4 углов ArUco, защита от следов ластика, микровыравнивание, живая камера, психометрика (CTT) и 6-язычная Web Studio.**

[![CI](https://github.com/duhanguler/omr/actions/workflows/ci.yml/badge.svg)](https://github.com/duhanguler/omr/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/omrkit?style=flat-square&color=0D7A52&logo=pypi&logoColor=white)](https://pypi.org/project/omrkit/)
[![Онлайн-демо](https://img.shields.io/badge/%D0%9E%D0%BD%D0%BB%D0%B0%D0%B9%D0%BD_%D0%B4%D0%B5%D0%BC%D0%BE-OMRKit_Studio-1849C6?style=flat-square&logo=render&logoColor=white)](https://omrkit-studio.onrender.com/)
[![Release](https://img.shields.io/github/v/release/duhanguler/omr?style=flat-square&color=111317)](https://github.com/duhanguler/omr/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-0D7A52.svg?style=flat-square)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-111317.svg?style=flat-square)](pyproject.toml)
[![Docker GHCR](https://img.shields.io/badge/Docker-ghcr.io%2Fduhanguler%2Fomr-2496ED.svg?style=flat-square)](https://github.com/duhanguler/omr/pkgs/container/omr)

[**Онлайн-демо**](https://omrkit-studio.onrender.com/) · [**PyPI**](https://pypi.org/project/omrkit/) · [Развёртывание](docs/DEPLOYMENT.md) · [Примеры](examples/) · [Участие](CONTRIBUTING.md)

[English](README.md) · [Türkçe](README.tr.md) · [简体中文](README.zh.md) · [Deutsch](README.de.md) · **Русский** · [Español](README.es.md)

</div>

> **Онлайн-песочница Web Studio:** Откройте **[omrkit-studio.onrender.com](https://omrkit-studio.onrender.com/)** в браузере (**EN · TR · ZH · DE · RU · ES**), нажмите **Пример партии** или протестируйте генерацию персонализированных бланков класса, скан ключа ответов и экспорт Moodle/Canvas. *(Бесплатный тариф Render: холодный старт ~20–30 с.)*

---

## Ключевые возможности (v2.3)

- **Сценарии для преподавателей и классов (Новое):**
  - **Персонализация по списку класса (`--roster class.csv` + `OMRKIT:v3` QR):** Создаёт многостраничный PDF-пакет с ФИО, ID, классом, вариантом и предзаполненными кружками ID; при сканировании личность ученика автоматически считывается из QR v3.
  - **Скан ключа ответов с бумажного бланка (`omrkit key-from-sheet`):** Превращает заполненные учителем бланки (1–4 варианта, включая множественные правильные ответы) прямо в `AnswerKey` без ручного JSON.
  - **Экспорт Moodle / Canvas, сводный PDF карточек и `omrkit watch`:** Готовые CSV для Moodle и Canvas, единый многостраничный PDF со всеми карточками класса (`scorecards_pdf`) и фоновый мониторинг папки сканера.
- **Устойчивость к реальным дефектам печати и съёмки:**
  - **Фильтр стёртых следов карандаша (`erased_dominance_ratio`):** Отсеивает бледные следы ластика и не создаёт ложных флагов двойной отметки, сохраняя 100% точность на реальных двойных отметках и мягком карандаше HB.
  - **Восстановление по 3 из 4 маркеров ArUco (`aruco_3pt`):** Если один угол перекрыт пальцем, скрепкой или сгибом, вычисляет точную перспективную гомографию по 12 субпиксельным углам трёх видимых маркеров.
  - **Поблочное микровыравнивание (`local_refinement`):** Корреляция границ Собеля (`±6px`) компенсирует локальные сдвиги фотокопий и масштабирования принтера.
  - **Автопоиск сеток с коррекцией наклона (`omrkit detect-layout`):** Автоматически выравнивает перекошенные до `±12°` пустые бланки и извлекает готовую структуру `template.json`.
- **Генератор векторных Unicode-PDF и автопоиск по QR:** Формирует A4/Letter PDF с TrueType-шрифтами, маркерами ArUco `[0,1,2,3]`, встроенным QR-кодом шаблона и точным `template.json`. При сканировании флаг `-t` не требуется.
- **Гибридный классификатор отметок и валидаторы:** Распознаёт закрашивание, **галочки (✓) и крестики (✗)** при тенях и бликах; проверяет идентификаторы по алгоритмам **Luhn** и **TC Kimlik No**.
- **Психометрика заданий (CTT) и отчётность:** Средний балл, медиана, стандартное отклонение, трудность ($p$), дискриминативность ($D$ по верхним/нижним 27%), распределение дистракторов и надёжность **KR-20**; экспорт в CSV, JSON, многолистовой Excel (`.xlsx`) и индивидуальные **PDF-карточки**.
- **6-язычная Web Studio:**
  - **Скан и проверка:** Увеличенные фрагменты спорных строк прямо в карточках очереди, живая рамка выделения на основном листе и быстрая проверка с клавиатуры (`A–E`, `Backspace`, `↑↓`).
  - **Редактор шаблонов:** Перетаскивание блоков мышью, сдвиг стрелками на `1px` (`Shift 10px`), история Отменить/Повторить (`Ctrl+Z` / `Ctrl+Shift+Z`), живые координаты курсора и миграция шаблонов `OMRChecker` v1.

---

## Реальные сканы и сгенерированные бланки

<table>
  <tr>
    <td width="54%" align="center">
      <img src="https://raw.githubusercontent.com/duhanguler/omr/main/docs/assets/scan_overlay_demo.jpg" alt="OMRKit распознавание фото со смартфона" />
      <br />
      <sub><b>Фото со смартфона:</b> Зелёный = уверенное распознавание (включая ✓ и ✗), Красный = двойная отметка, Жёлтый = очередь ручной проверки.</sub>
    </td>
    <td width="46%" align="center">
      <img src="https://raw.githubusercontent.com/duhanguler/omr/main/docs/assets/generated_sheet_preview.jpg" alt="OMRKit векторный бланк ArUco + QR" />
      <br />
      <sub><b>Векторный PDF без калибровки:</b> A4/Letter, маркеры ArUco [0,1,2,3], QR-код и точный файл <code>template.json</code>.</sub>
    </td>
  </tr>
</table>

---

## Быстрый старт (60 секунд)

```bash
# Установка из PyPI (рекомендуется)
pip install omrkit              # Ядро CV + PDF + ArUco/QR + генератор + CLI
pip install "omrkit[all]"       # Полный комплект: Web Studio, FastAPI и Excel

# Или запуск готового Docker-образа без сборки
docker run -p 8000:8000 ghcr.io/duhanguler/omr:latest
```

### 1. Сгенерировать бланк ArUco + QR

```bash
omrkit generate --preset standard_mcq_40 -o exam_pack
# Создаёт: standard_mcq_40_sheet.pdf, template.json, answer_key.json
```

### 2. Сканирование и оценивание изображений или многостраничных PDF

```bash
# Автоопределение шаблона по QR-коду бланка:
omrkit scan examples/standard_mcq_40q/scans -o outputs/auto_demo

# С явным шаблоном, ключом ответов, Excel и PDF-карточками:
omrkit scan examples/standard_mcq_40q/scans \
  -t examples/standard_mcq_40q/template.json \
  -k examples/standard_mcq_40q/answer_key.json \
  --policy standard \
  --format csv,json,xlsx,scorecards \
  -o outputs/demo

# Автопоиск сеток на любом пустом бланке (с коррекцией наклона ±12°):
omrkit detect-layout examples/turkish_exam_50q/blank_form.jpg -o auto_template.json
```

### 3. Web Studio и Python SDK

```bash
omrkit studio
# Web Studio:    http://127.0.0.1:8000
# OpenAPI Docs:  http://127.0.0.1:8000/docs
```

```python
from omrkit import AnswerKey, ExamGrader, GradingPolicy, OMRScanner, Template

template = Template.from_file("examples/standard_mcq_40q/template.json")
batch = OMRScanner(template).scan_batch("examples/standard_mcq_40q/scans", workers=4)

key = AnswerKey.from_file("examples/standard_mcq_40q/answer_key.json")
report = ExamGrader(key, GradingPolicy.preset("standard")).grade_batch(batch.sheets)
print(f"Проверено: {report.analytics.student_count} | Средний балл: {report.analytics.mean_score} | KR-20: {report.analytics.kr20_reliability}")
```

---

## Лицензия

Распространяется по лицензии [MIT License](LICENSE). Copyright © 2026 Duhan Güler & Contributors.
