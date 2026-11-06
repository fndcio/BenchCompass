"""api/share_card.py — Sosyal Medya Benchmark Infografik Kart Üreticisi (SVG).

1200x630 px Twitter / Reddit OpenGraph formatında şık, koyu temalı
ve gizlilik odaklı (sıfır PII, sıfır dış ağ) infografik SVG üretir
(ADR-0012, Ortakheyet konsensüsü).
"""

from __future__ import annotations

import html

from .system_info import get_hardware_specs


def generate_share_card_svg(
    model: str,
    tps: float,
    ttft_ms: float = 120.0,
    tier: str = "Tam Uyumlu",
    gpu: str | None = None,
    context_window: int = 4096,
    score: float | None = None,
    ttft_method: str | None = None,
    itl_ms: float | None = None,
) -> str:
    """Benchmark ölçüm sonucunu 1200x630 SVG görseline dönüştürür.

    ttft_method: "streaming"/"measured" (gerçek) veya "estimated"/"simulated"
    — tahmin ise kartta "(tahmini)" etiketi zorunlu (denetim T2, Y24).
    itl_ms verilirse (streaming) TTFT bloğu altında ITL satırı gösterilir.
    """
    if not gpu:
        hw = get_hardware_specs()
        gpu = str(hw.get("gpu", "NVIDIA RTX Series"))

    # PII Sanitizasyon: GPU adı veya modelde kullanıcı adı sızıntısı olamaz
    safe_model = html.escape(str(model)[:40])
    safe_gpu = html.escape(str(gpu)[:45])
    safe_tier = html.escape(str(tier)[:20])
    tps_val = f"{tps:.1f}"
    ttft_suffix = " (tahmini)" if (ttft_method in ("estimated", "simulated")) else ""
    if itl_ms is not None:
        intl_svg = f'    <text x="24" y="155" font-family="\'JetBrains Mono\', monospace" font-size="11" fill="#8b949e">ITL: {itl_ms:.1f} ms (p50)</text>'
    else:
        intl_svg = ""
    score_svg = ""
    if score is not None:
        score_val = f"{score:.1f}"
        score_svg = f"""<rect y="125" width="450" height="30" rx="6" fill="#161b26" stroke="#388bfd" stroke-width="1" />
    <text x="14" y="145" font-family="'JetBrains Mono', monospace" font-size="12" fill="#58a6ff">SINIF SKORU: <tspan fill="#ffffff" font-weight="bold">%{score_val}</tspan> (donanım sınıfı ortalaması)</text>"""

    tier_color = (
        "#3fb950"
        if "tam" in tier.lower()
        else ("#d29922" if "uyumlu" in tier.lower() else "#da3633")
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630" width="1200" height="630">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0a0c10"/>
      <stop offset="50%" stop-color="#111622"/>
      <stop offset="100%" stop-color="#090a0f"/>
    </linearGradient>
    <linearGradient id="glow" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#388bfd" stop-opacity="0.2"/>
      <stop offset="100%" stop-color="#2ea043" stop-opacity="0.1"/>
    </linearGradient>
  </defs>

  <!-- Arka Plan -->
  <rect width="1200" height="630" fill="url(#bg)" />
  <rect x="30" y="30" width="1140" height="570" rx="16" fill="none" stroke="#212638" stroke-width="2" />
  <rect x="30" y="30" width="1140" height="570" rx="16" fill="url(#glow)" />

  <!-- Logo ve Marka -->
  <g transform="translate(70, 75)">
    <rect width="42" height="42" rx="8" fill="#388bfd" />
    <path d="M12 21h18M21 12v18" stroke="#ffffff" stroke-width="3.5" stroke-linecap="round"/>
    <text x="56" y="28" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="24" font-weight="800" fill="#f0f6fc">BenchCompass</text>
    <text x="56" y="44" font-family="'JetBrains Mono', monospace" font-size="11" fill="#8b949e" letter-spacing="1">VERIFIED LOCAL LLM BENCHMARK</text>
  </g>

  <!-- Donanım ve Model Bilgisi -->
  <g transform="translate(70, 180)">
    <text font-family="'JetBrains Mono', monospace" font-size="14" fill="#58a6ff" letter-spacing="2">MODEL TEST EDİLDİ</text>
    <text y="50" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="44" font-weight="900" fill="#ffffff">{safe_model}</text>

    <rect y="80" width="450" height="40" rx="6" fill="#161b26" stroke="#212638" />
    <text x="14" y="105" font-family="'JetBrains Mono', monospace" font-size="13" fill="#8b949e">DONANIM: <tspan fill="#f0f6fc" font-weight="bold">{safe_gpu}</tspan></text>
    {score_svg}
  </g>

  <!-- Ana Metrik: TPS -->
  <g transform="translate(70, 370)">
    <rect width="500" height="180" rx="12" fill="#131722" stroke="#388bfd" stroke-width="1.5" />
    <text x="30" y="50" font-family="'JetBrains Mono', monospace" font-size="14" fill="#8b949e" letter-spacing="1">ÜRETİM HIZI (THROUGHPUT)</text>
    <text x="30" y="135" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="80" font-weight="900" fill="#58a6ff">{tps_val}</text>
    <text x="260" y="130" font-family="'JetBrains Mono', monospace" font-size="28" font-weight="bold" fill="#8b949e">tok/s</text>
  </g>

  <!-- İkincil Metrikler -->
  <g transform="translate(610, 370)">
    <!-- TTFT -->
    <rect width="240" height="180" rx="12" fill="#131722" stroke="#212638" />
    <text x="24" y="45" font-family="'JetBrains Mono', monospace" font-size="13" fill="#8b949e">İLK YANIT (TTFT){ttft_suffix}</text>
    <text x="24" y="115" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="48" font-weight="800" fill="#f0f6fc">{ttft_ms:.0f}</text>
    <text x="135" y="110" font-family="'JetBrains Mono', monospace" font-size="18" fill="#8b949e">ms</text>
{intl_svg}

    <!-- TIER & CONTEXT -->
    <rect x="270" width="250" height="180" rx="12" fill="#131722" stroke="#212638" />
    <text x="294" y="45" font-family="'JetBrains Mono', monospace" font-size="13" fill="#8b949e">UYUMLULUK TIER</text>
    <rect x="294" y="70" width="180" height="38" rx="6" fill="{tier_color}" fill-opacity="0.15" stroke="{tier_color}" />
    <text x="310" y="95" font-family="'JetBrains Mono', monospace" font-size="14" font-weight="bold" fill="{tier_color}">{safe_tier}</text>
    <text x="294" y="145" font-family="'JetBrains Mono', monospace" font-size="12" fill="#8b949e">Context: {context_window} tok</text>
  </g>

  <!-- Alt Çizgi -->
  <text x="1110" y="580" text-anchor="end" font-family="'JetBrains Mono', monospace" font-size="11" fill="#484f58">local-first · github.com/BenchCompass</text>
</svg>"""
