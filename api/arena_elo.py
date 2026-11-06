"""api/arena_elo.py — Çift-Kör Arena Elo Algoritması ve DB Yönetimi (P1-3).

K=32 standart Elo derecelendirmesi ve arena oylama mekanizması.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any
import sqlite3


def calculate_elo_delta(
    elo_a: float, elo_b: float, score_a: float, k: float = 32.0
) -> tuple[float, float]:
    """İki model arasındaki Elo puan değişimini hesaplar.

    score_a: 1.0 (A kazandı), 0.5 (berabere), 0.0 (B kazandı)
    Dönüş: (delta_elo_a, delta_elo_b)
    """
    expected_a = 1.0 / (1.0 + math.pow(10.0, (elo_b - elo_a) / 400.0))
    expected_b = 1.0 - expected_a
    score_b = 1.0 - score_a

    delta_a = round(k * (score_a - expected_a), 2)
    delta_b = round(k * (score_b - expected_b), 2)
    return delta_a, delta_b


def get_or_create_model_elo(con: sqlite3.Connection, model_name: str) -> dict[str, Any]:
    """Modelin mevcut Elo kaydını getirir veya 1000.0 başlangıç puanıyla oluşturur."""
    row = con.execute(
        "SELECT model, elo, wins, losses, draws, updated_at FROM arena_elo WHERE model = ?",
        (model_name,),
    ).fetchone()
    if row:
        return dict(row)

    now = datetime.now().isoformat()
    con.execute(
        "INSERT INTO arena_elo (model, elo, wins, losses, draws, updated_at) "
        "VALUES (?, 1000.0, 0, 0, 0, ?)",
        (model_name, now),
    )
    con.commit()
    return {
        "model": model_name,
        "elo": 1000.0,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "updated_at": now,
    }


def record_duel_vote(
    con: sqlite3.Connection, duel_id: int, choice: str
) -> dict[str, Any]:
    """Kullanıcının düello oyunu kaydeder, Elo'ları günceller ve körlüğü çözer.

    choice: 'a' | 'b' | 'draw'
    """
    row = con.execute(
        "SELECT id, model_a, model_b, winner, prompt_hash, blind_mode FROM arena_duels WHERE id = ?",
        (duel_id,),
    ).fetchone()
    if not row:
        raise ValueError(f"Düello bulunamadı: id={duel_id}")

    if row["winner"] is not None:
        raise ValueError(
            f"Bu düello zaten oylandı: id={duel_id}, winner={row['winner']}"
        )

    choice_norm = choice.strip().lower()
    if choice_norm not in ("a", "b", "draw"):
        raise ValueError(f"Geçersiz seçim: '{choice}' ('a', 'b' veya 'draw' olmalı)")

    model_a = row["model_a"]
    model_b = row["model_b"]

    stats_a = get_or_create_model_elo(con, model_a)
    stats_b = get_or_create_model_elo(con, model_b)

    if choice_norm == "a":
        winner_name = model_a
        score_a = 1.0
        wins_a = stats_a["wins"] + 1
        losses_a = stats_a["losses"]
        draws_a = stats_a["draws"]
        wins_b = stats_b["wins"]
        losses_b = stats_b["losses"] + 1
        draws_b = stats_b["draws"]
    elif choice_norm == "b":
        winner_name = model_b
        score_a = 0.0
        wins_a = stats_a["wins"]
        losses_a = stats_a["losses"] + 1
        draws_a = stats_a["draws"]
        wins_b = stats_b["wins"] + 1
        losses_b = stats_b["losses"]
        draws_b = stats_b["draws"]
    else:  # draw
        winner_name = "draw"
        score_a = 0.5
        wins_a = stats_a["wins"]
        losses_a = stats_a["losses"]
        draws_a = stats_a["draws"] + 1
        wins_b = stats_b["wins"]
        losses_b = stats_b["losses"]
        draws_b = stats_b["draws"] + 1

    delta_a, delta_b = calculate_elo_delta(stats_a["elo"], stats_b["elo"], score_a)
    new_elo_a = round(stats_a["elo"] + delta_a, 2)
    new_elo_b = round(stats_b["elo"] + delta_b, 2)
    now = datetime.now().isoformat()

    # Güncelle Elo tablosu
    con.execute(
        "UPDATE arena_elo SET elo = ?, wins = ?, losses = ?, draws = ?, updated_at = ? WHERE model = ?",
        (new_elo_a, wins_a, losses_a, draws_a, now, model_a),
    )
    con.execute(
        "UPDATE arena_elo SET elo = ?, wins = ?, losses = ?, draws = ?, updated_at = ? WHERE model = ?",
        (new_elo_b, wins_b, losses_b, draws_b, now, model_b),
    )

    # Güncelle Duels tablosu
    con.execute(
        "UPDATE arena_duels SET winner = ? WHERE id = ?",
        (winner_name, duel_id),
    )
    con.commit()

    return {
        "duel_id": duel_id,
        "winner": winner_name,
        "revealed": {
            "model_a": model_a,
            "model_b": model_b,
        },
        "elo_changes": {
            model_a: {
                "old_elo": stats_a["elo"],
                "new_elo": new_elo_a,
                "delta": delta_a,
            },
            model_b: {
                "old_elo": stats_b["elo"],
                "new_elo": new_elo_b,
                "delta": delta_b,
            },
        },
    }


def get_arena_leaderboard(con: sqlite3.Connection) -> list[dict[str, Any]]:
    """Tüm modelleri Elo puanına göre sıralı liste döner."""
    rows = con.execute(
        "SELECT model, elo, wins, losses, draws, updated_at "
        "FROM arena_elo "
        "ORDER BY elo DESC, wins DESC"
    ).fetchall()

    leaderboard = []
    for r in rows:
        total_matches = r["wins"] + r["losses"] + r["draws"]
        win_rate = (
            round((r["wins"] + 0.5 * r["draws"]) / total_matches * 100, 1)
            if total_matches > 0
            else 0.0
        )
        leaderboard.append(
            {
                "model": r["model"],
                "elo": r["elo"],
                "wins": r["wins"],
                "losses": r["losses"],
                "draws": r["draws"],
                "total_matches": total_matches,
                "win_rate_pct": win_rate,
                "updated_at": r["updated_at"],
            }
        )
    return leaderboard
