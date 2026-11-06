# BenchCompass

Local LLM hardware benchmark — donanıma duyarlı, kalıcı SQLite destekli yerel panel.

Bu proje `fndcio` tarafından geliştirilen **bağımsız** bir projedir.
Alex Jones veya llmfit projesiyle resmi bağlantısı yoktur; `llmfit` adı
yalnızca veri uyumluluğunu tanımlamak için kullanılır.

## Hızlı Başlatma

```powershell
pip install -r requirements.txt
npm install
open-all.cmd
```

Tarayıcıda `http://localhost:8788` açılır.

Bu panel-local-first çalışır: veriler yerelde yaşar.
Bulut telemetrisi varsayılan olarak kapalıdır.

## Özellikler

- Donanım profiline duyarlı tier/uyumluluk motoru
- SQLite kalıcılığı (`benchmark_history.db`)
- Model kataloğu ve benchmark skorları
- Yerel model değerlendirme aracı (plugin)
- Donanım simülatörü ve karar matriksi / profil önerisi
- Enerji ve kalibrasyon özetleri
- Modeller arası karşılaştırmalı hız/kalite görünümü

## Mimari (genel)

Flat layout — backend `api/`, veri collector kökte, frontend `web/`'de statik,
eklenti `plugin/` altında.

## Lisans ve Teşekkür

- BenchCompass kodu: MIT — `Copyright (c) 2026 fndcio` (bkz. `LICENSE`).
- Veri uyumluluğu: [AlexsJones/llmfit](https://github.com/AlexsJones/llmfit) (MIT, `Copyright (c) 2026 Alex Jones`).
  Veri dosyaları upstream'den alınır ve "AS IS" sağlanır; detay `data/NOTICE.md` ve `docs/DATA_SOURCES.md`.
- Frontend bileşenleri: Chart.js ve Alpine.js (MIT). Tam metinler `web/vendor/` altında.
- Tier/uyumluluk motoru bu projeye özgündür; llmfit kodundan kopyalanmamıştır.

Model adları/sürümleri ilgili sahiplerinin markasıdır; ağırlık dosyası içermez.
