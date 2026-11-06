import { describe, expect, it, vi, beforeEach } from 'vitest';
import '../../web/app.js';

describe('History toplu/seçerek silme (Sprint 17)', () => {
  let d;

  beforeEach(() => {
    d = dashboard();
    d.history = [
      { id: 1, name: 'run-a', created_at: '2026-08-01', use_case: 'coding', models: [{ fitScore: 90 }] },
      { id: 2, name: 'run-b', created_at: '2026-08-02', use_case: 'chat', models: [{ fitScore: 85 }] },
      { id: 3, name: 'run-c', created_at: '2026-08-03', use_case: 'coding', models: [{ fitScore: 80 }] },
    ];
    d.selectedHistoryIds = [];
    d.historyDeleteMsg = '';
  });

  describe('toggleHistorySelect', () => {
    it('seçilmemiş id seçilir', () => {
      d.toggleHistorySelect(2);
      expect(d.selectedHistoryIds).toEqual([2]);
    });

    it('seçili id tekrar tıklanınca çıkar', () => {
      d.selectedHistoryIds = [1, 2];
      d.toggleHistorySelect(2);
      expect(d.selectedHistoryIds).toEqual([1]);
    });

    it('seçim sonrası delete mesajını temizler', () => {
      d.historyDeleteMsg = 'eski mesaj';
      d.toggleHistorySelect(1);
      expect(d.historyDeleteMsg).toBe('');
    });
  });

  describe('toggleSelectAllHistory', () => {
    it('hiç seçili yokken tümü seçilir', () => {
      d.toggleSelectAllHistory();
      expect(d.selectedHistoryIds).toEqual([1, 2, 3]);
    });

    it('tümü seçiliyken tümü bırakılır', () => {
      d.selectedHistoryIds = [1, 2, 3];
      d.toggleSelectAllHistory();
      expect(d.selectedHistoryIds).toEqual([]);
    });
  });

  describe('allHistorySelected getter', () => {
    it('tümü seçiliyken true', () => {
      d.selectedHistoryIds = [1, 2, 3];
      expect(d.allHistorySelected).toBe(true);
    });

    it('kısmi seçimde false', () => {
      d.selectedHistoryIds = [1];
      expect(d.allHistorySelected).toBe(false);
    });

    it('boş history değilken false', () => {
      d.history = [];
      expect(d.allHistorySelected).toBe(false);
    });
  });

  describe('deleteSelectedHistory', () => {
    it('seçim yoksa istek atmaz', async () => {
      const fetchSpy = vi.spyOn(globalThis, 'fetch');
      const confirmSpy = vi.spyOn(globalThis, 'confirm');
      await d.deleteSelectedHistory();
      expect(fetchSpy).not.toHaveBeenCalled();
      expect(confirmSpy).not.toHaveBeenCalled();
    });

    it('onaylanırsa DELETE isteği atar ve refresh çağrılır', async () => {
      d.selectedHistoryIds = [1, 3];
      d.apiBase = 'http://localhost:8788';
      vi.spyOn(globalThis, 'confirm').mockReturnValue(true);
      const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => ({ ok: true, deleted: 2 }),
      });
      const refreshSpy = vi.spyOn(d, 'refreshFromDb').mockResolvedValue(undefined);
      const toastSpy = vi.spyOn(d, 'toast').mockImplementation(() => {});

      await d.deleteSelectedHistory();

      expect(fetchSpy).toHaveBeenCalledWith(
        'http://localhost:8788/api/dashboard/history',
        expect.objectContaining({ method: 'DELETE' }),
      );
      const body = JSON.parse(fetchSpy.mock.calls[0][1].body);
      expect(body.run_ids).toEqual([1, 3]);
      expect(refreshSpy).toHaveBeenCalled();
      expect(d.selectedHistoryIds).toEqual([]);
      expect(d.historyDeleteMsg).toBe('2 run silindi.');
      expect(toastSpy).not.toHaveBeenCalled();
    });

    it('onay reddedilirse istek atmaz', async () => {
      d.selectedHistoryIds = [1];
      vi.spyOn(globalThis, 'confirm').mockReturnValue(false);
      const fetchSpy = vi.spyOn(globalThis, 'fetch');
      await d.deleteSelectedHistory();
      expect(fetchSpy).not.toHaveBeenCalled();
    });
  });

  describe('deleteAllHistory', () => {
    it('onaylanırsa all=true DELETE isteği atar', async () => {
      d.apiBase = 'http://localhost:8788';
      vi.spyOn(globalThis, 'confirm').mockReturnValue(true);
      const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => ({ ok: true, deleted: 3 }),
      });
      const refreshSpy = vi.spyOn(d, 'refreshFromDb').mockResolvedValue(undefined);

      await d.deleteAllHistory();

      expect(fetchSpy).toHaveBeenCalledWith(
        'http://localhost:8788/api/dashboard/history',
        expect.objectContaining({ method: 'DELETE' }),
      );
      const body = JSON.parse(fetchSpy.mock.calls[0][1].body);
      expect(body).toEqual({ all: true });
      expect(refreshSpy).toHaveBeenCalled();
      expect(d.historyDeleteMsg).toBe('3 run silindi (tümü).');
    });

    it('history boşken istek atmaz', async () => {
      d.history = [];
      const fetchSpy = vi.spyOn(globalThis, 'fetch');
      await d.deleteAllHistory();
      expect(fetchSpy).not.toHaveBeenCalled();
    });
  });
});
