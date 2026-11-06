"""
Unit testler — api/benchcompass_proxy.py
==========================================================================
llmfit CLI sarmalayıcı + TTL cache. subprocess mock'lanır (gerçek CLI yok).

AGENTS.md §6: dış bağımlılık (llmfit CLI subprocess) mock'lanır.
Tüm public fonksiyonlar _run_llmfit üzerinden geçer — onu mock'lamak yeterli.
"""

from __future__ import annotations

import pytest

from api import benchcompass_proxy


@pytest.fixture(autouse=True)
def reset_cache():
    """Her test öncesi cache'i temizle (izolasyon)."""
    benchcompass_proxy.cache_clear()
    yield
    benchcompass_proxy.cache_clear()


# =============================================================================
# LlmfitError exception
# =============================================================================
class TestLlmfitError:
    def test_error_holds_fields(self):
        err = benchcompass_proxy.LlmfitError(
            "msg", stderr="err", returncode=1, command=["llmfit"]
        )
        assert err.message == "msg"
        assert err.stderr == "err"
        assert err.returncode == 1
        assert err.command == ["llmfit"]

    def test_to_dict_serializes(self):
        err = benchcompass_proxy.LlmfitError(
            "boom", stderr="detail", command=["llmfit", "info"]
        )
        d = err.to_dict()
        assert d["error"] == "boom"
        assert d["stderr"] == "detail"
        assert d["command"] == "llmfit info"


# =============================================================================
# Cache altyapısı
# =============================================================================
class TestCache:
    def test_cache_set_and_get(self):
        benchcompass_proxy._cache_set("key1", {"data": 1}, ttl=60)
        assert benchcompass_proxy._cache_get("key1") == {"data": 1}

    def test_cache_get_missing_returns_none(self):
        assert benchcompass_proxy._cache_get("nonexistent") is None

    def test_cache_clear_all(self):
        benchcompass_proxy._cache_set("a", 1, ttl=60)
        benchcompass_proxy._cache_set("b", 2, ttl=60)
        benchcompass_proxy.cache_clear()
        assert benchcompass_proxy._cache_get("a") is None
        assert benchcompass_proxy._cache_get("b") is None

    def test_cache_clear_pattern(self):
        benchcompass_proxy._cache_set("info:model1", 1, ttl=60)
        benchcompass_proxy._cache_set("plan:model1", 2, ttl=60)
        benchcompass_proxy._cache_set("info:model2", 3, ttl=60)
        benchcompass_proxy.cache_clear("info")
        assert benchcompass_proxy._cache_get("info:model1") is None
        assert benchcompass_proxy._cache_get("info:model2") is None
        # plan korunmalı
        assert benchcompass_proxy._cache_get("plan:model1") == 2

    def test_cache_expiry(self):
        """TTL 0 → hemen expire olur (geçmiş zaman)."""
        benchcompass_proxy._cache_set("expire", "x", ttl=-1)
        assert benchcompass_proxy._cache_get("expire") is None


# =============================================================================
# find_llmfit
# =============================================================================
class TestFindLlmfit:
    def test_find_llmfit_returns_str_or_none(self):
        """find_llmfit str veya None döner (kurulu değilse None)."""
        result = benchcompass_proxy.find_llmfit()
        assert result is None or isinstance(result, str)


# =============================================================================
# _run_llmfit mock'lu — public fonksiyonlar
# =============================================================================
@pytest.fixture()
def mock_run_llmfit(monkeypatch):
    """_run_llmfit'i mock'la — dict döndürür."""

    def fake_run(args, timeout=60, stdin_data=None):
        return {"mock": True, "args": args, "stdin": stdin_data}

    monkeypatch.setattr(benchcompass_proxy, "_run_llmfit", fake_run)
    return fake_run


@pytest.fixture()
def mock_find_llmfit(monkeypatch):
    """find_llmfit'in llmfit bulduğunu mock'la."""
    monkeypatch.setattr(benchcompass_proxy, "find_llmfit", lambda: "/fake/llmfit")


class TestLlmfitPublicFunctions:
    def test_llmfit_info_returns_dict(self, mock_run_llmfit):
        result = benchcompass_proxy.llmfit_info("test-model", use_cache=False)
        assert result["mock"] is True
        assert "info" in result["args"]
        assert "test-model" in result["args"]

    def test_llmfit_info_uses_cache(self, mock_run_llmfit):
        """İkinci çağrı cache'den gelir (mock çağrılmaz)."""
        call_count = [0]
        original = benchcompass_proxy._run_llmfit

        def counting_run(args, timeout=60, stdin_data=None):
            call_count[0] += 1
            return {"cached": False}

        benchcompass_proxy._run_llmfit = counting_run
        try:
            benchcompass_proxy.llmfit_info("model-x", use_cache=True)
            benchcompass_proxy.llmfit_info("model-x", use_cache=True)  # cache hit
            assert call_count[0] == 1  # sadece 1 kez çağrıldı
        finally:
            benchcompass_proxy._run_llmfit = original

    def test_llmfit_plan_returns_dict(self, mock_run_llmfit):
        result = benchcompass_proxy.llmfit_plan("model", context=8192, use_cache=False)
        assert result["mock"] is True
        assert "plan" in result["args"]

    def test_llmfit_plan_with_optional_params(self, mock_run_llmfit):
        result = benchcompass_proxy.llmfit_plan(
            "model",
            context=4096,
            memory_gb=16,
            vram_gb=12,
            quant="Q4_K_M",
            use_cache=False,
        )
        assert result["mock"] is True

    def test_llmfit_diff_returns_dict(self, mock_run_llmfit):
        result = benchcompass_proxy.llmfit_diff(use_cache=False)
        assert result["mock"] is True
        assert "diff" in result["args"]

    def test_llmfit_recommend_returns_dict(self, mock_run_llmfit):
        result = benchcompass_proxy.llmfit_recommend(use_case="coding", use_cache=False)
        assert result["mock"] is True
        assert "recommend" in result["args"]

    def test_llmfit_fit_returns_dict(self, mock_run_llmfit):
        result = benchcompass_proxy.llmfit_fit()
        assert result["mock"] is True
        assert "fit" in result["args"]

    def test_llmfit_hf_search_returns_dict(self, mock_run_llmfit):
        result = benchcompass_proxy.llmfit_hf_search("qwen", use_cache=False)
        assert result["mock"] is True
        assert "hf-search" in result["args"] or "search" in result["args"]

    def test_llmfit_diff_with_model_args(self, mock_run_llmfit):
        """diff iki model argümanıyla çağrılır (satır 267)."""
        result = benchcompass_proxy.llmfit_diff("model-a", "model-b", use_cache=False)
        assert result["mock"] is True
        args = " ".join(result["args"])
        assert "model-a" in args and "model-b" in args

    def test_llmfit_plan_cache_hit(self, mock_run_llmfit):
        """plan ikinci çağrı cache'den gelir (satır 222-224)."""
        call_count = [0]
        original = benchcompass_proxy._run_llmfit

        def counting_run(args, timeout=60, stdin_data=None):
            call_count[0] += 1
            return {"cached": False}

        benchcompass_proxy._run_llmfit = counting_run
        try:
            benchcompass_proxy.llmfit_plan("m", context=4096, use_cache=True)
            benchcompass_proxy.llmfit_plan("m", context=4096, use_cache=True)
            assert call_count[0] == 1
        finally:
            benchcompass_proxy._run_llmfit = original

    def test_llmfit_diff_cache_hit(self, mock_run_llmfit):
        """diff ikinci çağrı cache'den gelir (satır 261-263, 273)."""
        call_count = [0]
        original = benchcompass_proxy._run_llmfit

        def counting_run(args, timeout=60, stdin_data=None):
            call_count[0] += 1
            return {"cached": False}

        benchcompass_proxy._run_llmfit = counting_run
        try:
            benchcompass_proxy.llmfit_diff("a", "b", use_cache=True)
            benchcompass_proxy.llmfit_diff("a", "b", use_cache=True)
            assert call_count[0] == 1
        finally:
            benchcompass_proxy._run_llmfit = original

    def test_llmfit_recommend_cache_hit(self, mock_run_llmfit):
        """recommend ikinci çağrı cache'den gelir (satır 285-287)."""
        call_count = [0]
        original = benchcompass_proxy._run_llmfit

        def counting_run(args, timeout=60, stdin_data=None):
            call_count[0] += 1
            return {"cached": False}

        benchcompass_proxy._run_llmfit = counting_run
        try:
            benchcompass_proxy.llmfit_recommend(use_case="coding", use_cache=True)
            benchcompass_proxy.llmfit_recommend(use_case="coding", use_cache=True)
            assert call_count[0] == 1
        finally:
            benchcompass_proxy._run_llmfit = original

    def test_llmfit_hf_search_cache_hit(self, mock_run_llmfit):
        """hf_search ikinci çağrı cache'den gelir (satır 311-313)."""
        call_count = [0]
        original = benchcompass_proxy._run_llmfit

        def counting_run(args, timeout=60, stdin_data=None):
            call_count[0] += 1
            return {"cached": False}

        benchcompass_proxy._run_llmfit = counting_run
        try:
            benchcompass_proxy.llmfit_hf_search("qwen", use_cache=True)
            benchcompass_proxy.llmfit_hf_search("qwen", use_cache=True)
            assert call_count[0] == 1
        finally:
            benchcompass_proxy._run_llmfit = original


# =============================================================================
# llmfit_bench (Sprint 23 — gerçek yerel ölçüm)
# =============================================================================
class TestLlmfitBench:
    def test_bench_builds_args(self, mock_run_llmfit):
        """bench args: model + provider + --json. (mock_run_llmfit raw args yakalar.)"""
        raw_args = []
        original = benchcompass_proxy._run_llmfit

        def spy_run(args, timeout=60, stdin_data=None):
            raw_args.append(args)
            return {"measured_tps": 42.0}

        benchcompass_proxy._run_llmfit = spy_run
        try:
            result = benchcompass_proxy.llmfit_bench(
                "qwen3:8b", provider="ollama", runs=1, use_cache=False
            )
        finally:
            benchcompass_proxy._run_llmfit = original

        args = " ".join(raw_args[0])
        assert "bench" in args
        assert "qwen3:8b" in args
        assert "ollama" in args
        assert "--json" in args
        assert result["measured_tps"] == 42.0
        assert result["source"] == "real"

    def test_bench_uses_cache(self, mock_run_llmfit):
        """Aynı model+provider ikinci çağrı cache'den gelir."""
        call_count = [0]
        original = benchcompass_proxy._run_llmfit

        def counting_run(args, timeout=60, stdin_data=None):
            call_count[0] += 1
            return {"measured_tps": 42.0}

        benchcompass_proxy._run_llmfit = counting_run
        try:
            benchcompass_proxy.llmfit_bench(
                "m", provider="ollama", runs=1, use_cache=True
            )
            benchcompass_proxy.llmfit_bench(
                "m", provider="ollama", runs=1, use_cache=True
            )
            assert call_count[0] == 1
        finally:
            benchcompass_proxy._run_llmfit = original

    def test_bench_no_binary_raises(self, monkeypatch):
        """llmfit yoksa LlmfitError fırlatır."""
        monkeypatch.setattr(benchcompass_proxy, "find_llmfit", lambda: None)
        with pytest.raises(benchcompass_proxy.LlmfitError):
            benchcompass_proxy.llmfit_bench("m", use_cache=False)


# =============================================================================
# llmfit_doctor — find_llmfit mock'lu
# =============================================================================
class TestLlmfitDoctor:
    def test_doctor_no_binary_raises(self, monkeypatch):
        """llmfit yoksa LlmfitError fırlatır."""
        monkeypatch.setattr(benchcompass_proxy, "find_llmfit", lambda: None)
        with pytest.raises(benchcompass_proxy.LlmfitError) as exc_info:
            benchcompass_proxy.llmfit_doctor(use_cache=False)
        assert "bulunamadi" in exc_info.value.message

    def test_doctor_with_mock_subprocess(self, monkeypatch):
        """llmfit varsa + subprocess mock'lu → dict döner."""

        class FakeProc:
            returncode = 0
            stdout = '{"status": "ok"}'
            stderr = ""

        monkeypatch.setattr(benchcompass_proxy, "find_llmfit", lambda: "/fake/llmfit")
        monkeypatch.setattr(
            benchcompass_proxy.subprocess, "run", lambda *a, **kw: FakeProc()
        )
        result = benchcompass_proxy.llmfit_doctor(use_cache=False)
        assert isinstance(result, str)

    def test_doctor_failure_raises(self, monkeypatch):
        """llmfit doctor returncode != 0 → LlmfitError."""

        class FakeFailProc:
            returncode = 1
            stdout = ""
            stderr = "doctor error"

        monkeypatch.setattr(benchcompass_proxy, "find_llmfit", lambda: "/fake/llmfit")
        monkeypatch.setattr(
            benchcompass_proxy.subprocess, "run", lambda *a, **kw: FakeFailProc()
        )
        with pytest.raises(benchcompass_proxy.LlmfitError) as exc_info:
            benchcompass_proxy.llmfit_doctor(use_cache=False)
        assert "basarisiz" in exc_info.value.message

    def test_doctor_caches_result(self, monkeypatch):
        """use_cache=True → sonuç cache'lenir (ikinci çağrı subprocess'siz)."""

        class FakeProc:
            returncode = 0
            stdout = "cached doctor report"
            stderr = ""

        call_count = [0]

        def counting_run(*a, **kw):
            call_count[0] += 1
            return FakeProc()

        monkeypatch.setattr(benchcompass_proxy, "find_llmfit", lambda: "/fake/llmfit")
        monkeypatch.setattr(benchcompass_proxy.subprocess, "run", counting_run)
        benchcompass_proxy.llmfit_doctor(use_cache=True)
        benchcompass_proxy.llmfit_doctor(use_cache=True)  # cache hit
        assert call_count[0] == 1

    def test_doctor_empty_stdout_returns_default(self, monkeypatch):
        """Boş stdout → 'Bos rapor' fallback döner."""

        class FakeEmptyProc:
            returncode = 0
            stdout = ""
            stderr = ""

        monkeypatch.setattr(benchcompass_proxy, "find_llmfit", lambda: "/fake/llmfit")
        monkeypatch.setattr(
            benchcompass_proxy.subprocess, "run", lambda *a, **kw: FakeEmptyProc()
        )
        result = benchcompass_proxy.llmfit_doctor(use_cache=False)
        assert result == "Bos rapor"


# =============================================================================
# _run_llmfit — hata yolları (subprocess mock'lu)
# =============================================================================
class TestRunLlmfitErrors:
    def test_timeout_raises_llmfit_error(self, monkeypatch):
        import subprocess

        def fake_run(*a, **kw):
            raise subprocess.TimeoutExpired(cmd="llmfit", timeout=1)

        monkeypatch.setattr(benchcompass_proxy.subprocess, "run", fake_run)
        monkeypatch.setattr(benchcompass_proxy, "find_llmfit", lambda: "/fake/llmfit")

        with pytest.raises(benchcompass_proxy.LlmfitError) as exc_info:
            benchcompass_proxy._run_llmfit(["info", "model"])
        assert "timeout" in exc_info.value.message.lower()

    def test_oserror_raises_llmfit_error(self, monkeypatch):
        monkeypatch.setattr(
            benchcompass_proxy.subprocess,
            "run",
            lambda *a, **kw: (_ for _ in ()).throw(OSError("nope")),
        )
        monkeypatch.setattr(benchcompass_proxy, "find_llmfit", lambda: "/fake/llmfit")

        with pytest.raises(benchcompass_proxy.LlmfitError):
            benchcompass_proxy._run_llmfit(["info"])

    def test_nonzero_returncode_raises(self, monkeypatch):
        """llmfit exit code != 0 → LlmfitError."""

        class FakeFailProc:
            returncode = 1
            stdout = ""
            stderr = "model not found"

        monkeypatch.setattr(benchcompass_proxy, "find_llmfit", lambda: "/fake/llmfit")
        monkeypatch.setattr(
            benchcompass_proxy.subprocess, "run", lambda *a, **kw: FakeFailProc()
        )

        with pytest.raises(benchcompass_proxy.LlmfitError) as exc_info:
            benchcompass_proxy._run_llmfit(["info", "bad-model"])
        assert exc_info.value.returncode == 1

    def test_empty_stdout_raises(self, monkeypatch):
        """Boş stdout → LlmfitError."""

        class FakeEmptyProc:
            returncode = 0
            stdout = ""
            stderr = ""

        monkeypatch.setattr(benchcompass_proxy, "find_llmfit", lambda: "/fake/llmfit")
        monkeypatch.setattr(
            benchcompass_proxy.subprocess, "run", lambda *a, **kw: FakeEmptyProc()
        )

        with pytest.raises(benchcompass_proxy.LlmfitError) as exc_info:
            benchcompass_proxy._run_llmfit(["info"])
        assert "boş" in exc_info.value.message.lower()

    def test_valid_json_returns_parsed(self, monkeypatch):
        """Geçerli JSON stdout → dict döner (başarılı yol)."""

        class FakeOkProc:
            returncode = 0
            stdout = '{"model": "test", "score": 95}'
            stderr = ""

        monkeypatch.setattr(benchcompass_proxy, "find_llmfit", lambda: "/fake/llmfit")
        monkeypatch.setattr(
            benchcompass_proxy.subprocess, "run", lambda *a, **kw: FakeOkProc()
        )

        result = benchcompass_proxy._run_llmfit(["info", "test"])
        assert result["model"] == "test"
        assert result["score"] == 95

    def test_json_with_prefix_text(self, monkeypatch):
        """stdout'ta JSON öncesi bilgi mesajı var → yine de parse edilir."""

        class FakePrefixProc:
            returncode = 0
            stdout = 'Searching...\n{"result": "ok"}'
            stderr = ""

        monkeypatch.setattr(benchcompass_proxy, "find_llmfit", lambda: "/fake/llmfit")
        monkeypatch.setattr(
            benchcompass_proxy.subprocess, "run", lambda *a, **kw: FakePrefixProc()
        )

        result = benchcompass_proxy._run_llmfit(["info"])
        assert result["result"] == "ok"

    def test_nonzero_returncode_with_empty_stderr(self, monkeypatch):
        """returncode != 0 + boş stderr → exit code mesajı."""

        class FakeFailNoStderr:
            returncode = 2
            stdout = ""
            stderr = ""

        monkeypatch.setattr(benchcompass_proxy, "find_llmfit", lambda: "/fake/llmfit")
        monkeypatch.setattr(
            benchcompass_proxy.subprocess, "run", lambda *a, **kw: FakeFailNoStderr()
        )

        with pytest.raises(benchcompass_proxy.LlmfitError) as exc_info:
            benchcompass_proxy._run_llmfit(["info"])
        assert (
            "exit code" in exc_info.value.message.lower()
            or "2" in exc_info.value.message
        )

    def test_completely_invalid_json_raises(self, monkeypatch):
        """stdout JSON değil ve '{'/'[' yok → LlmfitError."""

        class FakeBadJson:
            returncode = 0
            stdout = "this is not json at all"
            stderr = ""

        monkeypatch.setattr(benchcompass_proxy, "find_llmfit", lambda: "/fake/llmfit")
        monkeypatch.setattr(
            benchcompass_proxy.subprocess, "run", lambda *a, **kw: FakeBadJson()
        )

        with pytest.raises(benchcompass_proxy.LlmfitError) as exc_info:
            benchcompass_proxy._run_llmfit(["info"])
        assert "JSON" in exc_info.value.message


# =============================================================================
# normalize_system_info — llmfit system → hardware profile schema
# =============================================================================
class TestNormalizeSystemInfo:
    """llmfit system JSON'unu hardware_profile.json şemasına çevirme."""

    def test_full_system_info(self):
        data = {
            "system": {
                "cpu_name": "AMD Ryzen 9",
                "gpu_name": "RTX 5070 Ti",
                "gpu_vram_gb": 11.94,
                "total_ram_gb": 31.29,
            }
        }
        result = benchcompass_proxy.normalize_system_info(data)
        assert result["cpu"] == "AMD Ryzen 9"
        assert result["gpu"] == "RTX 5070 Ti"
        assert result["vram_gb"] == pytest.approx(11.94)
        assert result["ram_gb"] == pytest.approx(31.29)
        assert result["device_name"] == "AMD Ryzen 9 + RTX 5070 Ti"
        assert result["npu_tops"] is None
        assert result["storage_gb"] is None

    def test_flat_system_info_no_wrapper(self):
        """system wrapper yoksa direkt dict kullanılır."""
        data = {
            "cpu_name": "Intel i7",
            "gpu_name": "RTX 4060",
            "gpu_vram_gb": 8.0,
            "total_ram_gb": 16.0,
        }
        result = benchcompass_proxy.normalize_system_info(data)
        assert result["cpu"] == "Intel i7"

    def test_total_gpu_vram_fallback(self):
        """gpu_vram_gb yoksa total_gpu_vram_gb kullanılır."""
        data = {"system": {"total_gpu_vram_gb": 24.0, "total_ram_gb": 64.0}}
        result = benchcompass_proxy.normalize_system_info(data)
        assert result["vram_gb"] == pytest.approx(24.0)

    def test_missing_values_default_zero(self):
        """Eksik değerler 0'a düşer."""
        result = benchcompass_proxy.normalize_system_info({})
        assert result["vram_gb"] == 0
        assert result["ram_gb"] == 0
        assert result["device_name"] == "Algılanan donanım"


# =============================================================================
# _detect_device_name
# =============================================================================
class TestDetectDeviceName:
    def test_both_cpu_gpu(self):
        assert (
            benchcompass_proxy._detect_device_name(
                {"cpu_name": "i7", "gpu_name": "RTX"}
            )
            == "i7 + RTX"
        )

    def test_only_cpu(self):
        assert benchcompass_proxy._detect_device_name({"cpu_name": "i7"}) == "i7"

    def test_only_gpu(self):
        assert benchcompass_proxy._detect_device_name({"gpu_name": "RTX"}) == "RTX"

    def test_empty(self):
        assert benchcompass_proxy._detect_device_name({}) == "Algılanan donanım"


# =============================================================================
# _detect_os
# =============================================================================
class TestDetectOs:
    def test_returns_nonempty_string(self):
        result = benchcompass_proxy._detect_os()
        assert isinstance(result, str)
        assert len(result) > 0


# =============================================================================
# llmfit_system — mock'lu
# =============================================================================
class TestLlmfitSystem:
    def test_system_returns_normalized_dict(self, monkeypatch):
        """llmfit_system mock'lu raw dict döner (cache'siz)."""
        monkeypatch.setattr(
            benchcompass_proxy,
            "_run_llmfit",
            lambda args, timeout=60, stdin_data=None: {"system": {"cpu_name": "test"}},
        )
        result = benchcompass_proxy.llmfit_system(use_cache=False)
        assert isinstance(result, dict)
        assert "system" in result or "cpu" in result


# =============================================================================
# _normalize_bench_output — sürüm direnci (llmfit 1.1.x formatı dahil)
# =============================================================================
class TestNormalizeBenchOutput:
    def test_llmfit_111_runs_and_summary(self):
        """llmfit 1.1.x: result.runs[].tps + summary.avg_tps → measured_tps."""
        raw = {
            "result": {
                "model": "qwen3:8b",
                "provider": "ollama",
                "runs": [
                    {
                        "tps": 84.0,
                        "ttft_ms": 21.9,
                        "output_tokens": 300,
                        "total_ms": 3488.0,
                    },
                    {
                        "tps": 91.1,
                        "ttft_ms": 22.2,
                        "output_tokens": 300,
                        "total_ms": 3529.0,
                    },
                    {
                        "tps": 90.7,
                        "ttft_ms": 21.8,
                        "output_tokens": 300,
                        "total_ms": 3798.0,
                    },
                ],
                "summary": {
                    "avg_tps": 88.6,
                    "avg_ttft_ms": 22.0,
                    "max_tps": 91.1,
                    "num_runs": 3,
                },
            }
        }
        out = benchcompass_proxy._normalize_bench_output(raw)
        assert out["measured_tps"] == pytest.approx(88.6)
        assert out["ttft_ms"] == pytest.approx(22.0)
        # En iyi run'ın token/süre bilgisi (summary'dan measured gelsin de)
        assert out["total_tokens"] == 300
        assert out["total_ms"] == pytest.approx(3529.0)
        assert out["source"] == "real"

    def test_llmfit_111_runs_without_summary(self):
        """summary yoksa runs[].tps'den en iyi tekrar alınır."""
        raw = {
            "result": {
                "runs": [
                    {
                        "tps": 50.0,
                        "ttft_ms": 30.0,
                        "output_tokens": 120,
                        "total_ms": 2400.0,
                    },
                    {
                        "tps": 62.5,
                        "ttft_ms": 28.0,
                        "output_tokens": 150,
                        "total_ms": 2500.0,
                    },
                ]
            }
        }
        out = benchcompass_proxy._normalize_bench_output(raw)
        assert out["measured_tps"] == pytest.approx(62.5)
        assert out["ttft_ms"] == pytest.approx(28.0)
        assert out["total_tokens"] == 150
        assert out["total_ms"] == pytest.approx(2500.0)

    def test_old_flat_format_backward_compat(self):
        """Eski üst-düzey measured_tps hâlâ çalışır."""
        raw = {"measured_tps": 45.2, "ttft_ms": 120.0}
        out = benchcompass_proxy._normalize_bench_output(raw)
        assert out["measured_tps"] == pytest.approx(45.2)

    def test_empty_returns_none(self):
        out = benchcompass_proxy._normalize_bench_output({"result": {"runs": []}})
        assert out["measured_tps"] is None
