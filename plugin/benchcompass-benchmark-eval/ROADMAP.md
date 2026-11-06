# LLMFit Benchmark Eval — Yol Haritası (ROADMAP)

> Bu doküman, plugin'in geliştirme yolunu tanımlar. **Sonraki geliştirmeler burada
> yazılan fazlar üzerinden yürütülür.** Her fazın kabul kriterleri ve kanıt
> komutları aşağıdadır. Geliştirme yapan ajanların (agent) bu dokümanı okuyup
> fazları sırayla takip etmesi beklenir.

Motto: *"Kanıt veya geri al."*

## Durum

| Faz | Başlık | Durum |
|---|---|---|
| Faz 0 | Plugin iskeleti & manifest | ✅ Tamam |
| Faz 1 | Harness portu (config + suite JSON) | ✅ Tamam |
| Faz 2 | Veri çözümleyici + TR suite + sonuç birleştirme | ✅ Tamam |
| Faz 3 | MD rapor üretici (EN+TR matris) | ✅ Tamam (üretici hazır; sonuç koşusu bekliyor) |
| Faz 4 | HTML interaktif rapor (hybrid chart) | ✅ Tamam (üretici hazır; sonuç koşusu bekliyor) |
| Faz 5 | Dashboard entegrasyonu (menü + iframe) | ✅ Tamam |
| Faz 6 | Tam otomatik pipeline + SQLite geçmiş | ✅ Tamam (koşu + rapor son adım) |
| Faz 7 | Testler + G1–G7 doğrulama | ✅ Tamam (plugin 25 test; repo kapıları pre-existing sapmalar) |
| Faz 8 | Genişletme (quant, context, vision/RAG, tam TR) | ✅ Tamam (Sprint 27 B1-B5) |

---

## Faz 0 — Plugin iskeleti & manifest ✅

**Yapılanlar:**
- `plugin/benchcompass-benchmark-eval/` klasör hiyerarşisi
- `plugin.json` manifest (bağımsız çalışma garantisi, entegrasyon noktaları)
- `README.md` (standalone + entegrasyon rehberi)
- `pyproject.toml` (bağımsız paket)

**Kabul:** `plugin.json` şemaya uygun; README başka projeye kurulumu anlatıyor.

## Faz 1 — Harness portu

**Hedef:** `scratch/benchmark_ollama.py`'nin olgunlaştırılmış hali plugin'e taşınır.

- [ ] `eval/config.py`: koşullar (runs, temperature, num_predict, think, keep_alive, Ollama URL) — Y17: koda sabitlenmez, config/suiteden gelir
- [ ] `eval/grading.py`: num/word/code + think-strip + accept-list (grading kuralları, network yok)
- [ ] `eval/harness.py`: Ollama REST — `measure_speed` (tok/s, prefill, bayt-bayt TTFT), `generate`
- [ ] `tasks/suite_default.json`: 24 EN görev (metadata: kategori, zorluk, dil)
- [ ] `eval/runner.py`: değerlendirme akışı (per-model speed+quality, checkpoint)
- [ ] `scripts/run_benchmark.py`: CLI (models, suites, no-speed, no-quality, json-out)

**Kabul:** `python -m benchcompass_benchmark_eval.scripts.run_benchmark --models <model> --no-quality` tek modelde koşar; JSON üretir.

## Faz 2 — Veri çözümleyici + TR suite + sonuç birleştirme

**Hedef:** Plugin bağımsız koşabilir ama llmfit verisini de kullanabilir.

- [ ] `eval/llmfit_data.py` — çözümleme sırası:
      1. `--llmfit-data-dir` / otomatik: parent `data/` (hf_models.json, benchmark_cache.json)
      2. plugin `data/llmfit_snapshot_*.json`
      3. yok → llmfit verisi olmadan çalış (graceful)
- [ ] `data/hardware.json` — donanım + runtime + koşullar
- [ ] `tasks/suite_tr.json` — 8+ Türkçe görev (aritmetik/mantık/talimat/bilgi)
- [ ] `data/results_2026-08-04.json` — bugünkü ölçümlerin birleştirilmiş hali
- [ ] `data/llmfit_snapshot_*.json` — llmfit 12GB altı katalog + RTX 4070 Ti/3060 preset özeti
- [ ] `scripts/extract_llmfit_snapshot.py` — parent `data/`'dan snapshot üreten yardımcı

**Kabul:** `test_llmfit_data.py` 3 modu (parent/snapshot/yok) network'süz test eder.

## Faz 3 — MD rapor üretici

- [ ] `scripts/generate_md.py` — `results_*.json` + `hardware.json` + (varsa) llmfit snapshot → `reports/index.md`
- [ ] Bölümler: Yöntem & Koşullar / Görev Matrisi (EN+TR) / Sonuçlar / Per-model per-task pass-fail / Analiz (hız, kalite, verimlilik, varyans) / İyileştirmeler / Community karşılaştırma
- [ ] Deterministik üretim (aynı girdi = aynı çıktı)

**Kabul:** `generate_md.py` çalışır, `index.md` EN+TR görevleri içerir.

## Faz 4 — HTML interaktif rapor

- [ ] `scripts/generate_html.py` — veri JSON'a gömülür (self-contained)
- [ ] Hybrid grafik: Chart.js CDN denenir → yoksa elle SVG/Canvas fallback
- [ ] Bölümler: Genel Bakış / Testler & Koşullar / Sonuçlar (sıralanabilir+filtre) / Grafikler / İyileştirmeler / Veri
- [ ] Dashboard estetiği (dark terminal, renk değişkenleri)

**Kabul:** `reports/index.html` internet olsa da olmasa da grafik gösterir.

## Faz 5 — Dashboard entegrasyonu

- [ ] `api/main.py`: `REPORTS_DIR` + `app.mount("/eval-reports", NoCacheStaticFiles(...), name="eval-reports")`
- [ ] `web/index.html`: nav'a `[ RAPOR ]` butonu → `view='rapor'`; iframe bölümü
- [ ] `api/compat.py`, `api/db.py`, `config/*.json` **dokunulmaz**

**Kabul:** Dashboard açıkken `[ RAPOR ]` sekmesi iframe ile interaktif raporu gösterir.

## Faz 6 — Tam otomatik pipeline + SQLite geçmiş

- [ ] `run_benchmark.py --pipeline`: koş → JSON → SQLite `benchmarks` INSERT (`source='plugin-eval'`) → md → html
- [ ] SQLite yolu çözümleyici gibi: parent `benchmark_history.db` yoksa atla
- [ ] `run.py` kök başlatıcı

**Kabul:** `--pipeline` tek komutla tüm çıktıları üretir; `benchmarks` tablosuna kayıt düşer (entegre modda).

## Faz 7 — Testler + doğrulama

- [ ] `tests/test_grading.py` (EN+TR, network yok)
- [ ] `tests/test_llmfit_data.py` (3 mod)
- [ ] `tests/test_reports.py` (md/html deterministik)
- [ ] `tests/test_runner.py` (mock Ollama)
- [ ] G1 ruff · G3 mypy · G4 pytest · G7 verify_completion
- [ ] ADR + CHANGELOG

**Kabul:** İlgili kapılar taze yeşil (mevcut mesajda terminal çıktısı).

## Faz 8 — Genişletme ✅ (Sprint 27 B1-B5)

- [x] **Çoklu quant (B1):** aynı modelin Q4_K_M vs Q8_0 karşılaştırması — `harness.model_quant`/`model_family` + `runner.quant_comparison`; MD+HTML rapor bölümü. `--models qwen3:8b-q4_K_M qwen3:8b-q8_0` ile otomatik tetiklenir.
- [x] **Context stres (B2):** needle-in-haystack — `harness.context_stress` (32K/64K/128K, `num_ctx` ayarı, recall + prefill tok/s); `--context-stress 32k,64k,128k`; MD+HTML rapor bölümü.
- [x] **Tam TR suite (B3):** `suite_tr.json` 12 → 24 görev; dil bazlı skor kırılımı `grading.summarize_by_lang` (EN/TR ayrı skor rapor tablolarında).
- [x] **Vision (B4):** `suite_vision.json` + `harness.synthetic_png` (stdlib PNG üretici) + `generate_vision`; minicpm-v/Qwen3-VL için renk/mekansal görevler.
- [x] **Embedding / RAG (B4):** `harness.embed` + `cosine` + `runner.retrieval_test` (sorgu-doğru-doküman eşleşmesi); `--retrieval`; MD+HTML rapor bölümü.
- [x] **Community karşılaştırma panosu (B5):** `_match_community` gevşek eşleşme ile yerel ölçüm vs llmfit benchmark_cache; MD+HTML pano.
- [x] **Geçmiş arşiv / zaman serisi (B5):** `history.py` — parent benchmark_history.db'den per-model trend (yükseliyor/düşüyor/sabit); MD+HTML rapor bölümü.

---

## Kalıcı ilkeler (agent'lara not)

1. **Bağımsız çalışabilirlik kırılamaz:** plugin, parent proje verisi olmadan da koşar.
2. **Veri koda gömülmez:** görevler `tasks/*.json`, koşullar `config.py`, eşikler rapor üretici parametreleri.
3. **Dokümantasyon önceliklidir:** her anlamlı değişiklik → CHANGELOG + gerekirse ROADMAP/ADR güncellemesi.
4. **Yorumlar Türkçe, kod İngilizce, commit mesajları Türkçe (conventional).**
5. **Rapor üreticiler deterministik olmalı** (aynı veri → aynı çıktı).
