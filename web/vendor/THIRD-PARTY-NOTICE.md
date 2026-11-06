# web/vendor/ — Üçüncü Parti Varlık Notu

> Local-First: tüm üçüncü parti varlıklar yerel yaşar; dış CDN bağımlılığı yok.
> Bu dizin dışarıdan indirilen **değiştirilmemiş** dağıtım dosyalarını tutar.

| Dosya | Kütüphane | Sürüm | Lisans | Kaynak |
|---|---|---|---|---|
| `chart.umd.min.js` | Chart.js | 4.6.1 | MIT | https://cdn.jsdelivr.net/npm/chart.js — indirme 2026-11-05 |
| `alpine.cdn.min.js` | Alpine.js | 3.x | MIT | https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js — indirme 2026-11-05 |
| Google Fonts (Inter / JetBrains Mono) | — | — | OFL | **Kaldırıldı** — sistem font-stack kullanılıyor; Inter/JetBrains Mono kuruluysa yerel olarak seçilir |

## Yenileme talimatı

```bash
curl -sL -o web/vendor/chart.umd.min.js "https://cdn.jsdelivr.net/npm/chart.js"
curl -sL -o web/vendor/alpine.cdn.min.js "https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"
# sürüm parametresini index.html'deki ?v= ile eşitle
```

## Lisans metinleri

Chart.js ve Alpine.js MIT lisansı kullanır. Kısa özet:

> Permission is hereby granted, free of charge, to any person obtaining a copy of
> this software and associated documentation files (the "Software"), to deal in
> the Software without restriction, including without limitation the rights to
> use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
> of the Software, subject to the copyright notice inclusion requirement.

Tam metinler: github.com/chartjs/Chart.js (LICENSE) ve github.com/alpinejs/alpine
(LICENSE). Google Fonts OFL metni: openfontlicense.org.

---
*Not: `tools/vendor/` .gitignore desenine girmez; `web/vendor/` ayrı ağaçtır ve
vendor dosyaları commit'lenir.*
