import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import '../../web/app.js';

describe('Mağaza filtreleri (Sprint 25 G2/G3)', () => {
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

  describe('searchStore — filtre iletimi', () => {
    it('filtreler set edilmişse URL param olarak backend\'e iletilir', async () => {
      d.storeProvider = 'ollama';
      d.storeUseCase = 'coding';
      d.storeMoe = true;
      d.storeMinCtx = 32768;
      const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
        expect(String(url)).toContain('/api/catalog/search?');
        expect(String(url)).toContain('provider=ollama');
        expect(String(url)).toContain('use_case=coding');
        expect(String(url)).toContain('is_moe=true');
        expect(String(url)).toContain('min_ctx=32768');
        return { ok: true, json: async () => ({ models: [{ name: 'Qwen/Qwen3-7B' }], total: 1 }) };
      });

      await d.searchStore();

      expect(fetchSpy).toHaveBeenCalledTimes(1);
      expect(d.storeSource).toBe('local-catalog');
    });

    it('filtreler boşsa sadece q + limit gönderilir (mevcut davranış korunur)', async () => {
      d.storeProvider = '';
      d.storeUseCase = '';
      d.storeMoe = false;
      d.storeMinCtx = 0;
      const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
        const s = String(url);
        expect(s).toContain('/api/catalog/search?');
        expect(s).toContain('q=qwen');
        expect(s).not.toContain('provider=');
        expect(s).not.toContain('use_case=');
        expect(s).not.toContain('is_moe=');
        expect(s).not.toContain('min_ctx=');
        return { ok: true, json: async () => ({ models: [{ name: 'X' }], total: 1 }) };
      });

      await d.searchStore();

      expect(fetchSpy).toHaveBeenCalledTimes(1);
    });

    it('MoE checkbox kapalıyken is_moe gönderilmez', async () => {
      d.storeProvider = 'qwen';
      d.storeMoe = false;
      const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
        expect(String(url)).toContain('provider=qwen');
        expect(String(url)).not.toContain('is_moe=');
        return { ok: true, json: async () => ({ models: [{ name: 'X' }], total: 1 }) };
      });

      await d.searchStore();

      expect(fetchSpy).toHaveBeenCalledTimes(1);
    });
  });

  describe('loadStoreProviders — filtre seçenekleri', () => {
    it('provider listesini /api/catalog üzerinden yükler', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => ({ providers: ['ollama', 'qwen', 'lmstudio'] }),
      });

      await d.loadStoreProviders();

      expect(d.storeProviders).toEqual(['ollama', 'qwen', 'lmstudio']);
    });

    it('hata durumunda boş liste bırakır (çökmez)', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: false,
        json: async () => ({}),
      });

      await d.loadStoreProviders();

      expect(Array.isArray(d.storeProviders)).toBe(true);
    });
  });
});
