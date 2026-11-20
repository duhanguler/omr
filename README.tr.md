<div align="center">

# OMRKit v2.1

**QR otomatik şablon tanımalı, boş formdan otomatik balon ızgara buluculu, canlı kamera tarayıcılı Optik Form Okuma (OMR) motoru, ArUco PDF form üreteci, sınav psikometrisi, FastAPI REST API ve React Web Studio.**

[![CI](https://github.com/duhanguler/omr/actions/workflows/ci.yml/badge.svg)](https://github.com/duhanguler/omr/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/omrkit?style=flat-square&color=0F8A5F&logo=pypi&logoColor=white)](https://pypi.org/project/omrkit/)
[![Canlı Demo](https://img.shields.io/badge/Canl%C4%B1_Demo-OMRKit_Studio-1D4ED8?style=flat-square&logo=render&logoColor=white)](https://omrkit-studio.onrender.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-0F8A5F.svg?style=flat-square)](LICENSE)
[![Docker GHCR](https://img.shields.io/badge/Docker-ghcr.io%2Fduhanguler%2Fomr-2496ED.svg?style=flat-square)](https://github.com/duhanguler/omr/pkgs/container/omr)

[**Canlı Demo**](https://omrkit-studio.onrender.com/) · [**PyPI**](https://pypi.org/project/omrkit/) · [English](README.md) · [Türkçe](README.tr.md) · [Dağıtım Rehberi](docs/DEPLOYMENT.md) · [Örnekler](examples/) · [Katkı Rehberi](CONTRIBUTING.md)

</div>

> **Canlı Web Studio Demosu:** Kurulum yapmadan doğrudan tarayıcınızda deneyin → **[omrkit-studio.onrender.com](https://omrkit-studio.onrender.com/)** *(Render ücretsiz katmanında ilk açılış ~20–30 sn sürebilir.)*

---

## Öne Çıkan Özellikler

- **Otomatik Baskıya Hazır Optik Form Üreteci (`omrkit generate`):** A4 veya Letter formatında, 4 köşesinde ArUco işaretçisi ve **otomatik şablon tanıtan QR rozeti** bulunan vektörel PDF + birebir eşleşen `template.json` üretir.
- **Şablonsuz QR Otomatik Tarama:** Üretilen formlarda `-t template.json` bile vermeden doğrudan `omrkit scan klasor/` ile her sayfanın şablonunu QR koddan otomatik tanıyıp okur.
- **Boş Formdan Otomatik Balon Izgara Keşfi (`omrkit detect-layout`):** Elinizdeki herhangi bir mevcut boş optik formu yükleyin; balonları otomatik bulup bloklara ayırarak anında `template.json` taslağı çıkarır.
- **Canlı Webcam / Mobil Tarayıcı Kamera Okuyucu (`Live Camera`):** Tarayıcıdan (`getUserMedia`) gerçek zamanlı kamera ile köşeler kilitlendiğinde otomatik tarama (**Auto-Lock**) + sesli bildirim.
- **Tek Tık Canlı Demo & Eski Şablon Dönüştürücü:** Studio üst çubuğundaki **Try Demo** ile 5 öğrencilik gerçekçi sınavı 1 saniyede deneyin; eski `OMRChecker` şablonlarını `omrkit migrate-template` ile tek komutta v2 formatına geçirin.
- **Türkiye Sınav Sistemine Hazır Ön Ayarlar:**
  - `turkish_exam_50`: 50 soru (A–E), 6 haneli Sınav Kodu, **11 haneli TC Kimlik No** (algoritmik sağlama doğrulamalı) ve Kitapçık (A–D).
  - `turkish_yks_120`: 120 soruluk TYT/YKS optik düzeni.
  - Hazır puanlama politikaları: **YKS / TYT / KPSS (4 yanlış 1 doğruyu götürür)**, **LGS (3 yanlış 1 doğruyu götürür)**, standart puanlama, çoklu kitapçık (A/B/C/D) ve iptal/bonus soru desteği.
- **Hibrit Balon Algılama & HITL İnceleme:** Düzgün karalamanın yanında **tik (✓) ve çarpı (✗)** işaretlerini de okur; her soru için `0–1` güven skoru hesaplar, çoklu işaretleme veya silik/belirsiz lekeleri Web Studio’da 1 tıkla onaylanmak üzere inceleme kuyruğuna ayırır.
- **Sınav Psikometrisi & Raporlama:** Ortalama, medyan, standart sapma, yüzdelik dilimler, madde güçlük indeksi ($p$), ayırt edicilik indeksi ($D$), çeldirici dağılımı, **KR-20 güvenilirlik katsayısı**, çok sekmeli Excel (`.xlsx`), CSV, JSON ve öğrenci bazlı **PDF Sınav Karnesi**.

---

## Hızlı Başlangıç

```bash
# PyPI üzerinden kurulum (önerilen):
pip install omrkit              # Çekirdek CV motoru + PDF + ArUco/QR + CLI
pip install "omrkit[all]"       # Tam paket: Web Studio, FastAPI REST API ve Excel desteği
```

### 1. Türkçe 50 Soruluk Optik Form + Şablon Üret

```bash
omrkit generate --preset turkish_exam_50 -o deneme_sinavi
```

### 2. Şablonsuz QR Tarama, Mevcut Formdan Izgara Keşfi veya Gerçek Türkçe Taramalar

```bash
# QR ile sıfır şablon tarama:
omrkit scan examples/standard_mcq_40q/scans -o outputs/auto_demo

# Mevcut herhangi bir boş formdan otomatik şablon keşfi:
omrkit detect-layout examples/turkish_exam_50q/blank_form.jpg -o kesfedilen_template.json

# Gerçek Türkçe 50 soruluk telefon taramaları + YKS puanlama + PDF karneler:
omrkit scan examples/turkish_exam_50q/scans \
  -t examples/turkish_exam_50q/template.json \
  -k examples/turkish_exam_50q/answer_key.json \
  --policy yks_tyt \
  --format csv,json,xlsx,scorecards \
  -o outputs/turkish_demo
```

### 3. Görsel Web Studio, Canlı Demo & Docker

```bash
# Yerelde Web Studio:
omrkit studio
# Web Studio:   http://127.0.0.1:8000
# OpenAPI Docs: http://127.0.0.1:8000/docs

# Sıfır derleme ile resmi GHCR Docker imajı:
docker run -p 8000:8000 ghcr.io/duhanguler/omr:latest
```

Ücretsiz canlı demo yayınlama (**HuggingFace Spaces** / **Render Tek Tık Blueprint**) ve **PyPI Trusted Publishing** adımları için [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) rehberine göz atabilirsiniz.

---

## Gizlilik & EXIF Temizliği

Telefonla çekilen optik form fotoğraflarını paylaşmadan veya test setine eklemeden önce GPS/cihaz bilgisini silmek ve yönü sabitlemek için yerleşik aracı kullanabilirsiniz:

```bash
omrkit strip-exif ham_fotograflar/ -o temiz_fotograflar/
```

---

## Lisans

[MIT Lisansı](LICENSE) altında açık kaynak olarak sunulmaktadır.
