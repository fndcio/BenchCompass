/**
 * tests/frontend/gpu-telemetry.test.js
 *
 * Özellik 3 (Telemetri Eşik Uyarıları) — denetim kapanışı:
 * 92–96 VRAM sarı bandı, 75–82 sıcaklık bandı, sınır değerleri ve
 * backend eşik beslemesi (tek kaynak, Y17) kapsanır.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import '../../web/app.js';
import '../../web/i18n.js';

describe('Telemetri Eşik Uyarıları (Özellik 3 — bant ve tek kaynak)', () => {
  let app;

  beforeEach(() => {
    app = globalThis.dashboard();
    globalThis.setLang('tr');
  });

  const gpuPayload = (over = {}) => ({
    available: true,
    used_pct: 50,
    level: 'ok',
    temp_c: 60,
    warn_pct: 92,
    crit_pct: 96,
    temp_warn_c: 75,
    temp_crit_c: 82,
    vram_total_mb: 12288,
    vram_used_mb: 6144,
    power_w: 95,
    util_pct: 30,
    ...over,
  });

  const runPoll = async (payload) => {
    app.getJson = vi.fn().mockResolvedValue(payload);
    await app.pollGpu();
    return app.telemetryAlerts;
  };

  it('eşik altı değerlerde uyarı üretilmez', async () => {
    const alerts = await runPoll(gpuPayload({ used_pct: 91.9, temp_c: 74.9 }));
    expect(alerts).toHaveLength(0);
  });

  it('VRAM warn bandı (92–95.9) sarı uyarı üretir', async () => {
    const a1 = await runPoll(gpuPayload({ used_pct: 92 }));
    expect(a1).toHaveLength(1);
    expect(a1[0].type).toBe('vram');
    expect(a1[0].level).toBe('warn');

    const a2 = await runPoll(gpuPayload({ used_pct: 95.9 }));
    expect(a2).toHaveLength(1);
    expect(a2[0].level).toBe('warn');
  });

  it('VRAM crit sınırı (≥96) kırmızı uyarı üretir', async () => {
    const alerts = await runPoll(gpuPayload({ used_pct: 96 }));
    expect(alerts).toHaveLength(1);
    expect(alerts[0].type).toBe('vram');
    expect(alerts[0].level).toBe('crit');
  });

  it('sıcaklık warn bandı (75–81.9) ve crit sınırı (≥82)', async () => {
    const w1 = await runPoll(gpuPayload({ temp_c: 75 }));
    expect(w1.some((a) => a.type === 'temp' && a.level === 'warn')).toBe(true);

    const w2 = await runPoll(gpuPayload({ temp_c: 81.9 }));
    expect(w2.some((a) => a.type === 'temp' && a.level === 'warn')).toBe(true);

    const c = await runPoll(gpuPayload({ temp_c: 82 }));
    expect(c.some((a) => a.type === 'temp' && a.level === 'crit')).toBe(true);
  });

  it('backend eşik alanları frontend davranışını yönetir (tek kaynak, Y17)', async () => {
    // Backend crit_pct=88 derse 90 kullanım crit'tir — frontend sabiti değil API kazanır.
    const alerts = await runPoll(gpuPayload({ used_pct: 90, crit_pct: 88, level: 'ok' }));
    expect(alerts.some((a) => a.type === 'vram' && a.level === 'crit')).toBe(true);
  });

  it('eşik alanları yoksa frontend fallback sabitleri geçerli kalır', async () => {
    const alerts = await runPoll({ available: true, used_pct: 93, level: 'ok', temp_c: 50 });
    expect(alerts.some((a) => a.type === 'vram' && a.level === 'warn')).toBe(true);
  });
});
