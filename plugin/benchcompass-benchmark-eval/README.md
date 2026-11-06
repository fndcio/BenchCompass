# LLMFit Benchmark Eval — Plugin

Ollama üzerinde çalışan **yerel model değerlendirme aracı**. İki boyutta ölçer:

1. **Hız:** tok/s (generation), tok/s (prefill), TTFT (ilk token süresi), model yükleme süresi
2. **Kalite:** elle doğrulanabilir cevaplı görev suite'i (aritmetik, mantık, kod üretimi+exec, talimat takibi) — **EN** (24 görev) + **TR** (Türkçe görevler)

Çıktılar: **detaylı MD rapor** + **interaktif HTML rapor** (offline, hybrid grafik).

> Bu plugin **tamamen bağımsızdır**: başka bir projeye kopyalanıp çalıştırılabilir.
> benchcompass içindeyken parent projenin `data/` (hf_models, benchmark_cache)
> verisini **ek zenginlik** olarak okur; yoksa zarifçe atlar.

---

## Hızlı başlangıç (standalone)

```powershell
cd plugin\benchcompass-benchmark-eval
python -m benchcompass_benchmark_eval.scripts.run_benchmark --pipeline
```

Bu komut:
1. Kurulu Ollama modellerini koşturur (hız + kalite)
2. Sonuçları `data/results_<tarih>.json`'a yazar
3. `benchmark_history.db`'deki `benchmarks` tablosuna `source='plugin-eval'` ile ekler (entegre modda)
4. `reports/index.md` ve `reports/index.html` üretir

> ⚠️ Ollama çalışıyor olmalı (`ollama serve` / Ollama app açık, port 11434).

## Seçenekler

```powershell
# Belirli modeller
python -m benchcompass_benchmark_eval.scripts.run_benchmark --models qwen3:8b gemma4:12b

# Sadece hız / sadece kalite
python -m benchcompass_benchmark_eval.scripts.run_benchmark --no-quality
python -m benchcompass_benchmark_eval.scripts.run_benchmark --no-speed

# Görev suite'leri (EN + TR)
python -m benchcompass_benchmark_eval.scripts.run_benchmark --suites suite_default,suite_tr

# Çoklu quant karşılaştırma (B1): aynı ailenin farklı quant'ları
python -m benchcompass_benchmark_eval.scripts.run_benchmark --models qwen3:8b-q4_K_M qwen3:8b-q8_0

# Context stres testi (B2): needle-in-haystack 32K/64K/128K
python -m benchcompass_benchmark_eval.scripts.run_benchmark --context-stress 32k,64k,128k

# Vision görevleri (B4): görüntülü modeller için (minicpm-v, Qwen3-VL)
python -m benchcompass_benchmark_eval.scripts.run_benchmark --suites suite_vision

# Embedding retrieval kalitesi (B4)
python -m benchcompass_benchmark_eval.scripts.run_benchmark --retrieval

# Sadece rapor üret (mevcut sonuçtan, benchmark yapmadan)
python -m benchcompass_benchmark_eval.scripts.generate_md --input data/results_2026-08-04.json
python -m benchcompass_benchmark_eval.scripts.generate_html --input data/results_2026-08-04.json
```

## Klasör yapısı

```
benchcompass-benchmark-eval/
├── plugin.json                  # manifest (entegrasyon noktaları, bağımsız çalışma)
├── README.md                    # bu dosya
├── ROADMAP.md                   # geliştirme yol haritası
├── pyproject.toml               # bağımsız paket bildirimi
├── run.py                       # kolay başlatıcı (python run.py --pipeline)
└── benchcompass_benchmark_eval/       # Python paketi (underscore = import edilebilir)
    ├── config.py                # koşullar (donanım, tekrar, sıcaklık, vb.)
    ├── grading.py               # görev değerlendirme kuralları
    ├── harness.py               # Ollama REST istemcisi (hız ölçümü)
    ├── llmfit_data.py           # veri çözümleyici (parent data/ → snapshot → yok)
    ├── runner.py                # değerlendirme akışı
    ├── tasks/                   # görev suite'leri (JSON — koda gömülü değil)
    │   ├── suite_default.json   # EN: 24 görev
    │   └── suite_tr.json        # TR: Türkçe görevler
    ├── scripts/
    │   ├── run_benchmark.py     # CLI entrypoint (koş → JSON → SQLite → raporlar)
    │   ├── generate_md.py       # JSON → index.md
    │   └── generate_html.py     # JSON → index.html
    ├── data/
    │   ├── hardware.json        # test koşulları
    │   ├── results_*.json       # koşu sonuçları (append-only, tarihli)
    │   └── llmfit_snapshot_*.json  # llmfit verisi önbelleği (standalone mod)
    ├── reports/
    │   ├── index.md             # detaylı rapor (otomatik üretilir)
    │   └── index.html           # interaktif rapor (otomatik üretilir)
    └── tests/                   # pytest (network yok: mock/grading)
```

## Başka bir projeye entegrasyon (plugin olarak)

1. `plugin/benchcompass-benchmark-eval/` klasörünü hedef projeye kopyala.
2. Hedef projede:
   ```powershell
   cd plugin\benchcompass-benchmark-eval
   python -m benchcompass_benchmark_eval.scripts.run_benchmark --pipeline
   ```
3. Raporları hedef projeye göm: `reports/index.html`'i static dosya olarak serve et (ör. FastAPI `StaticFiles` mount).

### FastAPI'de raporu mount etme (örnek)

```python
from fastapi.staticfiles import StaticFiles
app.mount("/eval-reports", StaticFiles(directory="plugin/benchcompass-benchmark-eval/reports", html=False))
```

Ardından tarayıcıda `/eval-reports/index.html` açılır.

### llmfit verisi entegrasyonu (isteğe bağlı)

Plugin, `llmfit_data.py` üzerinden sırasıyla şunları arar:
1. `--llmfit-data-dir <proje>/data` (veya otomatik: parent proje `data/` içinde `hf_models.json` varsa)
2. Plugin kendi `data/llmfit_snapshot_*.json` önbelleği
3. Yoksa → llmfit verisi olmadan çalışır

Bu sayede **aynı `data/` klasörünü** paylaşabilir (entegre mod) ama **bağımsız da** koşar (standalone mod).

## Raporlar hakkında

- **`index.md`**: Yöntem & koşullar, 24+TR görev matrisi, per-model per-task pass/fail, hız/kalite/verimlilik analizi, iyileştirme önerileri, community karşılaştırması.
- **`index.html`**: Self-contained. Grafikler **hybrid**: Chart.js CDN'i dener, internet yoksa elle SVG/Canvas çizime düşer. Bölümler: Genel Bakış / Testler & Koşullar / Sonuçlar / Grafikler / İyileştirmeler / Veri.

## Testler

```powershell
cd plugin\benchcompass-benchmark-eval
python -m pytest -m "not integration and not e2e" --tb=short
```

Yol notu: testler `benchcompass_benchmark_eval/tests/` altındadır ve `pyproject.toml`
`testpaths` bunu gösterir — bu yüzden argümansız `python -m pytest` doğru komuttur
(`pytest tests` **FileNotFoundError** verir; 7 Ekim 2026'da yaşandı).

Grading, veri çözümleyici ve rapor üretimi **network olmadan** test edilir (mock Ollama).
