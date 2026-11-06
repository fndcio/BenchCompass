# docs/DATA_SOURCES.md — Veri kaynakları

| Dosya | Kaynak | Lisans | Çekim |
|---|---|---|---|
| `data/hf_models.json` | llmfit catalog snapshot (HuggingFace metadata) | MIT (llmfit) | fetch script |
| `data/benchmark_cache.seed.json` | llmfit leaderboard snapshot, strip (user/prompt/output/notes yok) | MIT (llmfit) | seed script |
| `data/baselines.json`, `data/use_case_benchmarks.json` | llmfit baseline / toplanan public leaderboard özetleri | MIT (llmfit) | fetch script |

Notlar:
- Model adları/sürümleri ilgili sahiplerinin markasıdır; ağırlık içermez.
- Seed dosyadaki skorlar resmi leaderboard skoru değildir; relative güçlüklü olur.
- Kaldırma talepleri GitHub issue ile vsrilse incelenir.
- Topluluk kullanıcı katkıları (user/prompt/output) seed'de yer almaz.
