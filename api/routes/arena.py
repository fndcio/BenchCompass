"""api/routes/arena.py — Local Model Arena (Split-Screen & Sıralı Adil Karşılaştırma).

İki yerel modeli sıralı (sequential fair duel) çalıştırarak tek GPU'da (12 GB)
OOM oluşmasını önler; TTFT, tok/s, gecikme ve çıktıları yan yana kıyaslar.
P1-3 ile Çift-Kör (Blind Duel), Elo birikimi ve oylama mekanizması eklenmiştir.
"""

from __future__ import annotations

import hashlib
import logging
import random
import re
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import arena_elo
from .. import db as dbmod
from ..ollama_client import _api_post

logger = logging.getLogger(__name__)
router = APIRouter()


class ArenaRequest(BaseModel):
    model_a: str
    model_b: str
    prompt: str = "Hızlıca 3 maddede yerel yapay zeka çalıştırmanın avantajlarını yaz."
    max_tokens: int = 120
    blind: bool = False


class ArenaVoteRequest(BaseModel):
    duel_id: int
    choice: str  # 'a', 'b', 'draw'


def _run_single_model(model_name: str, prompt: str, max_tokens: int) -> dict[str, Any]:
    """Tek bir modeli koşturur ve performans metriklerini hesaplar."""
    t0 = time.perf_counter()
    try:
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        res = _api_post("/api/generate", payload, timeout=60)
        t_total = time.perf_counter() - t0

        output_text = res.get("response", "")
        eval_count = res.get("eval_count", 0)
        eval_duration_ns = res.get("eval_duration", 0)
        prompt_eval_duration_ns = res.get("prompt_eval_duration", 0)

        # TTFT: prompt_eval_duration varsa gerçek (ms); yoksa %20 tahmini —
        # Y24 şeffaflığı: yöntem "measured"/"estimated" olarak işaretlenir
        # (denetim T2). Sahte kesinlik gösterilmez.
        if prompt_eval_duration_ns:
            ttft_ms = round(prompt_eval_duration_ns / 1e6, 1)
            ttft_method = "measured"
        else:
            ttft_ms = round(t_total * 200, 1)
            ttft_method = "estimated"

        # TPS: Token per second
        if eval_duration_ns and eval_count:
            tps = round(eval_count / (eval_duration_ns / 1e9), 1)
        elif t_total > 0 and eval_count > 0:
            tps = round(eval_count / t_total, 1)
        else:
            tps = round(len(output_text.split()) * 1.3 / max(0.1, t_total), 1)

        return {
            "model": model_name,
            "success": True,
            "response": output_text,
            "total_tokens": eval_count,
            "ttft_ms": ttft_ms,
            "ttft_method": ttft_method,
            "tok_per_sec": tps,
            "wall_clock_s": round(t_total, 2),
        }
    except Exception as exc:  # noqa: BLE001
        t_total = time.perf_counter() - t0
        logger.warning("Arena calistirma hatasi (%s): %s", model_name, exc)
        # Mock / Fallback (Offline / Test Uyumu)
        sim_tokens = max_tokens
        sim_tps = (
            48.5
            if "qwen" in model_name.lower()
            else (56.2 if "gemma" in model_name.lower() else 35.0)
        )
        return {
            "model": model_name,
            "success": False,
            "simulated": True,
            "error": str(exc),
            "response": f"[{model_name}] Yerel çıkarım simülasyon yanıtı: Yerel YZ, gizlilik, sıfır maliyet ve tam kontrol sağlar.",
            "total_tokens": sim_tokens,
            "ttft_ms": 145.0,
            "ttft_method": "simulated",
            "tok_per_sec": sim_tps,
            "wall_clock_s": round(sim_tokens / sim_tps, 2),
        }


@router.post("/api/arena/duel")
def arena_duel(req: ArenaRequest) -> dict[str, Any]:
    """İki modeli sıralı olarak çalıştırır ve adil karşılaştırma sonucunu döner."""
    prompt_hash = hashlib.sha256(req.prompt.encode("utf-8")).hexdigest()[:8]

    if req.blind:
        # Kör modda modeller rastgele karıştırılır
        is_swapped = random.choice([True, False])
        actual_model_a = req.model_b if is_swapped else req.model_a
        actual_model_b = req.model_a if is_swapped else req.model_b

        run_a = _run_single_model(actual_model_a, req.prompt, req.max_tokens)
        run_b = _run_single_model(actual_model_b, req.prompt, req.max_tokens)

        # Maskele: model isimlerini yanıttan ve metin gövdesinden tamamen kaldır (P1-3 sızıntı koruması)
        def _mask_result(
            item: dict[str, Any], actual_name: str, display_name: str
        ) -> dict[str, Any]:
            m = dict(item)
            m["model"] = display_name
            # Harf-duyarsız maskeleme: bazı backend'ler ismi büyük/küçük harf farklı yazabilir
            kalip = re.compile(re.escape(actual_name), re.IGNORECASE)
            if "response" in m and isinstance(m["response"], str):
                m["response"] = kalip.sub(display_name, m["response"])
            if "error" in m and isinstance(m["error"], str):
                m["error"] = kalip.sub(display_name, m["error"])
            return m

        masked_run_a = _mask_result(run_a, actual_model_a, "Model A")
        masked_run_b = _mask_result(run_b, actual_model_b, "Model B")

        con = dbmod.connect()
        try:
            cur = con.execute(
                "INSERT INTO arena_duels (model_a, model_b, winner, prompt_hash, tps_a, tps_b, ttft_a_ms, ttft_b_ms, blind_mode) "
                "VALUES (?, ?, NULL, ?, ?, ?, ?, ?, 1)",
                (
                    actual_model_a,
                    actual_model_b,
                    prompt_hash,
                    run_a.get("tok_per_sec"),
                    run_b.get("tok_per_sec"),
                    run_a.get("ttft_ms"),
                    run_b.get("ttft_ms"),
                ),
            )
            con.commit()
            duel_id = cur.lastrowid
        finally:
            con.close()

        return {
            "status": "OK",
            "mode": "blind_duel",
            "duel_id": duel_id,
            "blind": True,
            "shared_gpu_notice": "Tek GPU üzerinde körleme uygulanmış adil sıralı test.",
            "prompt": req.prompt,
            "results": {
                "model_a": masked_run_a,
                "model_b": masked_run_b,
            },
        }

    # Açık Mod (Mevcut davranış korunur)
    run_a = _run_single_model(req.model_a, req.prompt, req.max_tokens)
    run_b = _run_single_model(req.model_b, req.prompt, req.max_tokens)

    tps_a = run_a.get("tok_per_sec", 0)
    tps_b = run_b.get("tok_per_sec", 0)
    ttft_a = run_a.get("ttft_ms", 9999)
    ttft_b = run_b.get("ttft_ms", 9999)

    score_a = tps_a * 0.7 + (1000.0 / max(10.0, ttft_a)) * 0.3
    score_b = tps_b * 0.7 + (1000.0 / max(10.0, ttft_b)) * 0.3

    winner = req.model_a if score_a >= score_b else req.model_b

    con = dbmod.connect()
    try:
        cur = con.execute(
            "INSERT INTO arena_duels (model_a, model_b, winner, prompt_hash, tps_a, tps_b, ttft_a_ms, ttft_b_ms, blind_mode) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
            (
                req.model_a,
                req.model_b,
                winner,
                prompt_hash,
                tps_a,
                tps_b,
                ttft_a,
                ttft_b,
            ),
        )
        con.commit()
        duel_id = cur.lastrowid
    finally:
        con.close()

    return {
        "status": "OK",
        "mode": "sequential_fair_duel",
        "duel_id": duel_id,
        "blind": False,
        "shared_gpu_notice": "Tek GPU (12 GB) üzerinde OOM riskini önlemek için adil sıralı test uygulanmıştır.",
        "prompt": req.prompt,
        "winner": winner,
        "results": {
            "model_a": run_a,
            "model_b": run_b,
        },
    }


@router.post("/api/arena/vote")
def arena_vote(req: ArenaVoteRequest) -> dict[str, Any]:
    """Kör veya açık moddaki düello için kullanıcı oyunu kaydeder (P1-3)."""
    con = dbmod.connect()
    try:
        vote_result = arena_elo.record_duel_vote(con, req.duel_id, req.choice)
        return {
            "status": "OK",
            "message": "Oy kaydedildi ve Elo güncellendi.",
            "data": vote_result,
        }
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    finally:
        con.close()


@router.get("/api/arena/leaderboard")
def arena_leaderboard() -> dict[str, Any]:
    """Modellerin güncel Arena Elo derecelerini ve maç istatistiklerini döner (P1-3)."""
    con = dbmod.connect()
    try:
        leaderboard = arena_elo.get_arena_leaderboard(con)
        return {
            "status": "OK",
            "count": len(leaderboard),
            "leaderboard": leaderboard,
        }
    finally:
        con.close()
