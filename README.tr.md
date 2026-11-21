<div align="center">

# OMRKit v2.3

**Sınıf CSV kişiselleştirilmiş sınav paketi (`OMRKIT:v3` QR), cevap kağıdından Zero-JSON anahtar tarama, Moodle/Canvas not defteri ve toplu PDF karne, 3/4 ArUco köşe kurtarma, silinmiş leke dayanımı, fotokopi mikro hizalama, canlı kamera tarayıcı, Türkçe Unicode PDF üreteci, sınav psikometrisi ve 6 dilli Web Studio.**

[![CI](https://github.com/duhanguler/omr/actions/workflows/ci.yml/badge.svg)](https://github.com/duhanguler/omr/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/omrkit?style=flat-square&color=0D7A52&logo=pypi&logoColor=white)](https://pypi.org/project/omrkit/)
[![Canlı Demo](https://img.shields.io/badge/Canl%C4%B1_Demo-OMRKit_Studio-1849C6?style=flat-square&logo=render&logoColor=white)](https://omrkit-studio.onrender.com/)
[![Release](https://img.shields.io/github/v/release/duhanguler/omr?style=flat-square&color=111317)](https://github.com/duhanguler/omr/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-0D7A52.svg?style=flat-square)](LICENSE)
[![Docker GHCR](https://img.shields.io/badge/Docker-ghcr.io%2Fduhanguler%2Fomr-2496ED.svg?style=flat-square)](https://github.com/duhanguler/omr/pkgs/container/omr)

[**Canlı Demo**](https://omrkit-studio.onrender.com/) · [**PyPI**](https://pypi.org/project/omrkit/) · [Dağıtım Rehberi](docs/DEPLOYMENT.md) · [Örnekler](examples/) · [Katkı Rehberi](CONTRIBUTING.md)

[English](README.md) · **Türkçe** · [简体中文](README.zh.md) · [Deutsch](README.de.md) · [Русский](README.ru.md) · [Español](README.es.md)

</div>

> **Canlı Web Studio Demosu:** Kurulum yapmadan tarayıcınızda deneyin → **[omrkit-studio.onrender.com](https://omrkit-studio.onrender.com/)** (`EN · TR · ZH · DE · RU · ES` destekli). Üst çubuktan **Örnek Kohort** düğmesine tıklayıp 5 öğrencilik sınavı tarayın, sınıf CSV'sinden kişiselleştirilmiş PDF paketi üretin veya öğretmen cevap anahtarı kağıdını doğrudan tarayın. *(Render ücretsiz katmanında ilk açılış ~20–30 sn sürebilir.)*

---

## v2.3 Öne Çıkan Özellikler

- **Sınıf & Öğretmen İş Akışları (Yeni!):**
  - **Sınıf Listesi Kişiselleştirme (`--roster class.csv` + `OMRKIT:v3` QR):** CSV sınıf listesinden (noktalı virgül/virgül & Türkçe başlık uyumlu) her öğrenciye adı, numarası, sınıfı ve kitapçığı basılı, isteğe bağlı ID/Kitapçık balonları önceden doldurulmuş çok sayfalı PDF sınav paketi üretir; taranırken öğrenci kimliği QR v3'ten sıfır kodlama hatasıyla okunur.
  - **Cevap Kağıdından Zero-JSON Anahtar (`omrkit key-from-sheet`):** Öğretmenin kalemle doldurduğu 1–4 kitapçıklı cevap anahtarı kağıdını doğrudan `AnswerKey` JSON'a dönüştürür (çoklu doğru cevapları ve boş soruları otomatik tanır).
  - **Moodle & Canvas LMS + Toplu Sınıf PDF Karne:** Tek tıkla Moodle/Canvas not defteri CSV'si, tüm sınıfı içeren tek çok sayfalı PDF karne (`scorecards_pdf`) ve masaüstü ADF tarayıcılar için canlı klasör izleyici (`omrkit watch`).
- **Gerçek Hayat Optik Dayanımı:**
  - **Silinmiş Kurşun Kalem Lekesi Filtresi:** Koyuluk baskınlığı filtresiyle silinmiş gri izleri yanlış çift işaretleme olarak bayraklamaz; gerçek çift işaretlemeleri (`multi_marked`) eksiksiz yakalar.
  - **3/4 ArUco Köşe Kurtarma (`aruco_3pt`):** Bir köşe işaretçisi parmak, zımba veya katlanma nedeniyle kapansa bile kalan 3 işaretçinin 12 alt-piksel köşesinden tam perspektif homografisi kurar.
  - **Fotokopi Kayması Mikro Hizalama:** Blok bazlı Sobel kenar korelasyonu (`±6px`) ile fotokopi/baskı kaymalarını balon merkezlerine otomatik oturtur.
  - **Otomatik Eğiklik Düzeltmeli Izgara Keşfi (`omrkit detect-layout`):** `±12°` eğik taranmış boş formları otomatik doğrultup balon bloklarını `template.json` olarak çıkarır.
- **Doğal Türkçe Unicode PDF Form Üreteci (`omrkit generate`):** `İ, Ş, Ğ, Ü, Ö, Ç` karakterlerini bozmadan gömülü TrueType fontlarla vektörel A4/Letter optik form (ArUco + QR rozeti) ve birebir eşleşen `template.json` üretir.
- **Türkiye Sınav Sistemine Hazır Ön Ayarlar:**
  - `turkish_exam_50`: 50 soru (A–E), 6 haneli Sınav Kodu, **11 haneli TC Kimlik No** (mod-10/11 algoritmik sağlama doğrulamalı) ve Kitapçık (A–D).
  - `turkish_yks_120`: 120 soruluk TYT/YKS optik düzeni (4 sütun × 30 satır).
  - Hazır puanlama kuralları: **YKS / TYT / KPSS (4 yanlış 1 doğruyu götürür)**, **LGS (3 yanlış 1 doğruyu götürür)**, standart puanlama, çoklu kitapçık (`A/B/C/D`) ve bonus/iptal soru desteği.
- **6 Dilli Optik Çalışma Tezgâhı (Web Studio):**
  - **Tara & İncele:** Bayraklı kartlarda yakınlaştırılmış balon şeridi kırpımı, ana kağıt üzerinde canlı konum çerçevesi ve klavye ile hızlı onay (`A–E`, `Backspace`, `↑↓`).
  - **Canlı Kamera:** `getUserMedia` vizörü, köşe kilitlenince otomatik çekim (**Auto-Lock**), sesli onay ve QR otomatik tanıma.
  - **Şablon Tasarımcı:** Doğrudan tuval üzerinde blok seçme/sürükleme, ok tuşlarıyla `1px` / `Shift 10px` hassas kaydırma, Geri Al / İleri Al (`Ctrl+Z` / `Ctrl+Shift+Z`), canlı piksel koordinat göstergesi ve eski `OMRChecker` v1 dönüştürücü.
  - **Puanlama & Psikometri:** Üzerine gelince detaylı okuma veren puan histogramı, sıralanabilir öğrenci tablosu, seçenek dağılım çubukları ve kalite filtreli Klasik Test Kuramı ($p$, $D$, **KR-20**), Excel (`.xlsx`) ve Türkçe **PDF Sınav Karnesi**.

---

## Gerçek Tarama & Üretilen Form Örnekleri

<table>
  <tr>
    <td width="54%" align="center">
      <img src="https://raw.githubusercontent.com/duhanguler/omr/main/docs/assets/scan_overlay_demo.jpg" alt="OMRKit gerçek telefon taraması doğrulama görseli" />
      <br />
      <sub><b>Gerçek telefon taraması:</b> Zümrüt = güvenli okuma (✓ ve ✗ dahil), Kırmızı = çift işaret, Amber = yakınlaştırılmış HITL inceleme kuyruğu.</sub>
    </td>
    <td width="46%" align="center">
      <img src="https://raw.githubusercontent.com/duhanguler/omr/main/docs/assets/generated_sheet_preview.jpg" alt="OMRKit üretilen ArUco + QR optik cevap kağıdı" />
      <br />
      <sub><b>Sıfır kalibrasyonlu PDF:</b> Vektörel A4/Letter, ArUco [0,1,2,3], gömülü QR rozeti ve birebir eşleşen <code>template.json</code>.</sub>
    </td>
  </tr>
</table>

---

## Hızlı Başlangıç

```bash
# PyPI üzerinden kurulum (önerilen):
pip install omrkit              # Çekirdek CV motoru + PDF + ArUco/QR + CLI
pip install "omrkit[all]"       # Tam paket: 6 dilli Web Studio, FastAPI REST API ve Excel desteği

# Veya sıfır derleme ile resmi GHCR Docker imajı:
docker run -p 8000:8000 ghcr.io/duhanguler/omr:latest
```

### 1. Türkçe 50 Soruluk Optik Form + Şablon Üret

```bash
omrkit generate --preset turkish_exam_50 -o deneme_sinavi
```

### 2. Şablonsuz QR Tarama, Boş Formdan Izgara Keşfi veya Gerçek Taramalar

```bash
# QR ile şablon vermeden tarama:
omrkit scan examples/standard_mcq_40q/scans -o outputs/auto_demo

# Mevcut boş formdan eğiklik düzeltmeli otomatik şablon keşfi:
omrkit detect-layout examples/turkish_exam_50q/blank_form.jpg -o kesfedilen_template.json

# Gerçek Türkçe 50 soruluk telefon taramaları + YKS puanlama + PDF karneler:
omrkit scan examples/turkish_exam_50q/scans \
  -t examples/turkish_exam_50q/template.json \
  -k examples/turkish_exam_50q/answer_key.json \
  --policy yks_tyt \
  --format csv,json,xlsx,scorecards \
  -o outputs/turkish_demo
```

### 3. Yerelde Web Studio & EXIF Temizliği

```bash
# Web Studio (http://127.0.0.1:8000) & OpenAPI (/docs):
omrkit studio

# Fotoğraflardaki GPS/cihaz EXIF bilgisini silip yönü piksellere sabitle:
omrkit strip-exif ham_fotograflar/ -o temiz_fotograflar/
```

---

## Lisans

[MIT Lisansı](LICENSE) altında açık kaynak olarak sunulmaktadır. Copyright © 2026 Duhan Güler & Katkıda Bulunanlar.
