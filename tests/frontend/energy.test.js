// Sprint 45: Enerji/maliyet frontend testleri — model listesi + rapor çekme.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import '../../web/app.js';

const d = () => globalThis.dashboard();

describe('loadEnergyModels', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('modeller yüklenir ve ilk model seçilir', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({
        models: [
          { model: 'qwen3:8b', measured_tps: 41.2, last_at: 'x' },
          { model: 'muse:30b', measured_tps: 7.5, last_at: 'y' },
        ],
      }),
    });
    const state = d();
    state.energyModel = '';
    await state.loadEnergyModels();
    expect(state.energyModels).toHaveLength(2);
    expect(state.energyModel).toBe('qwen3:8b'); // en yenisi otomatik seçili
  });

  it('fetch hatası → boş liste (graceful)', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('yok'));
    const state = d();
    await state.loadEnergyModels();
    expect(state.energyModels).toEqual([]);
  });
});

describe('loadEnergyReport', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('rapor state\'e yazılır', async () => {
    const report = {
      model: 'qwen3:8b', measured_tps: 40, power_w: 95, power_source: 'live',
      tok_per_joule: 0.42, kwh_month: 5.7, cost_try_month: 14.25,
      cloud_cost_try_month: 138.0, local_vs_cloud_ratio: 0.103,
      co2_monthly_g: 2565.0, co2_car_km_equiv: 21.4,
    };
    const mock = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => report,
    });
    const state = d();
    state.energyModel = 'qwen3:8b';
    await state.loadEnergyReport();
    // model adı URL-güvenli kodlanır (':' → %3A); backend path param'ı çözer
    expect(mock).toHaveBeenCalledWith(expect.stringContaining('/api/telemetry/energy/qwen3%3A8b'));
    expect(state.energyReport).toEqual(report);
    expect(state.energyReport.co2_monthly_g).toBe(2565.0);
    expect(state.energyReport.co2_car_km_equiv).toBe(21.4);
    expect(state.energyLoading).toBe(false);
  });

  it('model boşsa istek atılmaz', async () => {
    const mock = vi.spyOn(globalThis, 'fetch');
    const state = d();
    state.energyModel = '';
    await state.loadEnergyReport();
    expect(mock).not.toHaveBeenCalled();
  });

  it('404 → energyError dolar, rapor null kalır', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ detail: 'benchmark yok' }),
    });
    const state = d();
    state.energyModel = 'olmayan';
    await state.loadEnergyReport();
    expect(state.energyReport).toBeNull();
    expect(state.energyError).toBeTruthy();
  });
});
