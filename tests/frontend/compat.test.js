import { describe, expect, it } from 'vitest';
import { computeTier } from '../../web/app.js';

describe('computeTier (AGENTS.md G8 Harmony)', () => {
  const hw = { vram_gb: 12, ram_gb: 32 };
  const th = { vram_full_margin: 2.0, ram_full_margin: 4.0, vram_caution_margin: -1.5 };

  it('computes Tam Uyumlu when VRAM and RAM margins are ample', () => {
    const model = { required_vram_gb: 8.0, required_ram_gb: 16.0 };
    const res = computeTier(model, hw, th);
    expect(res.tier).toBe('Tam Uyumlu');
    expect(res.tone).toBe('good');
    expect(res.vram_margin_gb).toBe(4.0);
    expect(res.ram_margin_gb).toBe(16.0);
  });

  it('computes Uyumlu (Sınırda) when margins are non-negative but below thresholds', () => {
    const model = { required_vram_gb: 11.0, required_ram_gb: 30.0 };
    const res = computeTier(model, hw, th);
    expect(res.tier).toBe('Uyumlu (Sınırda)');
    expect(res.tone).toBe('warn');
  });

  it('computes Dikkatli Kullan when VRAM margin is slightly negative above caution threshold', () => {
    const model = { required_vram_gb: 13.0, required_ram_gb: 30.0 };
    const res = computeTier(model, hw, th);
    expect(res.tier).toBe('Dikkatli Kullan');
    expect(res.tone).toBe('orange');
  });

  it('computes Uygun Değil when VRAM is far below caution margin', () => {
    const model = { required_vram_gb: 24.0, required_ram_gb: 64.0 };
    const res = computeTier(model, hw, th);
    expect(res.tier).toBe('Uygun Değil');
    expect(res.tone).toBe('bad');
  });

  it('handles missing numerical data using notes hints', () => {
    const loadedModel = { notes: 'Loaded into VRAM successfully' };
    const resLoaded = computeTier(loadedModel, hw, th);
    expect(resLoaded.tier).toBe('Tam Uyumlu');

    const insufficientModel = { notes: 'Insufficient VRAM for offloading' };
    const resInsuff = computeTier(insufficientModel, hw, th);
    expect(resInsuff.tier).toBe('Dikkatli Kullan');
  });

  it('detects Mixture-of-Experts (MoE) models and computes active/total params', () => {
    const moeModel = { name: 'Mixtral-8x7B-Instruct-v0.1', required_vram_gb: 12.0, required_ram_gb: 32.0 };
    const res = computeTier(moeModel, hw, th);
    expect(res.is_moe).toBe(true);
    expect(res.active_params_b).toBe(13);
    expect(res.total_params_b).toBe(47);
  });

  it('mirrors CPU run_mode: RAM-only margins (api/compat.py _tier_from_margins)', () => {
    // CPU modunda VRAM önemsiz — büyük VRAM gerekse de RAM rahatsa Tam Uyumlu
    const cpuModel = { required_vram_gb: 30.0, required_ram_gb: 16.0, run_mode: 'CPU' };
    const res = computeTier(cpuModel, hw, th);
    expect(res.tier).toBe('Tam Uyumlu');
    expect(res.tone).toBe('good');
  });

  it('mirrors cpu_offload: VRAM esnek pay (vram_full_margin - 2.0)', () => {
    const offloadModel = { required_vram_gb: 13.0, required_ram_gb: 30.0, run_mode: 'CPU_offload' };
    const res = computeTier(offloadModel, hw, th);
    // vram_margin = -1.0 >= (2.0 - 2.0 = 0.0) DEĞİL ama >= -6.0 ve RAM >= 0 → Sınırda
    expect(res.tier).toBe('Uyumlu (Sınırda)');
    expect(res.tone).toBe('warn');
  });

  it('mirrors mixed: deep VRAM overshoot still Dikkatli Kullan', () => {
    const mixedModel = { required_vram_gb: 24.0, required_ram_gb: 32.0, run_mode: 'Mixed' };
    const res = computeTier(mixedModel, hw, th);
    // vram_margin = -12.0 → >= -12.0 olduğu için Dikkatli Kullan (RAM negatif değil)
    expect(res.tier).toBe('Dikkatli Kullan');
    expect(res.tone).toBe('orange');
  });

  it('backward-compat: rv null + rr set goes to margins with rv treated as 0', () => {
    // Backend: rv yoksa 0 kabul edilir → vram_margin = hw.vram (12). GPU katı mantık.
    const ramOnly = { required_ram_gb: 16.0 };
    const res = computeTier(ramOnly, hw, th);
    expect(res.tier).toBe('Tam Uyumlu');
    expect(res.vram_margin_gb).toBe(12.0);
  });
});

describe('guideCalcTier (Sprint 10 kid-friendly tier widget)', () => {
  it('returns Tam Uyumlu with good tone and green emoji for ample margins', () => {
    const d = dashboard();
    d.guideInteractiveVram = 16;
    d.guideInteractiveModelVram = 8;
    d.guideInteractiveRam = 64;
    d.guideInteractiveModelRam = 16;
    const res = d.guideCalcTier;
    expect(res.tier).toBe('Tam Uyumlu');
    expect(res.tone).toBe('good');
    expect(res.emoji).toBe('🟢');
    expect(res.vramMargin).toBe(8);
  });

  it('returns Uygun Değil with bad tone and red emoji for insufficient VRAM', () => {
    const d = dashboard();
    d.guideInteractiveVram = 8;
    d.guideInteractiveModelVram = 24;
    const res = d.guideCalcTier;
    expect(res.tier).toBe('Uygun Değil');
    expect(res.tone).toBe('bad');
    expect(res.emoji).toBe('🔴');
  });

  it('returns Dikkatli Kullan with orange emoji for slightly negative margin', () => {
    const d = dashboard();
    d.guideInteractiveVram = 12;
    d.guideInteractiveModelVram = 13;
    d.guideInteractiveRam = 32;
    d.guideInteractiveModelRam = 16;
    const res = d.guideCalcTier;
    expect(res.tier).toBe('Dikkatli Kullan');
    expect(res.tone).toBe('orange');
    expect(res.emoji).toBe('🟠');
  });
});

describe('guideGeneratedCliCommand (Sprint 10 CLI generator widget)', () => {
  it('maps fit subcommand to llmfit fit --json --good', () => {
    const d = dashboard();
    d.guideInteractiveCliCmd = 'fit';
    expect(d.guideGeneratedCliCommand).toBe('llmfit fit --json --good');
  });

  it('maps doctor subcommand to llmfit doctor', () => {
    const d = dashboard();
    d.guideInteractiveCliCmd = 'doctor';
    expect(d.guideGeneratedCliCommand).toBe('llmfit doctor');
  });

  it('maps recommend subcommand with args', () => {
    const d = dashboard();
    d.guideInteractiveCliCmd = 'recommend';
    expect(d.guideGeneratedCliCommand).toBe('llmfit recommend --use-case coding --limit 5 --json');
  });
});


describe('openTierWhy (P0-3 Karar Seffafligi UI)', () => {
  it('populates tierWhyData and opens modal with explanation and inputs', () => {
    const d = dashboard();
    const model = {
      name: 'qwen2.5:7b',
      required_vram_gb: 5.5,
      required_ram_gb: 16.0,
      run_mode: 'GPU'
    };
    d.openTierWhy(model);
    expect(d.tierWhyModalOpen).toBe(true);
    expect(d.tierWhyData).toBeTruthy();
    expect(d.tierWhyData.model_name).toBe('qwen2.5:7b');
    expect(d.tierWhyData.tier).toBe('Tam Uyumlu');
    expect(d.tierWhyData.explanation).toContain('VRAM');
    expect(d.tierWhyData.inputs.vram_gb).toBe(12);
    expect(d.tierWhyData.inputs.required_vram_gb).toBe(5.5);
    expect(d.tierWhyData.verify_cmd).toBe('llmfit check qwen2.5:7b');
  });

  it('handles null model gracefully without crashing', () => {
    const d = dashboard();
    d.tierWhyModalOpen = false;
    d.openTierWhy(null);
    expect(d.tierWhyModalOpen).toBe(false);
  });
});

describe('simulateHardwareFit mirror (Adım 5, G8)', () => {
  it('geri uyumlu: tek GPU 450 GB/s', async () => {
    const { simulateHardwareFit, effectiveBandwidth } = await import('../../web/modules/tier.js');
    expect(effectiveBandwidth('single', 1)).toBe(450.0);
    expect(effectiveBandwidth('nvlink', 2)).toBe(792.0);
    const r = simulateHardwareFit(8.0, 'Q4_K_M', 4096, 12, 32, 1, 'single');
    expect(r.simulation.fit_status).toBe('TAM_UYUMLU');
    expect(r.simulation.effective_bandwidth_gb_s).toBe(450.0);
  });

  it('Ethernet darboğazı NVLink\'den yavaş', async () => {
    const { simulateHardwareFit } = await import('../../web/modules/tier.js');
    const eth = simulateHardwareFit(8.0, 'Q4_K_M', 4096, 12, 32, 2, 'ethernet');
    const nv = simulateHardwareFit(8.0, 'Q4_K_M', 4096, 12, 32, 2, 'nvlink');
    expect(eth.simulation.estimated_speed_tps).toBeLessThan(nv.simulation.estimated_speed_tps);
  });
});
