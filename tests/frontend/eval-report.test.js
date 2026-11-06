import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import '../../web/app.js';

describe('Eval rapor durumu (Sprint 27 C1 — [ RAPOR ] boş durum)', () => {
  let d;

  beforeEach(() => {
    d = dashboard();
    d.apiBase = 'http://localhost:8788';
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('checkEvalReport', () => {
    it('rapor varsa evalReportExists=true ve updated_at set eder', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => ({ exists: true, updated_at: '2026-08-04T10:00:00', path: 'x' }),
      });

      await d.checkEvalReport();

      expect(d.evalReportExists).toBe(true);
      expect(d.evalReportUpdatedAt).toBe('2026-08-04T10:00:00');
      expect(d.evalReportChecked).toBe(true);
    });

    it('rapor yoksa evalReportExists=false (iframe yerine mesaj)', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => ({ exists: false, updated_at: null, path: 'x' }),
      });

      await d.checkEvalReport();

      expect(d.evalReportExists).toBe(false);
      expect(d.evalReportUpdatedAt).toBeNull();
      expect(d.evalReportChecked).toBe(true);
    });

    it('hata durumunda exists=false (boş durum korunur)', async () => {
      vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('network'));

      await d.checkEvalReport();

      expect(d.evalReportExists).toBe(false);
      expect(d.evalReportChecked).toBe(true);
    });
  });

  describe('loadEvalHistory (Sprint 34 P2)', () => {
    it('history listesini yükler', async () => {
      const runs = [
        { id: 1, model: 'qwen3:8b', measured_tps: 45.2, ttft_ms: 120, source: 'real' },
      ];
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => ({ ok: true, runs }),
      });

      await d.loadEvalHistory();

      expect(d.evalHistoryLoading).toBe(false);
      expect(d.evalHistory).toEqual(runs);
    });

    it('boş veri geldiğinde evalHistory=[] (boş durum)', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => ({ ok: true, runs: [] }),
      });

      await d.loadEvalHistory();

      expect(d.evalHistory).toEqual([]);
    });

    it('hata durumunda evalHistory=[] (çökmez)', async () => {
      vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('network'));

      await d.loadEvalHistory();

      expect(d.evalHistoryLoading).toBe(false);
      expect(d.evalHistory).toEqual([]);
    });

    it('checkEvalReport geçmiş listesini de tetikler', async () => {
      const calls = [];
      vi.spyOn(globalThis, 'fetch').mockImplementation((url) => {
        calls.push(String(url));
        return Promise.resolve({
          ok: true,
          json: async () =>
            String(url).includes('report-status')
              ? { exists: true, updated_at: null }
              : { ok: true, runs: [] },
        });
      });

      await d.checkEvalReport();

      expect(calls.some((u) => u.includes('/api/eval/history'))).toBe(true);
    });
  });

  describe('loadEvalCompare (Adım 3 McNemar)', () => {
    it('iki model seçili ise karşılaştırmayı yükler', async () => {
      d.compareModelA = 'model-a';
      d.compareModelB = 'model-b';
      const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => ({
          ok: true,
          model_a: 'model-a',
          model_b: 'model-b',
          n: 3,
          b: 1,
          c: 0,
          discordant: 1,
          p_value: 1.0,
          significant: false,
          tasks: [{ id: 'G1', a_pass: true, b_pass: true, category: 'both_pass' }],
        }),
      });

      await d.loadEvalCompare();

      expect(fetchSpy).toHaveBeenCalledWith(expect.stringContaining('/api/eval/compare'));
      expect(d.evalCompare.model_a).toBe('model-a');
      expect(d.evalCompareLoading).toBe(false);
    });

    it('model eksikse hata mesajı gösterir, fetch çağırmaz', async () => {
      d.compareModelA = 'model-a';
      d.compareModelB = '';
      const fetchSpy = vi.spyOn(globalThis, 'fetch');

      await d.loadEvalCompare();

      expect(fetchSpy).not.toHaveBeenCalled();
      expect(d.evalCompare).toBeNull();
      expect(d.evalCompareError).toBeTruthy();
    });
  });

  describe('startConcurrentStress (Adım 4)', () => {
    it('eşzamanlılık sonuçlarını yükler', async () => {
      d.benchmarkModel = 'qwen3:8b';
      d.benchmarkProvider = 'lmstudio';
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => ({
          ok: true,
          results: [{ concurrency: 1, latency_p50_ms: 100, latency_p95_ms: 110, latency_p99_ms: 120, ttft_p50_ms: 80, throughput_tps: 40, queue_effect_pct: 0 }],
        }),
      });

      await d.startConcurrentStress();

      expect(d.concurrentResults).toHaveLength(1);
      expect(d.concurrentResults[0].concurrency).toBe(1);
      expect(d.concurrentLoading).toBe(false);
    });

    it('hata durumunda concurrentError set eder', async () => {
      d.benchmarkModel = 'qwen3:8b';
      d.benchmarkProvider = 'lmstudio';
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => ({ ok: false, error: 'sunucu yok' }),
      });

      await d.startConcurrentStress();

      expect(d.concurrentResults).toBeNull();
      expect(d.concurrentError).toContain('sunucu yok');
    });
  });

  describe('red-team (Adım 6)', () => {
    it('planı yükler ve ilk görevi seçer', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => ({
          ok: true,
          tasks: [
            { id: 'rt_ignore', category: 'talimat_yok_sayma', prompt: 'p1' },
            { id: 'rt_dan', category: 'jailbreak', prompt: 'p2' },
          ],
        }),
      });

      await d.loadRedteamPlan();

      expect(d.redteamTasks).toHaveLength(2);
      expect(d.redteamTaskId).toBe('rt_ignore');
      expect(d.redteamLoading).toBe(false);
    });

    it('grade sonucunu taşımalı', async () => {
      d.redteamTaskId = 'rt_dan';
      d.redteamResponse = 'Sorry, I cannot help.';
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => ({ ok: true, task_id: 'rt_dan', pass: true, reason: 'reddetti' }),
      });

      await d.gradeRedteam();

      expect(d.redteamResult.pass).toBe(true);
      expect(d.redteamError).toBe('');
    });
  });
});
