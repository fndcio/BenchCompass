/* BenchCompass — uyumluluk (tier) motoru
 *
 * KAYNAK: `api/compat.py` — bu dosya onun BİREBİR frontend kopyasıdır (G8 mirror).
 * Formül değişikliği HER İKİ dosyada birlikte yapılır (AGENTS.md §1.6, Y17).
 * web/app.js'ten ayrıldı (2026-11-05, Faz 2 modülerleştirme).
 */
import { parseNotesFlags } from './format.js';

/**
 * computeTier — Master Prompt Bölüm 2.2'nin frontend kopyası.
 *
 * Formül:
 *   vram_margin = hw.vram_gb - model.required_vram_gb
 *   ram_margin  = hw.ram_gb  - model.required_ram_gb
 *
 *   vram_margin >= 2 AND ram_margin >= 4  -> "Tam Uyumlu"        (good)
 *   vram_margin >= 0 AND ram_margin >= 0  -> "Uyumlu (Sınırda)"  (warn)
 *   vram_margin >= -1.5                   -> "Dikkatli Kullan"   (orange)
 *   else                                   -> "Uygun Değil"      (bad)
 *
 * Eksik veri (required_vram_gb = null) durumunda not ipuçlarına güvenilir.
 */
export function computeTier(model, hw, th) {
  th = th || { vram_full_margin: 2.0, ram_full_margin: 4.0, vram_caution_margin: -1.5 };
  const flags = parseNotesFlags(model.notes);
  const rv = model.required_vram_gb;
  const rr = model.required_ram_gb;

  let tier, tone, vramMargin = null, ramMargin = null;

  if ((rv === null || rv === undefined) && (rr === null || rr === undefined)) {
    // Sayısal veri yok — not ipuçlarına güven (api/compat.py _tier_from_notes mirror)
    if (flags.loaded_into_vram && !flags.insufficient) {
      tier = 'Tam Uyumlu'; tone = 'good';
    } else if (flags.insufficient) {
      tier = 'Dikkatli Kullan'; tone = 'orange';
    } else {
      tier = 'Uyumlu (Sınırda)'; tone = 'warn';
    }
  } else {
    // Sayısal veri var — marjler; eksik alan 0 kabul edilir (backend ile aynı)
    vramMargin = hw.vram_gb - (rv || 0);
    ramMargin = hw.ram_gb - (rr || 0);
    const mode = String(model.run_mode || '').toLowerCase();
    if (mode === 'cpu' || mode === 'cpu_only') {
      // CPU modunda VRAM önemsiz, RAM'e bak (api/compat.py _tier_from_margins mirror)
      if (ramMargin >= th.ram_full_margin) { tier = 'Tam Uyumlu'; tone = 'good'; }
      else if (ramMargin >= 0) { tier = 'Uyumlu (Sınırda)'; tone = 'warn'; }
      else if (ramMargin >= th.vram_caution_margin) { tier = 'Dikkatli Kullan'; tone = 'orange'; }
      else { tier = 'Uygun Değil'; tone = 'bad'; }
    } else if (mode.indexOf('cpu_offload') !== -1 || mode.indexOf('mixed') !== -1) {
      // CPU offload: VRAM esnek (12GB eksik bile çalışabilir)
      if (vramMargin >= (th.vram_full_margin - 2.0) && ramMargin >= 0) { tier = 'Tam Uyumlu'; tone = 'good'; }
      else if (vramMargin >= -6.0 && ramMargin >= 0) { tier = 'Uyumlu (Sınırda)'; tone = 'warn'; }
      else if (vramMargin >= -12.0) { tier = 'Dikkatli Kullan'; tone = 'orange'; }
      else { tier = 'Uygun Değil'; tone = 'bad'; }
    } else {
      // GPU modu veya run_mode yok: katı mantık (backend varsayılanı)
      if (vramMargin >= th.vram_full_margin && ramMargin >= th.ram_full_margin) {
        tier = 'Tam Uyumlu'; tone = 'good';
      } else if (vramMargin >= 0 && ramMargin >= 0) {
        tier = 'Uyumlu (Sınırda)'; tone = 'warn';
      } else if (vramMargin >= th.vram_caution_margin) {
        tier = 'Dikkatli Kullan'; tone = 'orange';
      } else {
        tier = 'Uygun Değil'; tone = 'bad';
      }
    }
  }

  const isMoe = Boolean(model.is_moe || /8x7b|8x22b|moe|mixtral/i.test((model.name || '') + ' ' + (model.notes || '')));
  const activeParams = model.active_params_b || (isMoe ? (/8x22b/i.test(model.name) ? 39 : 13) : null);
  const totalParams = model.total_params_b || (isMoe ? (/8x22b/i.test(model.name) ? 141 : 47) : null);

  const vramStr = vramMargin !== null ? (vramMargin >= 0 ? '+' : '') + vramMargin.toFixed(1) + ' GB' : 'bilinmiyor';
  const ramStr = ramMargin !== null ? (ramMargin >= 0 ? '+' : '') + ramMargin.toFixed(1) + ' GB' : 'bilinmiyor';
  const reqVram = rv != null ? rv : 0;
  const explanation = "VRAM marjı: " + vramStr + " (donanım: " + hw.vram_gb + " GB, model gereksinimi: " + reqVram + " GB), RAM marjı: " + ramStr;
  const verifyCmd = "llmfit check " + (model.hf_id || model.name);

  return {
    tier, tone,
    vram_margin_gb: vramMargin,
    ram_margin_gb: ramMargin,
    is_moe: isMoe,
    active_params_b: activeParams,
    total_params_b: totalParams,
    context_flag: computeContextFlag(model),
    tooltip: buildTooltip(tier, model, hw, vramMargin, ramMargin),
    explanation: explanation,
    inputs: {
      vram_gb: hw.vram_gb,
      required_vram_gb: rv,
      ram_gb: hw.ram_gb,
      required_ram_gb: rr,
      run_mode: model.run_mode || ''
    },
    verify_cmd: verifyCmd
  };
}

export function computeContextFlag(model) {
  const est = model.context_length_estimated_at;
  const sup = model.context_length_supported;
  if (est != null && sup != null && est < sup) {
    return typeof window.t === 'function'
      ? window.t('ctx.restricted', { sup })
      : `Context kısıtlı tahmin edildi (gerçek limit: ${sup})`;
  }
  return null;
}

export function buildTooltip(tier, model, hw, vramMargin, ramMargin) {
  const hasT = typeof window.t === 'function';
  const lines = [hasT ? window.t('tooltip.tier', { tier }) : `Tier: ${tier}`];
  if (model.required_vram_gb != null) {
    const sign = (vramMargin || 0) >= 0 ? '+' : '';
    lines.push(
      hasT
        ? window.t('tooltip.vram', { req: model.required_vram_gb, yours: hw.vram_gb, sign, margin: (vramMargin || 0).toFixed(1) })
        : `Gerekli VRAM: ${model.required_vram_gb} GB | Senin: ${hw.vram_gb} GB | Boşluk: ${sign}${(vramMargin || 0).toFixed(1)} GB`
    );
  } else {
    lines.push(hasT ? window.t('tooltip.vramUnknown', { yours: hw.vram_gb }) : `Senin VRAM: ${hw.vram_gb} GB (gerekli değer bilinmiyor)`);
  }
  if (model.required_ram_gb != null) {
    const sign = (ramMargin || 0) >= 0 ? '+' : '';
    lines.push(
      hasT
        ? window.t('tooltip.ram', { req: model.required_ram_gb, yours: hw.ram_gb, sign, margin: (ramMargin || 0).toFixed(1) })
        : `Gerekli RAM: ${model.required_ram_gb} GB | Senin: ${hw.ram_gb} GB | Boşluk: ${sign}${(ramMargin || 0).toFixed(1)} GB`
    );
  } else {
    lines.push(hasT ? window.t('tooltip.ramUnknown', { yours: hw.ram_gb }) : `Senin RAM: ${hw.ram_gb} GB (gerekli değer bilinmiyor)`);
  }
  const est = model.context_length_estimated_at;
  const sup = model.context_length_supported;
  if (est != null && sup != null && est < sup) {
    lines.push(hasT ? window.t('tooltip.ctxEstimated', { est, sup }) : `Context: ${est} ile tahmin edildi (model gerçekte ${sup} destekliyor)`);
  } else if (sup != null) {
    lines.push(hasT ? window.t('tooltip.ctxSupports', { sup }) : `Context: ${sup} destekliyor`);
  } else if (est != null) {
    lines.push(hasT ? window.t('tooltip.ctxEst', { est }) : `Context: ${est} ile tahmin edildi`);
  }
  return lines.join('\n');
}

export const INTERCONNECT_BW = {
  single: 450.0,
  pcie3: 16.0,
  pcie4: 32.0,
  pcie5: 64.0,
  nvlink: 450.0,
  ethernet: 3.125,
};

export function effectiveBandwidth(interconnect = 'single', gpuCount = 1) {
  // api/compat.py effective_bandwidth_gb_s mirror (Adım 5, ADR-0016)
  const count = Math.max(1, gpuCount || 1);
  if (count <= 1) return 450.0;
  const linkBw = INTERCONNECT_BW[interconnect] ?? 450.0;
  const total = Math.min(450.0 * count, linkBw < 450 ? linkBw * count : 450.0 * count);
  return Math.round(total * (1 - 12.0 / 100.0) * 10) / 10;
}

export function simulateHardwareFit(
  paramCountB,
  quant = 'Q4_K_M',
  contextLength = 4096,
  userVramGb = null,
  userRamGb = null,
  gpuCount = 1,
  interconnect = 'single'
) {
  // api/compat.py simulate_hardware_fit mirror (Adım 5). VRAM toplamı +
  // etkin bant; geri uyumlu (tek GPU'da eski 450 sabiti).
  const bitsMap = { FP16: 16.0, BF16: 16.0, Q8_0: 8.5, Q6_K: 6.6, Q5_K_M: 5.5, Q5_K_S: 5.2, Q4_K_M: 4.5, Q4_K_XL: 4.6, Q4_0: 4.2, NVFP4: 4.0, Q3_K_M: 3.4, Q3_K_S: 3.2, IQ2_M: 2.6, IQ2_XXS: 2.2, PTQ1_0: 1.6 };
  const bits = bitsMap[String(quant).toUpperCase().replace(/-/g, '_')] ?? 4.5;
  const weightsGb = Math.round((paramCountB * 1e9 * (bits / 8.0)) / (1024 ** 3) * 100) / 100;
  const kvGb = Math.round(Math.max(0.1, (paramCountB / 7.0) * (contextLength / 4096.0) * 0.45) * 100) / 100;
  const overheadGb = 0.85;
  const totalReq = Math.round((weightsGb + kvGb + overheadGb) * 100) / 100;
  const perGpu = userVramGb ?? 12.0;
  const ram = userRamGb ?? 32.0;
  const count = Math.max(1, gpuCount || 1);
  const totalVram = perGpu * count;
  const margin = Math.round((totalVram - totalReq) * 100) / 100;
  const bw = effectiveBandwidth(interconnect, count);
  let fitStatus, tone, runMode, offloadPct, speedTps;
  if (margin >= 0) {
    offloadPct = 100.0; runMode = 'GPU';
    speedTps = Math.round(Math.min(125.0, bw / Math.max(1.0, weightsGb)) * 10) / 10;
    fitStatus = 'TAM_UYUMLU'; tone = 'good';
  } else if (totalReq <= totalVram + ram * 0.7) {
    const frac = Math.max(0.2, (totalVram - overheadGb - kvGb) / Math.max(1.0, weightsGb));
    offloadPct = Math.round(Math.min(95.0, frac * 100.0) * 10) / 10;
    runMode = 'CPU_OFFLOAD';
    speedTps = Math.round(Math.max(3.5, (bw / Math.max(1.0, weightsGb)) * (offloadPct / 100.0) * 0.35) * 10) / 10;
    fitStatus = 'DIKKATLI_KULLAN'; tone = 'orange';
  } else {
    offloadPct = 0.0; runMode = 'CPU_ONLY';
    speedTps = Math.round(Math.max(1.5, 60.0 / Math.max(1.0, weightsGb)) * 10) / 10;
    fitStatus = 'UYGUN_DEGIL'; tone = 'bad';
  }
  return {
    param_count_b: paramCountB, quantization: quant, context_length: contextLength,
    hardware: { vram_gb: perGpu, ram_gb: ram, gpu_count: count, interconnect },
    budget: { weights_gb: weightsGb, kv_cache_gb: kvGb, overhead_gb: overheadGb, total_required_vram_gb: totalReq, vram_margin_gb: margin },
    simulation: { fit_status: fitStatus, tone, run_mode: runMode, gpu_offload_pct: offloadPct, estimated_speed_tps: speedTps, effective_bandwidth_gb_s: bw },
  };
}
