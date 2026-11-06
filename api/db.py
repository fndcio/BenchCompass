"""SQLite baglantisi + geri-donuk-uyumlu sema migrasyonu + backfill.

TASARIM:
- Tek bir connect() gercek bir sqlite3.Connection dondurur (row_factory ayarli).
- connect() her cagrildiginda CREATE TABLE IF NOT EXISTS calistirir (mevcut
  tablolar korunur) ve migrate() ile eksik sutunlari ALTER TABLE ADD COLUMN
  ile ekler. SQLite 'ADD COLUMN IF NOT EXISTS' desteklemedigi icin once
  PRAGMA table_info ile mevcut sutunlari kontrol ederiz.
- backfill_from_notes(): mevcut 112 satirin notes metninden yeni sutunlari
  doldurur. Bir kez calistirilir; idempotent (tekrar calistirilirsa sadece
  NULL kalanlari gunceller).

KRITIK: Mevcut veri ASLA silinmez. Migrasyon sadece ekleme yapar.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .notes_parser import enrich_model

BASE = Path(__file__).resolve().parent.parent  # benchcompass/
DB = BASE / "benchmark_history.db"

# Orijinal sema (Sprint 3 oncesi) — hala IF NOT EXISTS ile yaratilir.
SCHEMA_BASE = """
CREATE TABLE IF NOT EXISTS benchmark_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT,
  source TEXT,
  use_case TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS benchmark_models (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  name TEXT,
  provider TEXT,
  use_case TEXT,
  fit_score REAL,
  context_window INTEGER,
  notes TEXT,
  FOREIGN KEY(run_id) REFERENCES benchmark_runs(id)
);
"""

# Sprint 3 ile eklenen sutunlar. (sutun_adi, SQL tipi) ikilileri.
# Eklenti sirasi onemli degil; IF NOT EXISTS mantigi PRAGMA ile yapilir.
NEW_COLUMNS: list[tuple] = [
    ("required_vram_gb", "REAL"),
    ("required_ram_gb", "REAL"),
    ("context_length_supported", "INTEGER"),
    ("context_length_estimated_at", "INTEGER"),
    ("quantization", "TEXT"),
    ("param_count_b", "REAL"),
    ("estimated_speed_tok_s", "REAL"),
    # Sprint 7: llmfit CLI first-class alanlari
    ("fit_level", "TEXT"),  # llmfit: "Perfect" / "Good" / "Warning" / "Bad"
    ("is_moe", "INTEGER"),  # 0/1 — Mixture of Experts flag
    ("capabilities", "TEXT"),  # virgulle ayrilmis: "Tool Use,Vision"
    ("disk_size_gb", "REAL"),  # gguf dosya boyutu
    ("llmfit_score", "REAL"),  # llmfit'in score alani (fit_score'tan farkli olabilir)
    # Sprint 12: llmfit run_mode (GPU/CPU_offload/CPU)
    ("run_mode", "TEXT"),  # GPU / CPU_offload / CPU / Mixed
]

# Sprint 9: yeni tablolar (yardimci veriler)
SCHEMA_SPRINT9 = """
CREATE TABLE IF NOT EXISTS benchmarks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  model TEXT NOT NULL,
  provider TEXT,
  measured_tps REAL,
  ttft_ms REAL,
  total_tokens INTEGER,
  wall_clock_s REAL,
  shared INTEGER DEFAULT 0,
  error TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  source TEXT,
  tps_kaynagi TEXT,
  trust TEXT,
  -- P1-2 (04.11.2026, kullanıcı onayı): BENCHCOMPASS_YOL_HARITASI.md P1-2 kapsamında
  -- eklendi — tahmin/ölçüm kalibrasyon sütunları (idempotent ALTER: BENCH_COLUMNS).
  predicted_tps REAL,
  prediction_delta_pct REAL,
  -- Adım 2 (06.11.2026, §9.3 onayı A): SSE streaming TTFT/ITL kalıcılığı
  -- (idempotent ALTER: BENCH_COLUMNS).
  itl_ms REAL,
  ttft_method TEXT
);
CREATE TABLE IF NOT EXISTS downloaded_models (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  repo TEXT NOT NULL,
  model TEXT,
  quant TEXT,
  path TEXT,
  size_gb REAL,
  sha256 TEXT,
  downloaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
  installed INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS running_servers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pid INTEGER,
  port INTEGER,
  model TEXT,
  endpoint TEXT,
  started_at TEXT DEFAULT CURRENT_TIMESTAMP,
  stopped_at TEXT
);
CREATE TABLE IF NOT EXISTS background_tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  uuid TEXT UNIQUE NOT NULL,
  type TEXT NOT NULL,
  status TEXT DEFAULT 'pending',
  progress INTEGER DEFAULT 0,
  result TEXT,
  error TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  completed_at TEXT
);
"""


# Sprint 23: benchmarks tablosuna eklenecek kolonlar (real/community ayrımı)
BENCH_COLUMNS: list[tuple] = [
    ("source", "TEXT"),
    ("predicted_tps", "REAL"),  # P1-2: tahmin edilen tok/s
    ("prediction_delta_pct", "REAL"),  # P1-2: (olculen - tahmin) / tahmin * 100
    # Gece otonomu 2026-10-06 (denetim raporu 2026-10-05 §2/§5.1-3): 97 hız
    # kaydında 3 farklı tps metodolojisi karışıyordu (eval_duration / usage /
    # char_tahmin); "hız şampiyonu" gibi karar iddiaları yalnız trust='good'
    # kayıtlardan üretilir. Etiket: scripts/label_speed_trust.py (kuru koşu + --apply).
    ("tps_kaynagi", "TEXT"),  # eval_duration | usage | char_tahmin | NULL=bilinmiyor
    ("trust", "TEXT"),  # good | suspect | invalid | NULL=etiketsiz
    # Adım 2 (06.11.2026, §9.3 onayı A): SSE streaming ölçümleri
    ("itl_ms", "REAL"),  # chunk-arası geçen süre ortancası (p50)
    ("ttft_method", "TEXT"),  # streaming | measured | estimated | simulated
]

# ---------------------------------------------------------------------------
# Kalite katmanı (7 Ekim 2026, kullanıcı onaylı additive tablo)
# ---------------------------------------------------------------------------
# Denetim bulgusu: kodlama değerlendirmesinin KALİTE boyutu (Pass@1/Pass@N,
# visible/hidden) hiçbir kalıcı veriye girmiyordu — `benchmarks` yalnız hız
# (tok/s) tutar, skor kolonu yok. Sonuçlar markdown + elle küratörlü panel
# metninde yaşıyordu; trend/sorgu/izlenebilirlik mümkün değildi.
# Çözüm: mevcut şemaya/kolonlara DOKUNMAYAN yeni tablo (additive migration,
# AGENTS.md §9.3 kullanıcı onayı alındı). Doldurma: scripts/insert_quality_results.py.
SCHEMA_QUALITY = """
CREATE TABLE IF NOT EXISTS benchmark_quality (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  model TEXT NOT NULL,
  gorev TEXT NOT NULL,
  dil TEXT,
  deneme INTEGER,
  visible INTEGER,
  hidden INTEGER,
  pass1 INTEGER,
  passN INTEGER,
  attempts INTEGER,
  tg REAL,
  tg_kaynagi TEXT,
  tokens INTEGER,
  finish TEXT,
  thinking TEXT,
  harness_sha TEXT,
  seed INTEGER,
  source TEXT,
  gecerlilik TEXT,
  notlar TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_quality_model ON benchmark_quality(model);
CREATE INDEX IF NOT EXISTS idx_quality_gorev ON benchmark_quality(gorev, dil);
"""

# Sprint 53 / ADR-0012: Zero-Config Yerel GGUF Model Keşif Önbelleği
SCHEMA_LOCAL_MODELS = """
CREATE TABLE IF NOT EXISTS local_models_cache (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  file_path TEXT UNIQUE NOT NULL,
  file_name TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  size_gb REAL NOT NULL,
  mtime REAL NOT NULL,
  architecture TEXT,
  quant_type TEXT,
  context_length INTEGER,
  general_name TEXT,
  tensor_count INTEGER,
  vram_required_gb REAL,
  fit_level TEXT,
  last_scanned TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_local_models_path ON local_models_cache(file_path);
"""

# benchmark_quality için sonradan eklenen kolonlar (additive, idempotent).

# benchmark_quality için sonradan eklenen kolonlar (additive, idempotent).
# `gecerlilik`: ölçüm geçerliliği etiketi (trust kolonu deseniyle aynı
# yaklaşım — geçersiz ölçüm SİLİNMEZ, etiketlenir ki metodoloji karışmasın).
QUALITY_COLUMNS: list[tuple] = [
    ("gecerlilik", "TEXT"),  # gecerli | artefakt-g7 | NULL
    ("notlar", "TEXT"),
]


# P1-3: Çift-Kör Arena ve Elo Tabloları
# (04.11.2026, kullanıcı onayı): BENCHCOMPASS_YOL_HARITASI.md P1-3 kapsamında eklendi.
SCHEMA_ARENA = """
CREATE TABLE IF NOT EXISTS arena_elo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model TEXT UNIQUE NOT NULL,
    elo REAL NOT NULL DEFAULT 1000.0,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    draws INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS arena_duels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_a TEXT NOT NULL,
    model_b TEXT NOT NULL,
    winner TEXT,
    prompt_hash TEXT,
    tps_a REAL,
    tps_b REAL,
    ttft_a_ms REAL,
    ttft_b_ms REAL,
    blind_mode INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_arena_duels_models ON arena_duels(model_a, model_b);
"""


# Adım 4 (06.11.2026, §9.3 onayı): eşzamanlılık stres sonuçları
SCHEMA_CONCURRENT = """
CREATE TABLE IF NOT EXISTS concurrency_benchmarks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  model TEXT NOT NULL,
  backend TEXT,
  concurrency INTEGER NOT NULL,
  latency_p50_ms REAL,
  latency_p95_ms REAL,
  latency_p99_ms REAL,
  ttft_p50_ms REAL,
  ttft_p95_ms REAL,
  throughput_tps REAL,
  queue_effect_pct REAL,
  success INTEGER DEFAULT 0,
  errors INTEGER DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_concurrent_model ON concurrency_benchmarks(model);
"""


def connect() -> sqlite3.Connection:
    """Tablolari yaratir, eksik sutunlari ekler, hazir bir baglanti dondurur.

    Bu fonksiyon thread-safe degildir (FastAPI/uvicorn default olarak her
    istek icin yeni bir baglanti acar; biz de her endpoint call'inda connect()
    cagirip kapatiyoruz). long-lived connection istenirse ayri bir pool lazim.
    """
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA_BASE)
    con.executescript(SCHEMA_SPRINT9)  # Sprint 9 yeni tablolar
    con.executescript(SCHEMA_QUALITY)  # 7 Ekim 2026: kalite (Pass@N) katmanı
    con.executescript(SCHEMA_LOCAL_MODELS)  # ADR-0012: Zero-Config GGUF önbelleği
    con.executescript(SCHEMA_ARENA)  # P1-3: Çift-Kör Arena ve Elo
    con.executescript(SCHEMA_CONCURRENT)  # Adım 4: eşzamanlılık stresi
    migrate(con)
    return con


def migrate(con: sqlite3.Connection) -> list[str]:
    """Eksik sutunlari ALTER TABLE ile ekler.

    Hem benchmark_models (NEW_COLUMNS) hem de benchmarks (BENCH_COLUMNS)
    tablosunu kapsar. Donus: eklenen sutunlarin listesi (zaten var olanlari
    tekrar eklemez). Idempotent: tekrar cagrildiginda bos liste doner.
    """
    existing = {
        row["name"]
        for row in con.execute("PRAGMA table_info(benchmark_models)").fetchall()
    }
    added = []
    for col, sql_type in NEW_COLUMNS:
        if col not in existing:
            con.execute(f"ALTER TABLE benchmark_models ADD COLUMN {col} {sql_type}")
            added.append(col)

    bench_cols = {
        row["name"] for row in con.execute("PRAGMA table_info(benchmarks)").fetchall()
    }
    for col, sql_type in BENCH_COLUMNS:
        if col not in bench_cols:
            con.execute(f"ALTER TABLE benchmarks ADD COLUMN {col} {sql_type}")
            added.append(f"benchmarks.{col}")

    # benchmark_quality de aynı desene tabidir: tablo önce yaratılır
    # (SCHEMA_QUALITY, IF NOT EXISTS), sonra eksik kolonlar ALTER ile eklenir.
    # Tablo hiç yoksa (kısmi şema / izole test DB'si) atlanır — migrate()
    # mevcut olmayan tabloya ALTER etmeye çalışıp patlamamalıdır.
    kalite_var = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='benchmark_quality'"
    ).fetchone()
    if kalite_var:
        kalite_cols = {
            row["name"]
            for row in con.execute("PRAGMA table_info(benchmark_quality)").fetchall()
        }
        for col, sql_type in QUALITY_COLUMNS:
            if col not in kalite_cols:
                con.execute(
                    f"ALTER TABLE benchmark_quality ADD COLUMN {col} {sql_type}"
                )
                added.append(f"benchmark_quality.{col}")

    if added:
        con.commit()
    return added


def backfill_from_notes(con: sqlite3.Connection) -> int:
    """NULL kalan yeni sutunlari 'notes' metninden doldurur.

    Strateji: required_vram_gb NULL olan tum satirlari alir, her birinin
    notes'unu parse eder ve UPDATE eder. Hata alinan bir satir atlanir,
    gerisi devam eder (Kriter #14 dayaniklilik).

    Donus: guncellenen satir sayisi.
    """
    rows = con.execute(
        "SELECT id, name, notes, required_vram_gb FROM benchmark_models "
        "WHERE required_vram_gb IS NULL"
    ).fetchall()
    updated = 0
    for r in rows:
        try:
            enriched = enrich_model(r["name"], r["notes"])
        except Exception:
            # Tek model patlarsa gerisini etkilemesin
            continue
        con.execute(
            """
            UPDATE benchmark_models
            SET required_vram_gb = ?,
                required_ram_gb = ?,
                context_length_supported = ?,
                context_length_estimated_at = ?,
                quantization = ?,
                param_count_b = ?,
                estimated_speed_tok_s = ?
            WHERE id = ?
            """,
            (
                enriched["required_vram_gb"],
                enriched["required_ram_gb"],
                enriched["context_length_supported"],
                enriched["context_length_estimated_at"],
                enriched["quantization"],
                enriched["param_count_b"],
                enriched["estimated_speed_tok_s"],
                r["id"],
            ),
        )
        updated += 1
    if updated:
        con.commit()
    return updated


def fetch_history(con: sqlite3.Connection, limit: int = 200) -> list[dict]:
    """Son N run'u, modelleriyle birlikte dondurur. Mevcut dashboard_server
    davranisini birebir korur — frontend hala ayni JSON'u alir, fazladan
    yapilsal alanlarla."""
    runs = con.execute(
        "SELECT id,name,source,use_case,created_at FROM benchmark_runs ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    out = []
    for run in runs:
        models = con.execute(
            "SELECT id,run_id,name,provider,"
            "use_case as useCase,"
            "fit_score as fitScore,context_window as contextWindow,notes,"
            "required_vram_gb,required_ram_gb,"
            "context_length_supported,context_length_estimated_at,"
            "quantization,param_count_b,estimated_speed_tok_s,"
            "fit_level,is_moe,capabilities,disk_size_gb,llmfit_score,"
            "run_mode "
            "FROM benchmark_models WHERE run_id=? "
            "ORDER BY fit_score DESC",
            (run["id"],),
        ).fetchall()
        out.append(
            {
                "id": run["id"],
                "name": run["name"],
                "source": run["source"],
                "use_case": run["use_case"],
                "created_at": run["created_at"],
                "models": [dict(m) for m in models],
            }
        )
    return out


def fetch_latest(con: sqlite3.Connection) -> dict:
    """En son run'u, modelleriyle birlikte dondurur."""
    hist = fetch_history(con, limit=1)
    if not hist:
        return {"source": "sqlite", "models": []}
    latest = hist[0]
    return {
        "source": latest.get("source") or "sqlite",
        "run": latest.get("name"),
        "models": latest.get("models", []),
    }


def insert_snapshot(
    con: sqlite3.Connection,
    name: str,
    source: str = "manual",
    use_case: str = "mixed",
) -> dict:
    """En son run'daki modelleri kopyalayarak yeni bir snapshot (run) olusturur.

    Mevcut dashboard_server.insert_snapshot davranisini birebir korur, fazladan
    yeni yapilsal sutunlari da kopyalar (geri donuk uyum).
    """
    latest = fetch_latest(con)
    models = latest.get("models", [])
    cur = con.execute(
        "INSERT INTO benchmark_runs(name,source,use_case) VALUES(?,?,?)",
        (name, source, use_case),
    )
    run_id = cur.lastrowid
    for m in models:
        con.execute(
            """
            INSERT INTO benchmark_models(
                run_id,name,provider,use_case,fit_score,context_window,notes,
                required_vram_gb,required_ram_gb,
                context_length_supported,context_length_estimated_at,
                quantization,param_count_b,estimated_speed_tok_s,
                fit_level,is_moe,capabilities,disk_size_gb,llmfit_score
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                run_id,
                m.get("name"),
                m.get("provider"),
                m.get("useCase") or m.get("use_case"),
                m.get("fitScore"),
                m.get("contextWindow"),
                m.get("notes"),
                m.get("required_vram_gb"),
                m.get("required_ram_gb"),
                m.get("context_length_supported"),
                m.get("context_length_estimated_at"),
                m.get("quantization"),
                m.get("param_count_b"),
                m.get("estimated_speed_tok_s"),
                m.get("fit_level"),
                1 if m.get("is_moe") else 0,
                m.get("capabilities"),
                m.get("disk_size_gb"),
                m.get("llmfit_score"),
            ),
        )
    con.commit()
    return {"ok": True, "run_id": run_id, "copied_models": len(models)}


def delete_runs(con: sqlite3.Connection, run_ids: list[int]) -> int:
    """Seçilen benchmark run'larını ve bağlı modellerini siler.

    Sprint 17 — history toplu/seçerek silme. Modeller benchmark_models.run_id
    üzerinden cascade edilir (FK yoksa manuel DELETE). Boş/var olmayan id'ler
    sessizce yok sayılır; 0 silme hata değildir.
    """
    ids = [int(i) for i in run_ids if i is not None]
    if not ids:
        return 0
    placeholders = ",".join("?" for _ in ids)
    con.execute(f"DELETE FROM benchmark_models WHERE run_id IN ({placeholders})", ids)
    cur = con.execute(f"DELETE FROM benchmark_runs WHERE id IN ({placeholders})", ids)
    con.commit()
    return cur.rowcount


def delete_all_runs(con: sqlite3.Connection) -> int:
    """Tüm benchmark run'larını ve modellerini siler. Toplam silinen run sayısı."""
    cur = con.execute("SELECT COUNT(*) FROM benchmark_runs")
    total = cur.fetchone()[0]
    con.execute("DELETE FROM benchmark_models")
    con.execute("DELETE FROM benchmark_runs")
    con.commit()
    return total


# ---------------------------------------------------------------------------
# Kalite katmanı (benchmark_quality) — 7 Ekim 2026
# ---------------------------------------------------------------------------
QUALITY_ALANLAR = (
    "model",
    "gorev",
    "dil",
    "deneme",
    "visible",
    "hidden",
    "pass1",
    "passN",
    "attempts",
    "tg",
    "tg_kaynagi",
    "tokens",
    "finish",
    "thinking",
    "harness_sha",
    "seed",
    "source",
    "gecerlilik",
    "notlar",
)


def insert_quality(con: sqlite3.Connection, kayit: dict) -> int:
    """Tek bir kalite (görev bazlı) kaydı ekler; eklenen satırın id'sini döner.

    Eksik alanlar NULL kalır — kayıt şekli harness'ın sonuç JSON'undan gelir
    (bkz. scripts/insert_quality_results.py). Şema değişmez (additive tablo).
    """
    degerler = [kayit.get(a) for a in QUALITY_ALANLAR]
    yer = ",".join("?" for _ in QUALITY_ALANLAR)
    cur = con.execute(
        f"INSERT INTO benchmark_quality ({','.join(QUALITY_ALANLAR)}) VALUES ({yer})",
        degerler,
    )
    con.commit()
    return int(cur.lastrowid or 0)


def insert_quality_cok(con: sqlite3.Connection, kayitlar: list[dict]) -> int:
    """Toplu kalite kaydı ekler (tek transaction). Eklenen satır sayısını döner."""
    satirlar = [[k.get(a) for a in QUALITY_ALANLAR] for k in kayitlar]
    if not satirlar:
        return 0
    yer = ",".join("?" for _ in QUALITY_ALANLAR)
    con.executemany(
        f"INSERT INTO benchmark_quality ({','.join(QUALITY_ALANLAR)}) VALUES ({yer})",
        satirlar,
    )
    con.commit()
    return len(satirlar)


def fetch_quality(con: sqlite3.Connection, limit: int = 500) -> list[dict]:
    """En yeni kalite kayıtlarını döner (panel/sekme tüketimi)."""
    rows = con.execute(
        "SELECT * FROM benchmark_quality ORDER BY id DESC LIMIT ?", (int(limit),)
    ).fetchall()
    return [dict(r) for r in rows]


def quality_summary(con: sqlite3.Connection) -> list[dict]:
    """Model bazlı kalite özeti: görev sayısı, Pass@1/Pass@N toplamı, ort. deneme.

    Panel "Kodlama Değerlendirmesi" sekmesinin veri kaynağıdır; skor uydurmaz,
    yalnız kayıtlı görev sonuçlarını toplar.

    **Kural:** `gecerlilik='artefakt-g7'` satırları özetten HARİÇ tutulur
    (6 Ekim harness artefaktı; bkz. lessons-learned-2026-10-07). Bu satırlar
    silinmez — `artefakt` sayacıyla ayrıca raporlanır ki geçersiz ölçüm geçerli
    veriyle karışmasın (trust kolonu deseni).
    """
    # Koşullu toplama (WHERE ile filtrelemek artefakt SAYACINI da sıfırlardı):
    # geçerli satırlar metrikleri besler, artefakt satırlar yalnız sayılır.
    #
    # KATEGORİ AYRIMI (metodoloji karışımı YASAK — denetim raporu §2):
    # `benchmark_quality` üç farklı ölçüm türü taşır ve bunlar TEK başlıkta
    # toplanamaz: kodlama görevleri (G1/G3/G6/G7), B2 iğne senaryoları
    # (`B2-needle-*`) ve n örnekli varyans koşuları (`G6-n3`). Pass@1/Pass@N
    # YALNIZ kodlama görevlerinden hesaplanır; diğer ikisi ayrı sayılır.
    gecerli = "COALESCE(gecerlilik, 'gecerli') <> 'artefakt-g7'"
    kodlama = f"{gecerli} AND gorev NOT LIKE 'B2-%' AND gorev NOT LIKE '%-n%'"
    needle = f"{gecerli} AND gorev LIKE 'B2-%'"
    varyans = f"{gecerli} AND gorev LIKE '%-n%' AND gorev NOT LIKE 'B2-%'"
    rows = con.execute(
        f"""
        SELECT model,
               SUM(CASE WHEN {gecerli} THEN 1 ELSE 0 END)                 AS gorev_sayisi,
               SUM(CASE WHEN {kodlama} THEN 1 ELSE 0 END)                 AS kodlama_gorev,
               SUM(CASE WHEN {kodlama} THEN COALESCE(pass1, 0) ELSE 0 END) AS pass1,
               SUM(CASE WHEN {kodlama} THEN COALESCE(passN, 0) ELSE 0 END) AS passN,
               ROUND(AVG(CASE WHEN {kodlama} THEN attempts END), 2)       AS ort_deneme,
               SUM(CASE WHEN {needle} THEN 1 ELSE 0 END)                  AS needle_senaryo,
               SUM(CASE WHEN {needle} THEN COALESCE(passN, 0) ELSE 0 END) AS needle_passN,
               -- Varyans koşularında `passN` başarı SAYISIdır ve `attempts`
               -- örneklem büyüklüğüdür (n). Bu yüzden payda satır sayısı değil
               -- toplam örneklem olmalı: "3/6" = %50, "3/2" DEĞİL.
               SUM(CASE WHEN {varyans} THEN COALESCE(attempts, 0) ELSE 0 END) AS varyans_kosu,
               SUM(CASE WHEN {varyans} THEN COALESCE(passN, 0) ELSE 0 END) AS varyans_passN,
               -- Hız GÜVENİLMEZ olabilir: bonsai2/freetoken kayıtları
               -- tg_kaynagi='char_tahmin' (fork/usage vermiyor) → 433/340 tok/s
               -- gibi sahte değerler. `ort_tg_guvenilir` yalnız SUNUCUNUN
               -- ölçtüğü decode süresine dayanan kaynakları ortalar:
               -- eval_duration (Ollama) | usage (OpenAI uyumlu) | timings
               -- (llama.cpp /completion timings.predicted_per_second).
               ROUND(AVG(CASE WHEN {gecerli} THEN tg END), 1)             AS ort_tg,
               ROUND(AVG(CASE WHEN {gecerli} AND tg_kaynagi IN
                     ('eval_duration', 'usage', 'timings')
                     THEN tg END), 1)                                    AS ort_tg_guvenilir,
               COUNT(DISTINCT CASE WHEN {gecerli}
                     THEN gorev || COALESCE(dil, '') END)                 AS alt_senaryo,
               SUM(CASE WHEN gecerlilik = 'artefakt-g7' THEN 1 ELSE 0 END) AS artefakt
        FROM benchmark_quality
        GROUP BY model
        HAVING SUM(CASE WHEN {gecerli} THEN 1 ELSE 0 END) > 0
        ORDER BY passN DESC, ort_deneme ASC
        """
    ).fetchall()
    return [dict(r) for r in rows]
