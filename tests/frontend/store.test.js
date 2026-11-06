import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import '../../web/app.js';

describe('Mağaza — yerel katalog modu (Sprint 19)', () => {
  let d;

  beforeEach(() => {
    d = dashboard();
    d.apiBase = 'http://localhost:8788';
    d.storeQuery = 'qwen';
    d.storeResults = [];
    d.storeSource = 'hf';
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('yerel katalog sonuç dönerse HF aramaya geçmez', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
      if (String(url).includes('/api/catalog/search')) {
        return {
          ok: true,
          json: async () => ({
            total: 2,
            source: 'local-catalog',
            models: [
              { name: 'Qwen/Qwen3-7B', quantization: 'Q4_K_M', required_vram_gb: 6, context_window: 32768, is_moe: false },
              { name: 'Qwen/Qwen3-Coder-7B', quantization: 'Q4_K_M', required_vram_gb: 7, context_window: 65536, is_moe: false },
            ],
          }),
        };
      }
      throw new Error('HF arama çağrılmamalı: ' + url);
    });

    await d.searchStore();

    expect(d.storeSource).toBe('local-catalog');
    expect(d.storeResults.length).toBe(2);
    expect(d.storeResults[0].repo).toBe('Qwen/Qwen3-7B');
    expect(d.storeResults[0].context_window).toBe(32768);
    // HF arama çağrılmamalı
    const hfCalls = fetchSpy.mock.calls.filter(c => String(c[0]).includes('/api/hf-search'));
    expect(hfCalls.length).toBe(0);
  });

  it('yerel katalog boşsa HF aramaya geçer', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
      if (String(url).includes('/api/catalog/search')) {
        return { ok: true, json: async () => ({ models: [], source: 'local-catalog', total: 0 }) };
      }
      if (String(url).includes('/api/hf-search')) {
        return { ok: true, json: async () => ({ models: [{ repo: 'hf-model-x', quant: 'Q4_K_M' }] }) };
      }
      throw new Error('beklenmeyen: ' + url);
    });

    await d.searchStore();

    expect(d.storeSource).toBe('hf');
    expect(d.storeResults.length).toBe(1);
    expect(d.storeResults[0].repo).toBe('hf-model-x');
  });

  it('yerel katalog ve HF boşsa sonuç yok ve toast gösterir', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
      if (String(url).includes('/api/catalog/search')) {
        return { ok: true, json: async () => ({ models: [], total: 0 }) };
      }
      if (String(url).includes('/api/hf-search')) {
        return { ok: true, json: async () => ({ models: [] }) };
      }
      throw new Error('beklenmeyen: ' + url);
    });
    const toastSpy = vi.spyOn(d, 'toast').mockImplementation(() => {});

    await d.searchStore();

    expect(d.storeSource).toBe('none');
    expect(d.storeResults).toEqual([]);
    expect(toastSpy).toHaveBeenCalled();
  });

  it('boş sorgu ile arama yapılmaz', async () => {
    d.storeQuery = '   ';
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    await d.searchStore();
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe('Karar asistanı hibrit fit + baseline (Sprint 21)', () => {
  let d;

  beforeEach(() => {
    d = dashboard();
    d.apiBase = 'http://localhost:8788';
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('_hybridFit', () => {
    it('family_score yoksa fitScore döner', () => {
      expect(d._hybridFit({ fitScore: 80 })).toBe(80);
    });

    it('family_score varsa %30 ağırlık ekler', () => {
      expect(d._hybridFit({ fitScore: 80, family_score: 90 })).toBe(107);
    });

    it('her ikisi de yoksa 0', () => {
      expect(d._hybridFit({})).toBe(0);
    });
  });

  describe('loadBaseline', () => {
    it('baseline verisini yükler', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => ({
          model: 'yerel-model',
          role: 'coding',
          baseline: { model: 'claude-sonnet-4-5', quality: 9.5, speed: 80, composite: 9.6 },
          top_baseline: { model: 'claude-sonnet-4-5', composite: 9.6 },
          available: true,
        }),
      });

      await d.loadBaseline('yerel-model');

      expect(d.baselineData.role).toBe('coding');
      expect(d.baselineData.baseline.model).toBe('claude-sonnet-4-5');
      expect(d.baselineLoading).toBe(false);
    });

    it('hata durumunda baselineError set edilir', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => ({ error: 'bozuk' }),
      });

      await d.loadBaseline('x');

      expect(d.baselineError).toBeTruthy();
      expect(d.baselineLoading).toBe(false);
    });
  });
});
