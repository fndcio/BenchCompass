// P1-2: Tahmin İsabeti paneli frontend testleri — model listesi deseni (energy.test.js) izlenir.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import '../../web/app.js';

const d = () => globalThis.dashboard();

describe('loadCalibration', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('özet state\'e yazılır', async () => {
    const ozet = {
      n: 2,
      mean_delta_pct: 5.0,
      abs_mean_delta_pct: 5.0,
      std_delta_pct: 3.0,
      median_delta_pct: 4.5,
      accuracy_band: 'green',
      within_10_pct_ratio: 1.0,
      within_25_pct_ratio: 1.0,
      records: [
        { model: 'qwen3:8b', measured_tps: 41.2, predicted_tps: 39.2, prediction_delta_pct: 5.1, created_at: 'x' },
        { model: 'muse:30b', measured_tps: 7.5, predicted_tps: 8.0, prediction_delta_pct: -6.25, created_at: 'y' },
      ],
    };
    const mock = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ozet,
    });
    const state = d();
    await state.loadCalibration();
    expect(mock).toHaveBeenCalledWith(expect.stringContaining('/api/calibration/summary'));
    expect(state.calib).toEqual(ozet);
    expect(state.calibLoading).toBe(false);
    expect(state.calibError).toBe('');
  });

  it('n=0 → calib boş özetle dolar, hata yok', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({
        n: 0,
        mean_delta_pct: null,
        accuracy_band: 'insufficient_data',
        within_10_pct_ratio: 0.0,
        within_25_pct_ratio: 0.0,
        records: [],
      }),
    });
    const state = d();
    await state.loadCalibration();
    expect(state.calib.n).toBe(0);
    expect(state.calibError).toBe('');
  });

  it('fetch hatası → calib null + calibError dolar (graceful)', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('yok'));
    const state = d();
    await state.loadCalibration();
    expect(state.calib).toBeNull();
    expect(state.calibError).toBeTruthy();
  });
});

describe('calibBand helpers', () => {
  it('bant etiketleri doğru i18n anahtarına düşer', () => {
    const s = d();
    expect(s.calibBandLabel('green')).toBe(s.t('calib.bandGreen'));
    expect(s.calibBandLabel('yellow')).toBe(s.t('calib.bandYellow'));
    expect(s.calibBandLabel('red')).toBe(s.t('calib.bandRed'));
    expect(s.calibBandLabel('insufficient_data')).toBe(s.t('calib.bandInsufficient'));
  });

  it('bant renkleri eşleşir', () => {
    const s = d();
    expect(s.calibBandColor('green')).toBe('#3fb950');
    expect(s.calibBandColor('yellow')).toBe('#d29922');
    expect(s.calibBandColor('red')).toBe('#f85149');
    expect(s.calibBandColor('bilinmeyen')).toBe('');
  });
});
