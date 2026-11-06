// Sprint 44: GPU telemetri frontend testleri — format helper'ları + pollGpu.
// Desen: import app.js → globalThis export wrapper'ı (diğer frontend testleriyle aynı).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import '../../web/app.js';

const d = () => globalThis.dashboard();

describe('GPU format helper\'ları', () => {
  it('fmtMb — MB\'den GB\'ye çevirir, null için -', () => {
    expect(globalThis.fmtMb(8192)).toBe('8.0 GB');
    expect(globalThis.fmtMb(12288)).toBe('12.0 GB');
    expect(globalThis.fmtMb(null)).toBe('-');
    expect(globalThis.fmtMb(undefined)).toBe('-');
  });

  it('fmtW — W cinsine yuvarlar, null için -', () => {
    expect(globalThis.fmtW(85.32)).toBe('85 W');
    expect(globalThis.fmtW(null)).toBe('-');
  });

  it('fmtPct — yüzde formatlar, null için -', () => {
    expect(globalThis.fmtPct(66.7)).toBe('67%');
    expect(globalThis.fmtPct(null)).toBe('-');
  });

  it('gpuLevelColor — seviyeye göre renk döner', () => {
    const state = d();
    expect(state.gpuLevelColor('crit')).toBe('#f85149');
    expect(state.gpuLevelColor('warn')).toBe('#d29922');
    expect(state.gpuLevelColor('ok')).toBe('#58a6ff');
  });
});

describe('pollGpu — telemetri çekme döngüsü', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('available=true → state güncellenir ve history\'ye nokta eklenir', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({
        available: true,
        vram_total_mb: 12288,
        vram_used_mb: 8192,
        temp_c: 45,
        power_w: 85.5,
        util_pct: 30,
        used_pct: 66.7,
        level: 'ok',
        ts: '2026-08-18T00:00:00+00:00',
      }),
    });
    const state = d();
    state.gpuHistory = [];
    await state.pollGpu();
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/telemetry/gpu'));
    expect(state.gpu.available).toBe(true);
    expect(state.gpu.level).toBe('ok');
    expect(state.gpuHistory).toHaveLength(1);
    expect(state.gpuHistory[0].usedPct).toBe(66.7);
    expect(state.gpuHistory[0].temp).toBe(45);
    expect(state.telemetryAlerts).toHaveLength(0);
  });

  it('used_pct >= 96 veya temp_c >= 82 olduğunda telemetryAlerts dolar', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({
        available: true,
        vram_total_mb: 12288,
        vram_used_mb: 11900,
        temp_c: 84,
        power_w: 160.0,
        util_pct: 99,
        used_pct: 96.8,
        level: 'crit',
      }),
    });
    const state = d();
    await state.pollGpu();
    expect(state.telemetryAlerts.length).toBeGreaterThanOrEqual(2);
    expect(state.telemetryAlerts.some((a) => a.type === 'vram' && a.level === 'crit')).toBe(true);
    expect(state.telemetryAlerts.some((a) => a.type === 'temp' && a.level === 'crit')).toBe(true);
  });

  it('available=false → state dürüstçe kapanır, history dokunulmaz', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ available: false, error: 'nvidia-smi yok' }),
    });
    const state = d();
    state.gpuHistory = [{ label: 'x', usedPct: 1, temp: 1, power: 1, util: 1 }];
    await state.pollGpu();
    expect(state.gpu.available).toBe(false);
    expect(state.gpuHistory).toHaveLength(1);
  });

  it('fetch hatası → graceful degradation (available=false)', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('bağlantı yok'));
    const state = d();
    await state.pollGpu();
    expect(state.gpu.available).toBe(false);
  });

  it('history ring buffer 100 noktayı aşmaz', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({
        available: true, vram_used_mb: 1, used_pct: 1, temp_c: 1, power_w: 1, util_pct: 1,
      }),
    });
    const state = d();
    state.gpuHistory = Array.from({ length: 100 }, (_, i) => ({
      label: String(i), usedPct: i, temp: i, power: i, util: i,
    }));
    await state.pollGpu();
    expect(state.gpuHistory).toHaveLength(100);
  });
});

describe('loadMatrix — hata durumu dürüst raporlanır', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('HTTP 503 → matrixData null, matrixError dolu, loading kapanır', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({ ok: false, status: 503 });
    const state = d();

    await state.loadMatrix();

    expect(state.matrixData).toBeNull();
    expect(state.matrixError).toContain('503');
    expect(state.matrixLoading).toBe(false);
  });

  it('başarılı yükleme matrixError alanını temizler', async () => {
    const state = d();
    state.matrixError = 'eski hata';
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ roles: [] }),
    });

    await state.loadMatrix();

    expect(state.matrixData).toEqual({ roles: [] });
    expect(state.matrixError).toBe('');
  });
});
