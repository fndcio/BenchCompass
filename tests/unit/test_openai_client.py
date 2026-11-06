"""tests/unit/test_openai_client.py — OpenAI Uyumlu Backend İstemcisi Testleri (P1-5)."""

from __future__ import annotations

import httpx
import pytest

from api.db import connect
from api.openai_client import (
    _median,
    _parse_sse_chunk,
    get_backend_url,
    load_backends_config,
    openai_generate,
    run_openai_benchmark,
)
from benchmark_collector import collect_openai_backend


def test_load_backends_config() -> None:
    config = load_backends_config()
    assert "backends" in config
    assert "ollama" in config["backends"]
    assert "lmstudio" in config["backends"]
    assert "llamacpp" in config["backends"]
    assert "vllm" in config["backends"]


def test_get_backend_url(monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. Açık parametre
    url, btype = get_backend_url("lmstudio")
    assert url == "http://localhost:1234"
    assert btype == "openai"

    # 2. Ortam değişkeni
    monkeypatch.setenv("BENCHCOMPASS_BACKEND", "vllm")
    url_env, btype_env = get_backend_url()
    assert url_env == "http://localhost:8000"
    assert btype_env == "openai"

    # 3. Bilinmeyen backend fallback
    monkeypatch.delenv("BENCHCOMPASS_BACKEND", raising=False)
    url_def, btype_def = get_backend_url("unknown_custom")
    assert url_def == "http://localhost:1234"
    assert btype_def == "openai"


def test_openai_generate_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    # httpx.Client.post'u mock'la
    mock_response_data = {
        "id": "chatcmpl-test",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Yerel YZ verimlidir, gizlidir ve bağımsızdır.",
                }
            }
        ],
        "usage": {
            "prompt_tokens": 15,
            "completion_tokens": 30,
            "total_tokens": 45,
        },
    }

    class MockResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return mock_response_data

    class MockClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self) -> MockClient:
            return self

        def __exit__(self, *args) -> None:
            pass

        def post(self, url: str, json: dict, **kwargs) -> MockResponse:
            return MockResponse()

    monkeypatch.setattr(httpx, "Client", MockClient)

    res = openai_generate(
        prompt="Yerel yapay zeka avantajları",
        model="qwen-2.5-7b",
        base_url="http://localhost:1234",
    )

    assert "Yerel YZ verimlidir" in res["response"]
    assert res["output_tokens"] == 30
    assert res["tps"] > 0
    assert res["ttft_ms"] > 0
    # T2 şeffaflık: tahmin yöntemi açıkça işaretlenmeli
    assert res["ttft_method"] == "estimated"


def test_run_openai_benchmark_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    # openai_generate fonksiyonunu mock'la
    def mock_gen(*args, **kwargs) -> dict:
        return {
            "response": "Benchmark cevabı",
            "tps": 42.0,
            "ttft_ms": 110.0,
            "output_tokens": 50,
            "total_duration_s": 1.19,
        }

    monkeypatch.setattr("api.openai_client.openai_generate", mock_gen)

    bench = run_openai_benchmark(model="local-model", runs=2)
    assert bench["model"] == "local-model"
    assert bench["provider"] == "openai-compatible"
    assert bench["measured_tps"] == 42.0
    assert bench["output_tokens"] == 100
    assert bench["runs"] == 2
    assert bench["source"] == "real"


def test_collect_openai_backend(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    # İzole geçici veritabanı
    test_db = tmp_path / "test_collector_backend.db"
    monkeypatch.setattr("api.db.DB", test_db)

    # DB hazırla
    con = connect()
    con.close()

    # run_openai_benchmark'ı mock'la
    def mock_bench(*args, **kwargs) -> dict:
        return {
            "model": "qwen2.5-coder",
            "provider": "lmstudio",
            "measured_tps": 54.2,
            "ttft_ms": 95.0,
            "output_tokens": 120,
            "total_ms": 2214.0,
            "runs": 1,
            "source": "real",
        }

    monkeypatch.setattr("api.openai_client.run_openai_benchmark", mock_bench)

    res = collect_openai_backend("lmstudio", model_name="qwen2.5-coder")
    assert res is not None
    assert res["measured_tps"] == 54.2

    # DB'ye gerçekten yazıldığını doğrula
    con = connect()
    row = con.execute("SELECT * FROM benchmarks WHERE provider = 'lmstudio'").fetchone()
    assert row is not None
    assert row["model"] == "qwen2.5-coder"
    assert row["measured_tps"] == 54.2
    assert row["source"] == "lmstudio-collector"
    con.close()


# ---------------------------------------------------------------------------
# P1-2b: collector ölçüm akışı kalibrasyon alanlarını yazmalı
# ---------------------------------------------------------------------------
def _kalib_db_kur(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """İzole DB kurar ve ölçüm/taahmin stub'ları bağlar."""
    monkeypatch.setattr("api.db.DB", tmp_path / "test_collector_calib.db")
    con = connect()
    con.close()

    def mock_bench(*args, **kwargs) -> dict:
        return {
            "model": "kalib-model",
            "provider": "lmstudio",
            "measured_tps": 54.2,
            "ttft_ms": 95.0,
            "output_tokens": 120,
            "total_ms": 2214.0,
            "runs": 1,
            "source": "real",
        }

    monkeypatch.setattr("api.openai_client.run_openai_benchmark", mock_bench)


def test_collect_openai_backend_kalibrasyon_alanlari_yazar(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Collector ölçümü, tahmin referansı varsa predicted_tps + delta'yı yazmalı (P1-2b).

    Eski boşluk: collector akışı yalnız measured_tps yazıyor, kalibrasyon sütunları
    NULL kalıyordu → /api/calibration/summary paneli boş kalıyordu.
    """
    _kalib_db_kur(monkeypatch, tmp_path)

    class StubBench:
        def get_reference_tps(
            self, model_name: str, gpu_name: str = ""
        ) -> float | None:
            return 50.0

    monkeypatch.setattr("api.bench_data.get_bench", lambda: StubBench())
    collect_openai_backend("lmstudio", model_name="kalib-model")

    con = connect()
    row = con.execute(
        "SELECT predicted_tps, prediction_delta_pct FROM benchmarks "
        "WHERE provider = 'lmstudio' AND model = 'kalib-model'"
    ).fetchone()
    con.close()
    assert row is not None
    assert row["predicted_tps"] == 50.0
    assert row["prediction_delta_pct"] == 8.4  # (54.2-50.0)/50.0*100


def test_collect_openai_backend_tahmin_yoksa_null_yazar(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Tahmin referansı yoksa kalibrasyon alanları NULL yazılmalı (sahte veri yasak)."""
    _kalib_db_kur(monkeypatch, tmp_path)

    class StubBench:
        def get_reference_tps(
            self, model_name: str, gpu_name: str = ""
        ) -> float | None:
            return None

    monkeypatch.setattr("api.bench_data.get_bench", StubBench())

    collect_openai_backend("lmstudio", model_name="kalib-model")

    con = connect()
    row = con.execute(
        "SELECT predicted_tps, prediction_delta_pct FROM benchmarks "
        "WHERE provider = 'lmstudio' AND model = 'kalib-model'"
    ).fetchone()
    con.close()
    assert row is not None
    assert row["predicted_tps"] is None
    assert row["prediction_delta_pct"] is None


# ---------------------------------------------------------------------------
# P1-3 kalıntı: collect() backend yönlendirmesi (env + parametre)
# ---------------------------------------------------------------------------
def test_collect_backend_yonlendirme(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """collect() env (BENCHCOMPASS_BACKEND) ve parametre ile openai backend'lerine
    yönlendirmesi otomatik test altına alındı (önceden elle doğrulanmıştı)."""
    import benchmark_collector as bc

    # İzole DB — collect() ollama yolunda connect() açıyor
    monkeypatch.setattr("api.db.DB", tmp_path / "yonlendirme.db")
    con = connect()
    con.close()

    cagrilar: list[str] = []
    monkeypatch.setattr(
        bc, "collect_openai_backend", lambda name, **kw: cagrilar.append(name)
    )

    # 1) Parametre yönlendirme
    bc.collect(source="api", base="http://127.0.0.1:1", backend="lmstudio")
    assert cagrilar == ["lmstudio"]

    # 2) Env yönlendirme
    monkeypatch.setenv("BENCHCOMPASS_BACKEND", "vllm")
    bc.collect(source="api", base="http://127.0.0.1:1")
    assert cagrilar == ["lmstudio", "vllm"]

    # 3) ollama → openai yoluna yönlendirme YOK
    monkeypatch.delenv("BENCHCOMPASS_BACKEND", raising=False)
    bc.collect(source="api", base="http://127.0.0.1:1", backend="ollama")
    assert cagrilar == ["lmstudio", "vllm"]


# ---------------------------------------------------------------------------
# Adım 2: SSE streaming TTFT/ITL (06.11.2026, §9.3 onayı A)
# ---------------------------------------------------------------------------


def test_median_p50() -> None:
    assert _median([]) == 0.0
    assert _median([5.0]) == 5.0
    assert _median([1.0, 2.0, 3.0]) == 2.0
    assert _median([1.0, 2.0, 3.0, 4.0]) == 2.5


def test_parse_sse_chunk() -> None:
    assert _parse_sse_chunk("") is None
    assert _parse_sse_chunk("data: [DONE]") is None
    assert _parse_sse_chunk("data: {gecersiz") is None
    parsed = _parse_sse_chunk('data: {"choices":[{"delta":{"content":"Merhaba"}}]}')
    assert parsed is not None
    assert parsed["choices"][0]["delta"]["content"] == "Merhaba"


def _stream_lines_mock() -> list[str]:
    import json as _json

    parts = ["Merhaba", " dünya", "!"]
    lines = [
        "data: " + _json.dumps({"choices": [{"delta": {"content": p}}]}) for p in parts
    ]
    lines.append(
        "data: " + _json.dumps({"choices": [], "usage": {"completion_tokens": 30}})
    )
    lines.append("data: [DONE]")
    return lines


def test_openai_generate_streaming_olcer(monkeypatch: pytest.MonkeyPatch) -> None:
    """SSE streaming: gerçek TTFT + ITL + decode tok/s (prefill hariç)."""
    import time as _time

    tick = [_time.perf_counter()]

    def fake_counter() -> float:
        tick[0] += 0.05  # her chunk arası 50ms
        return tick[0]

    monkeypatch.setattr("api.openai_client.time.perf_counter", fake_counter)

    class MockStreamResp:
        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            pass

        def raise_for_status(self) -> None:
            pass

        def iter_lines(self):
            yield from _stream_lines_mock()

    class MockClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self) -> MockClient:
            return self

        def __exit__(self, *args) -> None:
            pass

        def stream(self, *args, **kwargs):
            return MockStreamResp()

        def post(self, url: str, json: dict, **kwargs):
            raise AssertionError("streaming varken fallback olmamalı")

    monkeypatch.setattr(httpx, "Client", MockClient)

    res = openai_generate(
        prompt="Selam", model="qwen-2.5-7b", base_url="http://localhost:1234"
    )

    assert res["ttft_method"] == "streaming"
    assert res["response"] == "Merhaba dünya!"
    assert res["output_tokens"] == 30
    assert res["ttft_ms"] > 0
    assert res["itl_ms"] is not None
    assert res["itl_ms"] >= 0
    assert res["tps"] > 0


def test_openai_generate_streaming_hata_yoksa_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stream desteklemeyen mock (post-only) → estimated fallback çalışmalı."""

    class MockResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {
                "choices": [{"message": {"content": "Fallback çalıştı"}}],
                "usage": {"completion_tokens": 10},
            }

    class MockClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self) -> MockClient:
            return self

        def __exit__(self, *args) -> None:
            pass

        def post(self, url: str, json: dict, **kwargs) -> MockResponse:
            return MockResponse()

        # stream metodu YOK → AttributeError → fallback

    monkeypatch.setattr(httpx, "Client", MockClient)

    res = openai_generate(prompt="Test", model="m", base_url="http://localhost:1234")
    assert res["ttft_method"] == "estimated"
    assert res["itl_ms"] is None
    assert "Fallback çalıştı" in res["response"]


def test_run_openai_benchmark_streaming_yayilim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_openai_benchmark: itl_ms + ttft_method son ölçümden yayılır."""

    def mock_gen(*args, **kwargs) -> dict:
        return {
            "response": "A",
            "tps": 50.0,
            "ttft_ms": 80.0,
            "ttft_method": "streaming",
            "itl_ms": 12.5,
            "output_tokens": 40,
            "total_duration_s": 0.8,
        }

    monkeypatch.setattr("api.openai_client.openai_generate", mock_gen)

    bench = run_openai_benchmark(model="m", runs=2)
    assert bench["ttft_method"] == "streaming"
    assert bench["itl_ms"] == 12.5
    assert bench["ttft_ms"] == 80.0


def test_db_migration_itl_kolonlari(tmp_path) -> None:
    """Adım 2 migration: benchmarks.itl_ms + ttft_method var olmalı (izole DB)."""
    import api.db as dbmod

    con = dbmod.connect()
    cols = {
        row["name"] for row in con.execute("PRAGMA table_info(benchmarks)").fetchall()
    }
    con.close()
    assert "itl_ms" in cols
    assert "ttft_method" in cols


def test_save_benchmark_record_itl_yazar(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """_save_benchmark_record: itl_ms + ttft_method DB'ye yazılmalı (izole DB)."""
    import api.db as dbmod
    from api.routes.shared import _save_benchmark_record

    monkeypatch.setattr(dbmod, "DB", tmp_path / "itl.db")
    con = dbmod.connect()
    con.close()

    _save_benchmark_record(
        "itl-model",
        "lmstudio",
        {
            "measured_tps": 42.0,
            "ttft_ms": 95.0,
            "ttft_method": "streaming",
            "itl_ms": 8.4,
            "output_tokens": 120,
            "total_ms": 2000.0,
            "source": "real",
        },
    )

    con = dbmod.connect()
    row = con.execute(
        "SELECT itl_ms, ttft_method FROM benchmarks WHERE model = 'itl-model'"
    ).fetchone()
    con.close()
    assert row is not None
    assert row["itl_ms"] == 8.4
    assert row["ttft_method"] == "streaming"
