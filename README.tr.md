<div align="center">

# OMRKit v2.0

**Sıfır kalibrasyonlu Optik Form Okuma (OMR) motoru, ArUco destekli PDF optik form üreteci, sınav puanlama ve psikometrik analitik, FastAPI REST API ve Görsel Web Studio.**

[English](README.md) · [Türkçe](README.tr.md) · [Örnekler](examples/) · [Katkı Rehberi](CONTRIBUTING.md)

</div>

---

## Öne Çıkan Özellikler

- **Otomatik Baskıya Hazır Optik Form Üreteci (`omrkit generate`):** A4 veya Letter formatında, 4 köşesinde ArUco işaretçisi bulunan vektörel PDF optik form ve milimetrik eşleşen `template.json` dosyasını tek komutla üretir.
- **Türkiye Sınav Sistemine Hazır Ön Ayarlar:**
  - `turkish_exam_50`: 50 soru (A–E), 6 haneli Sınav Kodu, **11 haneli TC Kimlik No** (algoritmik sağlama doğrulamalı) ve Kitapçık (A–D).
  - `turkish_yks_120`: 120 soruluk TYT/YKS optik düzeni.
  - Hazır puanlama politikaları: **YKS / TYT / KPSS (4 yanlış 1 doğruyu götürür)**, **LGS (3 yanlış 1 doğruyu götürür)**, standart puanlama, çoklu kitapçık (A/B/C/D) ve iptal/bonus soru desteği.
- **Gerçek Dünya Kamera Dayanıklılığı:** Çok sayfalı PDF desteği (`pypdfium2`), EXIF otomatik yön düzeltme, gölge/aydınlatma normalizasyonu, 0°/90°/180°/270° otomatik döndürme.
- **Hibrit Balon Algılama & HITL İnceleme:** Düzgün karalamanın yanında **tik (✓) ve çarpı (✗)** işaretlerini de okur; her soru için `0–1` güven skoru hesaplar, çoklu işaretleme veya silik/belirsiz lekeleri Web Studio’da 1 tıkla onaylanmak üzere inceleme kuyruğuna ayırır.
- **Sınav Psikometrisi & Raporlama:** Ortalama, medyan, standart sapma, yüzdelik dilimler, madde güçlük indeksi ($p$), ayırt edicilik indeksi ($D$), çeldirici dağılımı, **KR-20 güvenilirlik katsayısı**, çok sekmeli Excel (`.xlsx`), CSV, JSON ve öğrenci bazlı **PDF Sınav Karnesi**.
- **Web Studio (`omrkit studio`):** Tarama + HITL inceleme, HTML5 Canvas üzerinde sürükle-bırak görsel şablon tasarımcısı, canlı PDF form üreteci ve analitik paneli.

---

## Hızlı Başlangıç

```bash
git clone https://github.com/duhanguler/omr.git
cd omr
pip install -e ".[all]"
```

### 1. Türkçe 50 Soruluk Optik Form + Şablon Üret

```bash
omrkit generate --preset turkish_exam_50 -o deneme_sinavi
```

### 2. Gerçek Türkçe Telefon Fotoğraflarını Tara ve Puanla

```bash
omrkit scan examples/turkish_exam_50q/scans \
  -t examples/turkish_exam_50q/template.json \
  -k examples/turkish_exam_50q/answer_key.json \
  --policy yks_tyt \
  --format csv,json,xlsx,scorecards \
  -o outputs/turkish_demo
```

### 3. Görsel Web Studio ve REST API’yi Başlat

```bash
omrkit studio
# Web Studio:   http://127.0.0.1:8000
# OpenAPI Docs: http://127.0.0.1:8000/docs
```

Docker ile tek komutta çalıştırmak için:

```bash
docker compose up
```

---

## Gizlilik & EXIF Temizliği

Telefonla çekilen optik form fotoğraflarını paylaşmadan veya test setine eklemeden önce GPS/cihaz bilgisini silmek ve yönü sabitlemek için yerleşik aracı kullanabilirsiniz:

```bash
omrkit strip-exif ham_fotograflar/ -o temiz_fotograflar/
```

---

## Lisans

[MIT Lisansı](LICENSE) altında açık kaynak olarak sunulmaktadır.
