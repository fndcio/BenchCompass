// tests/frontend/arena.test.js — P1-3 Çift-Kör Arena ve Elo Arayüz Testleri
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import '../../web/app.js';

describe('Local Model Arena & Çift-Kör Oylama (P1-3)', () => {
  let d;

  beforeEach(() => {
    d = dashboard();
    d.apiBase = 'http://localhost:8788';
    d.arenaModelA = 'qwen3.5:4b';
    d.arenaModelB = 'gemma4:12b';
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('runArenaDuel blind=true bayrağını backend payloadına ekler', async () => {
    d.arenaBlind = true;
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({
        status: 'OK',
        duel_id: 42,
        blind: true,
        results: {
          model_a: { model: 'Model A', tok_per_sec: 40.0 },
          model_b: { model: 'Model B', tok_per_sec: 35.0 },
        },
      }),
    });

    await d.runArenaDuel();

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/api/arena/duel'),
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"blind":true'),
      })
    );
    expect(d.arenaResult.duel_id).toBe(42);
    expect(d.arenaResult.blind).toBe(true);
    expect(d.arenaRunning).toBe(false);
  });

  it('voteArena oy gönderir, arenaVoteResult set eder ve liderlik tablosunu günceller', async () => {
    d.arenaResult = { duel_id: 42, blind: true };
    const leaderboardSpy = vi.spyOn(d, 'loadArenaLeaderboard').mockResolvedValue();

    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({
        status: 'OK',
        data: {
          // Gerçek backend sözleşmesi: api/arena_elo.py record_duel_vote çıktısı
          // (elo_changes anahtarları MODEL ADLARI, alanlar old_elo/new_elo/delta)
          duel_id: 42,
          winner: 'qwen3.5:4b',
          revealed: { model_a: 'qwen3.5:4b', model_b: 'gemma4:12b' },
          elo_changes: {
            'qwen3.5:4b': { old_elo: 1200.0, new_elo: 1216.0, delta: 16.0 },
            'gemma4:12b': { old_elo: 1200.0, new_elo: 1184.0, delta: -16.0 },
          },
        },
      }),
    });

    await d.voteArena('a');

    expect(d.arenaVoteResult).toBeTruthy();
    expect(d.arenaVoteResult.revealed.model_a).toBe('qwen3.5:4b');
    // UI'ın okuduğu gerçek anahtarlar: elo_changes[<model_adı>].old_elo/new_elo/delta
    expect(d.arenaVoteResult.elo_changes['qwen3.5:4b'].old_elo).toBe(1200.0);
    expect(d.arenaVoteResult.elo_changes['qwen3.5:4b'].new_elo).toBe(1216.0);
    expect(d.arenaVoteResult.elo_changes['qwen3.5:4b'].delta).toBe(16.0);
    expect(d.arenaVoteResult.elo_changes['gemma4:12b'].delta).toBe(-16.0);
    expect(leaderboardSpy).toHaveBeenCalled();
  });

  it('loadArenaLeaderboard /api/arena/leaderboard verisini state e yazar', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({
        status: 'OK',
        count: 2,
        leaderboard: [
          // Gerçek backend sözleşmesi: api/arena_elo.py get_arena_leaderboard çıktısı
          // (total_matches / win_rate_pct — UI bu alanları okur)
          { model: 'qwen3.5:4b', elo: 1232.0, total_matches: 3, wins: 2, losses: 0, draws: 1, win_rate_pct: 66.7 },
          { model: 'gemma4:12b', elo: 1168.0, total_matches: 3, wins: 0, losses: 2, draws: 1, win_rate_pct: 0.0 },
        ],
      }),
    });

    await d.loadArenaLeaderboard();

    expect(d.arenaLeaderboard).toHaveLength(2);
    expect(d.arenaLeaderboard[0].model).toBe('qwen3.5:4b');
    expect(d.arenaLeaderboard[0].elo).toBe(1232.0);
    // UI'ın tabloda okuduğu gerçek alanlar (index.html MAÇ / KAZANMA ORANI kolonları)
    expect(d.arenaLeaderboard[0].total_matches).toBe(3);
    expect(d.arenaLeaderboard[0].win_rate_pct).toBe(66.7);
    expect(d.arenaLeaderboardLoading).toBe(false);
  });

  it('loadArenaLeaderboard hatada sessiz kalmaz — boş liste + hata mesajı', async () => {
    d.arenaLeaderboard = [{ model: 'eski', elo: 1200 }];
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({ ok: false, status: 503 });

    await d.loadArenaLeaderboard();

    expect(d.arenaLeaderboard).toEqual([]);
    expect(d.arenaLeaderboardError).toContain('503');
    expect(d.arenaLeaderboardLoading).toBe(false);
  });

  it('generateArenaShareCard arenaResult olmadan işlem yapmaz', () => {
    d.arenaResult = null;
    d.generateArenaShareCard();
    expect(d.arenaShareModalOpen).toBe(false);
    expect(d.arenaShareImage).toBe('');
  });

  it('generateArenaShareCard arenaResult olduğunda kartı üretir ve modalı açar', () => {
    const mockCtx = {
      createLinearGradient: () => ({ addColorStop: vi.fn() }),
      fillRect: vi.fn(),
      strokeRect: vi.fn(),
      beginPath: vi.fn(),
      roundRect: vi.fn(),
      rect: vi.fn(),
      fill: vi.fn(),
      stroke: vi.fn(),
      fillText: vi.fn(),
      measureText: () => ({ width: 50 }),
    };
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mockCtx);
    vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/png;base64,mockpng');

    d.arenaResult = {
      prompt: 'Türkiye nin başkenti neresidir?',
      results: {
        model_a: { model: 'qwen3.5:4b', tok_per_sec: 42.5, ttft_ms: 120, total_tokens: 65 },
        model_b: { model: 'gemma4:12b', tok_per_sec: 28.0, ttft_ms: 210, total_tokens: 80 },
      },
      winner: 'qwen3.5:4b',
      blind: false,
    };
    d.generateArenaShareCard();
    expect(d.arenaShareModalOpen).toBe(true);
    expect(d.arenaShareImage).toBe('data:image/png;base64,mockpng');
  });

  it('Arena duel ttft_method alanını korur (T2 şeffaflığı)', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({
        status: 'OK',
        duel_id: 43,
        blind: false,
        results: {
          model_a: { model: 'Model A', tok_per_sec: 40.0, ttft_ms: 120, ttft_method: 'estimated' },
          model_b: { model: 'Model B', tok_per_sec: 35.0, ttft_ms: 210, ttft_method: 'measured' },
        },
      }),
    });

    await d.runArenaDuel();

    expect(fetchSpy).toHaveBeenCalled();
    expect(d.arenaResult.results.model_a.ttft_method).toBe('estimated');
    expect(d.arenaResult.results.model_b.ttft_method).toBe('measured');
  });

  it('downloadArenaShareCard ve copyArenaShareCard güvenli çalışır', async () => {
    d.arenaShareImage = 'data:image/png;base64,mockpng';
    const clickSpy = vi.fn();
    const origCreateElement = document.createElement.bind(document);
    vi.spyOn(document, 'createElement').mockImplementation((tag) => {
      const el = origCreateElement(tag);
      if (tag === 'a') el.click = clickSpy;
      return el;
    });

    d.downloadArenaShareCard();
    expect(clickSpy).toHaveBeenCalledTimes(1);

    // copyArenaShareCard with clipboard
    const writeSpy = vi.fn().mockResolvedValue(undefined);
    globalThis.ClipboardItem = class ClipboardItem {
      constructor(items) {
        this.items = items;
      }
    };
    Object.assign(navigator, {
      clipboard: {
        write: writeSpy,
      },
    });
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      blob: async () => new Blob(['mock'], { type: 'image/png' }),
    });

    await d.copyArenaShareCard();
    expect(d.arenaShareCopied).toBe(true);
  });
});
