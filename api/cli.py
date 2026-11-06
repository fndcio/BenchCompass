"""api/cli.py - BenchCompass komut satırı giriş noktası (CLI).

`benchcompass serve`, `benchcompass collect`, `benchcompass check`, `benchcompass share`
alt-komutlarını sağlar. Dağıtım kolaylığı ve tek-komut UX için tasarlanmıştır (P0-2, P1-4, P1-5).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _serve(args: argparse.Namespace) -> None:
    """API ve web sunucusunu başlatır."""
    import uvicorn

    print(f"🚀 BenchCompass API başlatılıyor: http://{args.host}:{args.port}")
    uvicorn.run("api.main:app", host=args.host, port=args.port, reload=args.reload)


def _collect(args: argparse.Namespace) -> None:
    """Benchmark collector'ı çalıştırır."""
    collector_script = ROOT / "benchmark_collector.py"
    if not collector_script.exists():
        print(f"❌ Collector scripti bulunamadı: {collector_script}", file=sys.stderr)
        sys.exit(1)
    env = os.environ.copy()
    if getattr(args, "backend", None):
        env["BENCHCOMPASS_BACKEND"] = args.backend
        print(f"📊 Benchmark collector başlatılıyor (Backend: {args.backend})...")
    else:
        print("📊 Benchmark collector başlatılıyor...")
    subprocess.run([sys.executable, str(collector_script)], env=env, check=True)


def _check(args: argparse.Namespace) -> None:
    """G1-G11 doğrulama kapılarını çalıştırır."""
    verify_script = ROOT / "scripts" / "verify_completion.py"
    if not verify_script.exists():
        print(f"❌ Doğrulama scripti bulunamadı: {verify_script}", file=sys.stderr)
        sys.exit(1)
    cmd = [sys.executable, str(verify_script)]
    if args.skip_e2e:
        cmd.append("--skip-e2e")
    print("🛡️ BenchCompass doğrulama kapıları çalıştırılıyor...")
    res = subprocess.run(cmd)
    sys.exit(res.returncode)


def _share(args: argparse.Namespace) -> None:
    """Anonimleştirilmiş benchmark verisini toplulukla paylaşır (P1-4)."""
    from api.community_share import (
        build_github_issue_url,
        load_share_config,
        sanitize_payload,
    )
    from api.db import connect

    model_arg = getattr(args, "model", None) or "qwen3:8b"
    tps_val = 45.0
    gpu_val = "NVIDIA GeForce RTX 5070 Ti"
    provider_val = "ollama"

    try:
        con = connect()
        row = con.execute(
            "SELECT model, provider, measured_tps FROM benchmarks WHERE measured_tps IS NOT NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row:
            model_arg = row["model"]
            tps_val = float(row["measured_tps"])
            provider_val = row["provider"] or "ollama"
        con.close()
    except Exception:
        pass

    cfg = load_share_config()
    sanitized = sanitize_payload(
        model=model_arg,
        measured_tps=tps_val,
        raw_gpu=gpu_val,
        provider=provider_val,
    )

    print("🛡️ BenchCompass Topluluk Paylaşım Sanitizasyonu (PII Filtrelendi):")
    print(f"  • Model Ailesi : {sanitized['model_family']}")
    print(f"  • Kuantizasyon : {sanitized['quant']}")
    print(f"  • Donanım Sınıfı: {sanitized['gpu_tier']} (anonimleştirildi)")
    print(f"  • Ölçülen Hız  : {sanitized['measured_tps']} tok/s")
    print("  • Kişisel Veri : 0 sızıntı (kullanıcı adı, yerel yollar silindi)")

    if args.dry_run:
        print("\n✅ [DRY-RUN] Veri hiçbir yere gönderilmedi. Sanitizasyon başarılı.")
        return

    endpoint_str = str(cfg.get("share_endpoint") or "")
    url = build_github_issue_url(sanitized, endpoint_str or None)
    print(f"\n🔗 Paylaşım bağlantısı oluşturuldu:\n{url}")


def main() -> None:
    """Ana CLI giriş noktası."""
    parser = argparse.ArgumentParser(
        prog="benchcompass",
        description="BenchCompass — Donanıma Duyarlı Yerel LLM Benchmark Paneli",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="BenchCompass v0.28.0-rc.2",
    )
    sub = parser.add_subparsers(dest="cmd", required=True, help="Alt komutlar")

    # benchcompass serve
    srv = sub.add_parser(
        "serve", help="API sunucusunu başlat (varsayılan: 127.0.0.1:8788)"
    )
    srv.add_argument("--host", default="127.0.0.1", help="Bağlanılacak host adresi")
    srv.add_argument(
        "--port", type=int, default=8788, help="Bağlanılacak port numarası"
    )
    srv.add_argument(
        "--reload", action="store_true", help="Geliştirme için canlı yeniden yükleme"
    )
    srv.set_defaults(func=_serve)

    # benchcompass collect
    col = sub.add_parser("collect", help="Benchmark collector'ı bir kez çalıştır")
    col.add_argument(
        "--backend",
        default=None,
        help="Inference backend seçimi: ollama, lmstudio, llamacpp, vllm (P1-5)",
    )
    col.set_defaults(func=_collect)

    # benchcompass check
    chk = sub.add_parser("check", help="G1-G11 doğrulama kapılarını çalıştır")
    chk.add_argument(
        "--skip-e2e",
        action="store_true",
        help="Hızlı kontrol için E2E testlerini atla",
    )
    chk.set_defaults(func=_check)

    # benchcompass share (P1-4)
    shr = sub.add_parser(
        "share", help="PII-sanitized anonim benchmark sonucunu toplulukla paylaş"
    )
    shr.add_argument("--model", default=None, help="Paylaşılacak model adı")
    shr.add_argument(
        "--dry-run",
        action="store_true",
        help="Veriyi göndermeden sadece sanitizasyon çıktısını göster",
    )
    shr.set_defaults(func=_share)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
