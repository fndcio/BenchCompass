# docs/DEVELOPMENT.md — Geliştirme notları

## Gereksinimler

- Python >= 3.11, Node/npm (Vitest), Playwright (E2E)

## Testler

```powershell
python -m pytest tests/unit tests/integration -q
npm test
```

## Stil ve lint

```powershell
ruff check .
ruff format --check .
```

## Veri

- `benchmark_history.db` yerelde oluşur; repoya girmez.
- Seed: `data/benchmark_cache.seed.json`; tam leaderboard snapshot runtime'da `scripts/fetch_benchcompass_data.py` ile çekilir.
