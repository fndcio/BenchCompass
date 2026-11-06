"""BenchCompass — FastAPI backend paketi.

Sprint 3 ile gelen moduler:
  - schemas.py      : Pydantic modelleri (frontend/backend kontrat)
  - compat.py       : Sayisal uyumluluk motoru (Bolum 2.2 tier formulu)
  - db.py           : SQLite baglantisi + geri-donuk-uyumlu sema migrasyonu
  - notes_parser.py : llmfit 'notes' metninden yapilsal alan cikarma (regex)
  - main.py         : Dashboard API (port 8788)
  - collector_api.py: Collector kontrol API (port 8790)
  - i18n.py         : Ceviri katalogu (ADR-0009)
"""

__all__ = ["schemas", "compat", "db", "notes_parser", "main", "collector_api", "i18n"]
