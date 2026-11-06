"""
Unit testler — api/ollama_client.py
==========================================================================
Ollama REST API istemcisi. urllib monkeypatch ile network mock'lanır.

AGENTS.md §6: dış bağımlılık (network/Ollama servisi) mock'lanır.
no_network fixture'ı kazara network çağrısını yakalar.
"""

from __future__ import annotations

import json
import shutil
from unittest.mock import MagicMock

import pytest

from api import ollama_client


# =============================================================================
# Yardımcı: urllib.request.urlopen mock
# =============================================================================
def _make_mock_response(data: dict):
    """urlopen context manager mock'u — bytes yanıt döner."""
    mock_resp = MagicMock()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read = MagicMock(return_value=json.dumps(data).encode("utf-8"))
    return mock_resp


# =============================================================================
# OllamaError exception
# =============================================================================
class TestOllamaError:
    def test_error_holds_message_and_stderr(self):
        err = ollama_client.OllamaError("boom", stderr="detail")
        assert err.message == "boom"
        assert err.stderr == "detail"
        assert "boom" in str(err)


# =============================================================================
# _api_get — başarılı yol
# =============================================================================
class TestApiGet:
    def test_get_returns_parsed_json(self, monkeypatch):
        """_api_get dict döner (JSON parse)."""

        def fake_urlopen(url, timeout):
            return _make_mock_response({"models": [{"name": "test"}]})

        monkeypatch.setattr(ollama_client.urllib.request, "urlopen", fake_urlopen)

        result = ollama_client._api_get("/api/tags")
        assert result["models"][0]["name"] == "test"

    def test_get_url_error_raises_ollama_error(self, monkeypatch):
        """URLError → OllamaError (from e ile zincirli)."""
        import urllib.error

        def fake_urlopen(url, timeout):
            raise urllib.error.URLError("connection refused")

        monkeypatch.setattr(ollama_client.urllib.request, "urlopen", fake_urlopen)

        with pytest.raises(ollama_client.OllamaError) as exc_info:
            ollama_client._api_get("/api/tags")
        assert "erisilemiyor" in exc_info.value.message

    def test_get_json_decode_error_raises_ollama_error(self, monkeypatch):
        """Bozuk JSON → OllamaError."""

        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read = MagicMock(return_value=b"not-json{")

        monkeypatch.setattr(
            ollama_client.urllib.request, "urlopen", lambda url, timeout: mock_resp
        )

        with pytest.raises(ollama_client.OllamaError) as exc_info:
            ollama_client._api_get("/api/tags")
        assert "bozuk" in exc_info.value.message


# =============================================================================
# _api_post
# =============================================================================
class TestApiPost:
    def test_post_returns_parsed_json(self, monkeypatch):
        def fake_urlopen(req, timeout):
            return _make_mock_response({"ok": True})

        monkeypatch.setattr(ollama_client.urllib.request, "urlopen", fake_urlopen)

        result = ollama_client._api_post("/api/show", {"model": "test"})
        assert result["ok"] is True

    def test_post_url_error_raises(self, monkeypatch):
        import urllib.error

        monkeypatch.setattr(
            ollama_client.urllib.request,
            "urlopen",
            lambda req, timeout: (_ for _ in ()).throw(urllib.error.URLError("nope")),
        )

        with pytest.raises(ollama_client.OllamaError):
            ollama_client._api_post("/api/show", {"model": "test"})


# =============================================================================
# list_models
# =============================================================================
class TestListModels:
    def test_list_models_normalizes_shape(self, monkeypatch):
        """list_models Ollama yanıtını normalize edilmiş dict listesine çevirir."""
        raw = {
            "models": [
                {
                    "name": "qwen3:8b",
                    "size": 4661216768,  # ~4.34 GB
                    "details": {
                        "parameter_size": "8B",
                        "quantization_level": "q4_0",
                        "context_length": 32768,
                        "family": "qwen",
                    },
                    "modified_at": "2024-01-01",
                    "digest": "abc123",
                }
            ]
        }
        monkeypatch.setattr(
            ollama_client,
            "_api_get",
            lambda path: raw,
        )

        models = ollama_client.list_models()
        assert len(models) == 1
        m = models[0]
        assert m["name"] == "qwen3:8b"
        assert m["size_gb"] == pytest.approx(4.34, abs=0.1)
        assert m["provider"] == "ollama"
        assert m["parameter_size"] == "8B"
        assert m["context_length"] == 32768

    def test_list_models_empty(self, monkeypatch):
        """Ollama'da model yoksa boş liste döner."""
        monkeypatch.setattr(ollama_client, "_api_get", lambda path: {"models": []})
        assert ollama_client.list_models() == []


# =============================================================================
# ps
# =============================================================================
class TestPs:
    def test_ps_returns_models_list(self, monkeypatch):
        monkeypatch.setattr(
            ollama_client, "_api_get", lambda path: {"models": [{"name": "running"}]}
        )
        result = ollama_client.ps()
        assert len(result) == 1

    def test_ps_error_returns_empty(self, monkeypatch):
        """OllamaError → boş liste (ps hata fırlatmaz, sessce geçer)."""
        monkeypatch.setattr(
            ollama_client,
            "_api_get",
            lambda path: (_ for _ in ()).throw(ollama_client.OllamaError("down")),
        )
        assert ollama_client.ps() == []


# =============================================================================
# show_model
# =============================================================================
class TestShowModel:
    def test_show_model_returns_dict(self, monkeypatch):
        monkeypatch.setattr(
            ollama_client, "_api_post", lambda path, data, timeout=15: {"details": "ok"}
        )
        result = ollama_client.show_model("test-model")
        assert result["details"] == "ok"


# =============================================================================
# run_model — subprocess mock'lu
# =============================================================================
class TestRunModel:
    def test_run_model_success(self, monkeypatch):
        """Başarılı run → ok=True."""

        class FakeProc:
            returncode = 0
            stdout = ""
            stderr = ""

        monkeypatch.setattr(
            ollama_client.subprocess, "run", lambda *a, **kw: FakeProc()
        )
        result = ollama_client.run_model("test-model")

        assert result["ok"] is True
        assert result["model"] == "test-model"

    def test_run_model_timeout_returns_ok(self, monkeypatch):
        """Timeout = arka planda çalışıyor → ok=True (Ollama davranışı)."""
        import subprocess

        def fake_run(*a, **kw):
            raise subprocess.TimeoutExpired(cmd="ollama", timeout=5)

        monkeypatch.setattr(ollama_client.subprocess, "run", fake_run)
        result = ollama_client.run_model("test-model")

        assert result["ok"] is True
        assert "arkaplanda" in result["message"]

    def test_run_model_not_found_raises(self, monkeypatch):
        """ollama CLI yok → OllamaError."""
        monkeypatch.setattr(
            ollama_client.subprocess,
            "run",
            lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError()),
        )
        with pytest.raises(ollama_client.OllamaError) as exc_info:
            ollama_client.run_model("test")
        assert "bulunamadi" in exc_info.value.message


# =============================================================================
# stop_model — subprocess mock'lu
# =============================================================================
class TestStopModel:
    def test_stop_model_success(self, monkeypatch):
        class FakeProc:
            returncode = 0
            stdout = ""
            stderr = ""

        monkeypatch.setattr(
            ollama_client.subprocess, "run", lambda *a, **kw: FakeProc()
        )
        result = ollama_client.stop_model("test-model")

        assert result["ok"] is True
        assert result["model"] == "test-model"

    def test_stop_model_failure_raises(self, monkeypatch):
        """returncode != 0 → OllamaError."""

        class FakeFailProc:
            returncode = 1
            stdout = ""
            stderr = "model not running"

        monkeypatch.setattr(
            ollama_client.subprocess, "run", lambda *a, **kw: FakeFailProc()
        )
        with pytest.raises(ollama_client.OllamaError) as exc_info:
            ollama_client.stop_model("test")
        assert "basarisiz" in exc_info.value.message

    def test_stop_model_not_found_raises(self, monkeypatch):
        monkeypatch.setattr(
            ollama_client.subprocess,
            "run",
            lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError()),
        )
        with pytest.raises(ollama_client.OllamaError):
            ollama_client.stop_model("test")


# =============================================================================
# run_benchmark — llmfit CLI mock'lu
# =============================================================================
class TestRunBenchmark:
    def test_benchmark_no_llmfit_raises(self, monkeypatch):
        """llmfit binary yok → OllamaError."""
        monkeypatch.setattr(shutil, "which", lambda name: None)
        with pytest.raises(ollama_client.OllamaError) as exc_info:
            ollama_client.run_benchmark("model")
        assert "llmfit" in exc_info.value.message.lower()

    def test_benchmark_summary_format(self, monkeypatch):
        """result.summary formatı normalize edilir."""

        class FakeProc:
            returncode = 0
            stdout = '{"result": {"summary": {"avg_tps": 45.2, "avg_ttft_ms": 120, "avg_output_tokens": 100, "avg_total_ms": 5000, "num_runs": 3}}}'  # noqa: E501
            stderr = ""

        monkeypatch.setattr(shutil, "which", lambda name: "/fake/llmfit")
        monkeypatch.setattr(
            ollama_client.subprocess, "run", lambda *a, **kw: FakeProc()
        )
        result = ollama_client.run_benchmark("test-model")

        assert result["measured_tps"] == pytest.approx(45.2)
        assert result["ttft_ms"] == pytest.approx(120)
        assert result["model"] == "test-model"

    def test_benchmark_list_format(self, monkeypatch):
        """result liste formatı normalize edilir."""

        class FakeProc:
            returncode = 0
            stdout = '{"result": [{"tps": 30.0, "ttft_ms": 200, "output_tokens": 50, "total_ms": 3000}]}'
            stderr = ""

        monkeypatch.setattr(shutil, "which", lambda name: "/fake/llmfit")
        monkeypatch.setattr(
            ollama_client.subprocess, "run", lambda *a, **kw: FakeProc()
        )
        result = ollama_client.run_benchmark("test-model")

        assert result["measured_tps"] == pytest.approx(30.0)
        assert result["num_runs"] == 1

    def test_benchmark_failure_raises(self, monkeypatch):
        """returncode != 0 → OllamaError."""

        class FakeFailProc:
            returncode = 1
            stdout = ""
            stderr = "benchmark failed"

        monkeypatch.setattr(shutil, "which", lambda name: "/fake/llmfit")
        monkeypatch.setattr(
            ollama_client.subprocess, "run", lambda *a, **kw: FakeFailProc()
        )
        with pytest.raises(ollama_client.OllamaError):
            ollama_client.run_benchmark("test")

    def test_benchmark_timeout_raises(self, monkeypatch):
        import subprocess

        def fake_run(*a, **kw):
            raise subprocess.TimeoutExpired(cmd="llmfit", timeout=60)

        monkeypatch.setattr(shutil, "which", lambda name: "/fake/llmfit")
        monkeypatch.setattr(ollama_client.subprocess, "run", fake_run)
        with pytest.raises(ollama_client.OllamaError) as exc_info:
            ollama_client.run_benchmark("test")
        assert "timeout" in exc_info.value.message.lower()

    def test_benchmark_no_json_raises(self, monkeypatch):
        """stdout'ta JSON yok → OllamaError."""

        class FakeProc:
            returncode = 0
            stdout = "no json here"
            stderr = ""

        monkeypatch.setattr(shutil, "which", lambda name: "/fake/llmfit")
        monkeypatch.setattr(
            ollama_client.subprocess, "run", lambda *a, **kw: FakeProc()
        )
        with pytest.raises(ollama_client.OllamaError):
            ollama_client.run_benchmark("test")


class TestGenerateChat:
    """generate_chat() testleri."""

    def test_generate_chat_success(self, monkeypatch):
        fake_response = {
            "response": "Merhaba, ben bir yapay zeka modeliyim.",
            "total_duration": 500000000,
            "eval_count": 10,
            "eval_duration": 400000000,
        }
        monkeypatch.setattr(ollama_client, "_api_post", lambda *a, **kw: fake_response)
        res = ollama_client.generate_chat("qwen3:8b", "test prompt")
        assert res["ok"] is True
        assert "yapay zeka" in res["response"]
        assert res["eval_count"] == 10

    def test_generate_chat_error_raises_ollama_error(self, monkeypatch):
        def fake_post(*a, **kw):
            raise RuntimeError("network down")

        monkeypatch.setattr(ollama_client, "_api_post", fake_post)
        with pytest.raises(ollama_client.OllamaError):
            ollama_client.generate_chat("qwen3:8b", "test")


class TestPullModel:
    """pull_model() testleri."""

    def test_pull_model_success_with_progress(self, monkeypatch):
        lines = [
            b'{"status": "pulling manifest"}\n',
            b'{"status": "downloading", "completed": 500, "total": 1000}\n',
            b'{"status": "success"}\n',
        ]
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.__iter__ = MagicMock(return_value=iter(lines))

        monkeypatch.setattr(
            ollama_client.urllib.request, "urlopen", lambda *a, **kw: mock_resp
        )

        progress_calls = []
        res = ollama_client.pull_model(
            "qwen2.5:0.5b", on_progress=lambda p: progress_calls.append(p)
        )
        assert res["ok"] is True
        assert res["model"] == "qwen2.5:0.5b"
        assert res["status"] == "success"
        assert len(progress_calls) >= 2
        assert progress_calls[1]["completed"] == 500
        assert progress_calls[1]["pct"] == 50.0

    def test_pull_model_error_chunk_raises(self, monkeypatch):
        lines = [
            b'{"error": "model not found"}\n',
        ]
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.__iter__ = MagicMock(return_value=iter(lines))

        monkeypatch.setattr(
            ollama_client.urllib.request, "urlopen", lambda *a, **kw: mock_resp
        )

        with pytest.raises(ollama_client.OllamaError) as exc_info:
            ollama_client.pull_model("unknown:model")
        assert "model not found" in exc_info.value.message
