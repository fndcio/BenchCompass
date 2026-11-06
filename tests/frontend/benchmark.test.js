import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import '../../web/app.js';

describe('Benchmark kaynak rozeti (Sprint 23 G4)', () => {
  let d;

  beforeEach(() => {
    d = dashboard();
    d.apiBase = 'http://localhost:8788';
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('benchmarkSourceLabel', () => {
    it('real → GERÇEK YEREL ÖLÇÜM rozeti', () => {
      expect(d.benchmarkSourceLabel('real')).toBe('GERÇEK YEREL ÖLÇÜM');
    });

    it('community → TOPLULUK ÖLÇÜMÜ rozeti', () => {
      expect(d.benchmarkSourceLabel('community')).toBe('TOPLULUK ÖLÇÜMÜ');
    });

    it('estimate → TAHMİN rozeti', () => {
      expect(d.benchmarkSourceLabel('estimate')).toBe('TAHMİN');
    });

    it('kaynak yoksa varsayılan TAHMİN (geri uyumlu)', () => {
      expect(d.benchmarkSourceLabel(undefined)).toBe('TAHMİN');
      expect(d.benchmarkSourceLabel(null)).toBe('TAHMİN');
    });
  });

  describe('benchmarkOllamaModel — source yayılımı', () => {
    it('sonuç source alanını m.benchmark.source olarak iletir', async () => {
      d.installedModels = [{ name: 'qwen3:8b' }];
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => ({
          ok: true,
          result: { measured_tps: 45.2, ttft_ms: 120, source: 'real' },
        }),
      });
      vi.spyOn(d, 'toast').mockImplementation(() => {});

      await d.benchmarkOllamaModel('qwen3:8b');

      expect(d.installedModels[0].benchmark.measured_tps).toBe(45.2);
      expect(d.installedModels[0].benchmark.source).toBe('real');
      expect(d.installedModels[0]._benchmarking).toBe(false);
    });

    it('community sonucunda source=community iletilir', async () => {
      d.installedModels = [{ name: 'Qwen/Qwen3-8B' }];
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => ({
          ok: true,
          result: { measured_tps: 88.0, ttft_ms: 200, source: 'community' },
        }),
      });
      vi.spyOn(d, 'toast').mockImplementation(() => {});

      await d.benchmarkOllamaModel('Qwen/Qwen3-8B');

      expect(d.installedModels[0].benchmark.source).toBe('community');
    });

    it('ok:false gelirse hata gösterilir ve source set edilmez', async () => {
      d.installedModels = [{ name: 'olmayan' }];
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => ({ ok: false, error: 'ölçüm yapılamadı' }),
      });
      const toastSpy = vi.spyOn(d, 'toast').mockImplementation(() => {});

      await d.benchmarkOllamaModel('olmayan');

      expect(d.installedModels[0].benchmark).toBeUndefined();
      expect(toastSpy).toHaveBeenCalled();
      expect(d.installedModels[0]._benchmarking).toBe(false);
    });
  });

  describe('ensureBenchmarkModels (model seçim listesi — Sprint 27 sonrası)', () => {
    it('installedModels boşsa Ollama modellerini yükler', async () => {
      d.installedModels = [];
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => ({ ok: true, models: [{ name: 'qwen3:8b' }, { name: 'llama3:8b' }] }),
      });

      await d.ensureBenchmarkModels();

      expect(d.installedModels.map(m => m.name)).toEqual(['qwen3:8b', 'llama3:8b']);
    });

    it('installedModels doluysa tekrar yüklemez', async () => {
      d.installedModels = [{ name: 'qwen3:8b' }];
      const loadSpy = vi.spyOn(d, 'loadOllamaModels').mockResolvedValue();

      await d.ensureBenchmarkModels();

      expect(loadSpy).not.toHaveBeenCalled();
    });

    it('yükleme sırasında tekrar çağrılırsa ikinci yükleme atlanır', async () => {
      d.installedModels = [];
      d.installedModelsLoading = true;
      const loadSpy = vi.spyOn(d, 'loadOllamaModels').mockResolvedValue();

      await d.ensureBenchmarkModels();

      expect(loadSpy).not.toHaveBeenCalled();
    });
  });

  describe('_pollBenchmark — Adım 2 ITL/ttft_method yayılımı', () => {
    it('benchmarkResult itl_ms ve ttft_method alanlarını korur', async () => {
      d.benchmarkTaskId = 't-123';
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => ({
          status: 'completed',
          result: {
            measured_tps: 42.0,
            ttft_ms: 80.0,
            ttft_method: 'streaming',
            itl_ms: 12.5,
            source: 'real',
          },
        }),
      });
      vi.spyOn(d, '_refreshBenchmarkHistory').mockImplementation(() => {});
      vi.spyOn(d, 'toast').mockImplementation(() => {});

      await d._pollBenchmark();

      expect(d.benchmarkResult.itl_ms).toBe(12.5);
      expect(d.benchmarkResult.ttft_method).toBe('streaming');
    });
  });

  describe('loadNormalizedScore & SINIF SKORU rozeti (P1-1)', () => {
    it('loadNormalizedScore API çağrısı yapıp skoru döner', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => ({
          model: 'qwen3:8b',
          measured_tps: 45.0,
          ref_tps: 40.0,
          score: 112.5,
          unit: '% of class average',
        }),
      });

      const score = await d.loadNormalizedScore('qwen3:8b', 45.0);
      expect(score).toBe(112.5);
    });

    it('benchmark tamamlandığında class_score m.benchmark nesnesine eklenir', async () => {
      d.installedModels = [{ name: 'qwen3:8b' }];
      vi.spyOn(d, 'toast').mockImplementation(() => {});
      vi.spyOn(d, 'refreshFromDb').mockResolvedValue();

      vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
        if (typeof url === 'string' && url.includes('/api/score/normalized')) {
          return {
            ok: true,
            json: async () => ({ model: 'qwen3:8b', score: 108.2 }),
          };
        }
        return {
          ok: true,
          json: async () => ({
            ok: true,
            result: { measured_tps: 42.0, ttft_ms: 110, source: 'real' },
          }),
        };
      });

      await d.benchmarkOllamaModel('qwen3:8b');
      expect(d.installedModels[0].benchmark.measured_tps).toBe(42.0);
      expect(d.installedModels[0].benchmark.class_score).toBe(108.2);
    });
  });

});
