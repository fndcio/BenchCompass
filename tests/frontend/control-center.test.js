/**
 * tests/frontend/control-center.test.js
 *
 * Sprint 53: Control Center state, loadControlCenter and search methods tests.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import '../../web/app.js';
import '../../web/i18n.js';

describe('Control Center Frontend Component', () => {
  let app;

  beforeEach(() => {
    app = globalThis.dashboard();
  });

  it('initializes with default Control Center state', () => {
    expect(app.ccStatus).toBeNull();
    expect(app.ccFlags).toEqual({
      flags: [],
      counts: { critical: 0, high: 0, medium: 0, low: 0 },
      total: 0,
    });
    expect(app.ccLoading).toBe(false);
    expect(app.searchModalOpen).toBe(false);
    expect(app.searchQuery).toBe('');
  });

  it('loadControlCenter fetches and sets state correctly', async () => {
    const fakeStatus = { health: 'HEALTHY', version: '0.26.8' };
    const fakeFlags = { flags: [{ title: 'Test Flag', severity: 'HIGH' }], counts: { high: 1 }, total: 1 };
    const fakeVersions = { authoritative_version: '0.26.8' };
    const fakeRecent = { events: [{ description: 'Test Run', time: '2026-08-21' }] };
    const fakeDiag = { os: 'Windows 11', python: '3.12.0' };
    const fakeDocs = { documents: [{ name: 'README.md', path: 'README.md' }] };
    const fakeDb = { size_mb: 5.1 };

    app.getJson = vi.fn().mockImplementation((url) => {
      if (url.includes('/api/cc/status')) return Promise.resolve(fakeStatus);
      if (url.includes('/api/cc/flags')) return Promise.resolve(fakeFlags);
      if (url.includes('/api/cc/versions')) return Promise.resolve(fakeVersions);
      if (url.includes('/api/cc/recent')) return Promise.resolve(fakeRecent);
      if (url.includes('/api/cc/diagnostics')) return Promise.resolve(fakeDiag);
      if (url.includes('/api/cc/docs')) return Promise.resolve(fakeDocs);
      if (url.includes('/api/cc/db-info')) return Promise.resolve(fakeDb);
      if (url.includes('/api/control/launchers')) return Promise.resolve({ launchers: [{ name: 'test.bat', type: 'bat' }] });
      return Promise.reject(new Error('Unknown URL'));
    });

    await app.loadControlCenter();

    expect(app.ccStatus).toEqual(fakeStatus);
    expect(app.ccFlags).toEqual(fakeFlags);
    expect(app.ccVersions).toEqual(fakeVersions);
    expect(app.ccRecent).toEqual(fakeRecent.events);
    expect(app.ccDiagnostics).toEqual(fakeDiag);
    expect(app.ccDocs).toEqual(fakeDocs.documents);
    expect(app.ccDbInfo).toEqual(fakeDb);
    expect(app.ccLoading).toBe(false);
  });

  it('filteredSearchResults filters views, models, and documents', () => {
    app.latest = [
      { name: 'qwen3:8b-instruct', notes: 'fast model' },
      { name: 'llama3:8b', notes: 'general' },
    ];
    app.ccDocs = [
      { name: 'AGENTS.md', path: 'AGENTS.md' },
    ];

    app.searchQuery = 'qwen';
    const res = app.filteredSearchResults;
    expect(res.some((r) => r.type === 'Model' && r.title.includes('qwen3:8b'))).toBe(true);

    app.searchQuery = 'charts';
    const viewRes = app.filteredSearchResults;
    expect(viewRes.some((r) => r.type === 'View' && r.view === 'charts')).toBe(true);

    app.searchQuery = 'arena';
    const arenaRes = app.filteredSearchResults;
    expect(arenaRes.some((r) => r.type === 'View' && r.view === 'arena')).toBe(true);

    app.searchQuery = 'denetim';
    const auditRes = app.filteredSearchResults;
    expect(auditRes.some((r) => r.type === 'View' && r.view === 'denetim')).toBe(true);

    app.searchQuery = 'agents';
    const docRes = app.filteredSearchResults;
    expect(docRes.some((r) => r.type === 'Doc' && r.title === 'AGENTS.md')).toBe(true);
  });

  it('selectSearchResult updates view and resets search state', () => {
    app.searchModalOpen = true;
    app.searchQuery = 'overview';
    app.loadControlCenter = vi.fn();

    app.selectSearchResult({ view: 'control-center' });

    expect(app.view).toBe('control-center');
    expect(app.searchModalOpen).toBe(false);
    expect(app.searchQuery).toBe('');
    expect(app.loadControlCenter).toHaveBeenCalled();
  });

  it('loadAsrStatus fetches ASR status and populates state', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
      if (url.includes('/api/asr/status')) {
        return {
          ok: true,
          json: async () => ({
            ok: true,
            runtime_available: false,
            runtime_engine: 'none',
            missing_prerequisites: ['ASR motoru eksik'],
            detected_models: [],
          }),
        };
      }
      return { ok: false, status: 404 };
    });

    await app.loadAsrStatus();

    expect(app.asrStatus).toBeTruthy();
    expect(app.asrStatus.runtime_available).toBe(false);
    expect(app.asrStatus.missing_prerequisites).toContain('ASR motoru eksik');
    expect(app.asrLoading).toBe(false);
  });
});

describe('Arena Share Card (Özellik 1 — denetim kapanışı)', () => {
  let app;

  // jsdom'da canvas 2d context yoktur: çağrıları kaydeden sahte ctx kur.
  const stubCanvas = () => {
    const fills = [];
    const gradStops = [];
    const ctx = {
      fillStyle: null,
      strokeStyle: null,
      lineWidth: 1,
      font: '',
      createLinearGradient: () => ({ addColorStop: (o, c) => gradStops.push([o, c]) }),
      fillRect() {},
      strokeRect() {},
      beginPath() {},
      roundRect() {},
      rect() {},
      fill() {},
      stroke() {},
      fillText: (text) => fills.push(String(text)),
      measureText: () => ({ width: 10 }),
    };
    const origCreate = document.createElement.bind(document);
    vi.spyOn(document, 'createElement').mockImplementation((tag) => {
      if (String(tag).toLowerCase() === 'canvas') {
        return { width: 0, height: 0, getContext: () => ctx, toDataURL: () => 'data:image/png;base64,TESTCARD' };
      }
      return origCreate(tag);
    });
    return { fills, gradStops };
  };

  const loadArenaData = () => {
    app.arenaResult = {
      duel_id: 'd1',
      winner: 'model-a',
      blind: false,
      results: {
        model_a: { model: 'model-a', tok_per_sec: 42.5, ttft_ms: 120, total_tokens: 99 },
        model_b: { model: 'model-b', tok_per_sec: 30.1, ttft_ms: 200, total_tokens: 90 },
      },
    };
    app.arenaVoteResult = {
      winner: 'model-a',
      revealed: { model_a: 'model-a', model_b: 'model-b' },
      elo_changes: {
        'model-a': { old_elo: 1500, new_elo: 1512.4, delta: 12.4 },
        'model-b': { old_elo: 1500, new_elo: 1487.6, delta: -12.4 },
      },
    };
    app.arenaLeaderboard = [
      { model: 'model-a', elo: 1512.4, total_matches: 8 },
      { model: 'model-b', elo: 1487.6, total_matches: 8 },
    ];
    app.hardware = { device_name: 'RTX 5070 Ti', vram_gb: 12 };
  };

  beforeEach(() => {
    app = globalThis.dashboard();
    globalThis.setLang('tr');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('kartta gerçek Elo puanı ve maç sayısı çizilir (oylama sonrası)', () => {
    const { fills } = stubCanvas();
    loadArenaData();

    app.generateArenaShareCard();

    expect(app.arenaShareModalOpen).toBe(true);
    expect(fills.some((t) => t.includes('ELO: 1512') && t.includes('Maç: 8'))).toBe(true);
    expect(fills.some((t) => t.includes('ELO: 1488') && t.includes('Maç: 8'))).toBe(true);
    // Alt bantta Elo değişimi de korunur
    expect(fills.some((t) => t.includes('ELO Değişimi') && t.includes('+12.4'))).toBe(true);
  });

  it('kart metinleri dil kataloğundan gelir (EN)', () => {
    const { fills } = stubCanvas();
    loadArenaData();
    globalThis.setLang('en');

    app.generateArenaShareCard();

    expect(fills.some((t) => t.includes('BENCHCOMPASS ARENA DUEL'))).toBe(true);
    expect(fills.some((t) => t.includes('Matches: 8'))).toBe(true);
    expect(fills.some((t) => t.includes('Hardware:'))).toBe(true);
  });

  it('filigran sürümü /api/cc/status kaynağından, fallback rc sabitidir', () => {
    const { fills } = stubCanvas();
    loadArenaData();

    app.generateArenaShareCard();
    expect(fills.some((t) => t.includes('v0.28.0-rc.2'))).toBe(true);

    app.ccStatus = { version: '9.9.9-test' };
    const second = stubCanvas();
    app.generateArenaShareCard();
    expect(second.fills.some((t) => t.includes('v9.9.9-test'))).toBe(true);
  });

  it('kart renkleri aktif temanın CSS değişkenlerinden okunur (light)', () => {
    const { gradStops, fills } = stubCanvas();
    loadArenaData();
    vi.stubGlobal('getComputedStyle', () => ({
      getPropertyValue: (name) => ({
        '--bg': '#f2f1ee',
        '--surface-2': '#f7f6f2',
        '--text': '#1c1c1a',
      })[name] || '',
    }));

    app.generateArenaShareCard();

    expect(gradStops[0]).toEqual([0, '#f2f1ee']);
    expect(gradStops[1]).toEqual([1, '#f7f6f2']);
    expect(fills.some((t) => t.includes('BENCHCOMPASS ARENA'))).toBe(true);
  });

  it('revealed eksik arenaVoteResult hata fırlatmaz (guard)', () => {
    const { fills } = stubCanvas();
    app.arenaResult = {
      results: {
        model_a: { model: 'model-a', tok_per_sec: 1, ttft_ms: 1, total_tokens: 1 },
        model_b: { model: 'model-b', tok_per_sec: 1, ttft_ms: 1, total_tokens: 1 },
      },
    };
    app.arenaVoteResult = { elo_changes: {} };

    expect(() => app.generateArenaShareCard()).not.toThrow();
    expect(fills.some((t) => t.includes('model-a'))).toBe(true);
    expect(app.arenaShareModalOpen).toBe(true);
  });
});

describe('Ollama Pull Kuyruğu (Özellik 2 — denetim kapanışı)', () => {
  let app;

  beforeEach(() => {
    vi.useFakeTimers();
    app = globalThis.dashboard();
    globalThis.setLang('tr');
    app.toast = vi.fn();
    app.loadOllamaModels = vi.fn();
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  const mockFetch = (impl) => vi.spyOn(globalThis, 'fetch').mockImplementation(impl);

  it('pull kaydı açılır; polling tamamlanınca interval temizlenir ve kayıt düşer', async () => {
    const states = [{ status: 'running', progress: 42 }, { status: 'completed', progress: 100 }];
    let poll = 0;
    mockFetch(async (url) => {
      if (url.includes('/api/ollama/pull')) {
        return { ok: true, json: async () => ({ ok: true, task_uuid: 'task-ok', model: 'qwen2.5:0.5b' }) };
      }
      if (url.includes('/api/tasks/task-ok')) {
        const s = states[Math.min(poll, states.length - 1)];
        poll += 1;
        return { ok: true, json: async () => ({ status: s.status, progress: s.progress, detail: 'pulling' }) };
      }
      return { ok: false, status: 404 };
    });

    app.pullModelInput = 'qwen2.5:0.5b';
    await app.pullOllamaModel();

    // Başlatma: kuyruk kaydı eklendi (eski 'adds item' kapsamı)
    expect(app.activeDownloads.length).toBe(1);
    expect(app.activeDownloads[0].model).toBe('qwen2.5:0.5b');
    expect(app.activeDownloads[0].task_uuid).toBe('task-ok');
    expect(app.activeDownloads[0].status).toBe('running');
    expect(app.pullModelInput).toBe('');

    await vi.advanceTimersByTimeAsync(1000); // ilk poll: running %42
    expect(app.activeDownloads[0].progress).toBe(42);
    expect(vi.getTimerCount()).toBe(1); // interval hâlâ açık (temizlik bekleniyor)

    await vi.advanceTimersByTimeAsync(1000); // ikinci poll: completed
    expect(app.activeDownloads[0].status).toBe('completed');
    expect(app.activeDownloads[0].progress).toBe(100);
    expect(app.toast).toHaveBeenCalledWith(expect.stringContaining('başarıyla'), 'qwen2.5:0.5b', 'success', 4000);
    expect(app.loadOllamaModels).toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(4000); // listeden düşürme
    expect(app.activeDownloads.length).toBe(0);
    expect(vi.getTimerCount()).toBe(0); // sızıntı yok
  });

  it('ardışık poll hatası interval temizler ve kaydı failed yapar (lostTask)', async () => {
    mockFetch(async (url) => {
      if (url.includes('/api/ollama/pull')) {
        return { ok: true, json: async () => ({ ok: true, task_uuid: 'task-x' }) };
      }
      return { ok: false, status: 404 }; // /api/tasks/<uuid> hep 404
    });

    await app.pullOllamaModel('llama3.2:1b');
    await vi.advanceTimersByTimeAsync(6000); // >= 5 ardışık hata

    expect(app.activeDownloads[0].status).toBe('failed');
    expect(app.activeDownloads[0].detail).toContain('görevi bulunamadı');
    expect(app.toast).toHaveBeenCalledWith(expect.stringContaining('görevi bulunamadı'), 'llama3.2:1b', 'error', 5000);
    expect(vi.getTimerCount()).toBe(0); // sonsuz polling yok
  });

  it('aynı model kuyrukta aktifken mükerrer başlatılmaz', async () => {
    const fetchSpy = mockFetch(async () => ({ ok: false, status: 404 }));
    app.activeDownloads = [{ task_uuid: 't1', model: 'qwen2.5:0.5b', progress: 10, status: 'running', detail: 'x' }];

    await app.pullOllamaModel('qwen2.5:0.5b');

    expect(app.activeDownloads.length).toBe(1);
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(app.toast).toHaveBeenCalledWith(expect.stringContaining('zaten'), 'qwen2.5:0.5b', 'error', 4000);
  });

  it('HuggingFace repo kimliği reddedilir (Ollama etiketi beklenir)', async () => {
    const fetchSpy = mockFetch(async () => ({ ok: false, status: 404 }));

    await app.pullOllamaModel('Qwen/Qwen2.5-7B');

    expect(app.activeDownloads.length).toBe(0);
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(app.toast).toHaveBeenCalledWith(expect.stringContaining('HuggingFace'), 'Qwen/Qwen2.5-7B', 'error', 6000);
  });

  it('retryOllamaDownload failed kaydı düşürüp yeniden başlatır', async () => {
    const fetchSpy = mockFetch(async (url) => {
      if (url.includes('/api/ollama/pull')) {
        return { ok: true, json: async () => ({ ok: true, task_uuid: 'task-retry' }) };
      }
      return { ok: false, status: 404 };
    });
    app.activeDownloads = [{ task_uuid: 't-old', model: 'gemma2:2b', progress: 0, status: 'failed', detail: 'eski hata' }];

    await app.retryOllamaDownload(app.activeDownloads[0]);

    expect(app.activeDownloads.length).toBe(1);
    expect(app.activeDownloads[0].model).toBe('gemma2:2b');
    expect(app.activeDownloads[0].status).toBe('running');
    expect(app.activeDownloads[0].task_uuid).toBe('task-retry');
    expect(fetchSpy).toHaveBeenCalled();
  });

  it('removeOllamaDownload kaydı kuyruktan kaldırır', () => {
    app.activeDownloads = [
      { task_uuid: 't1', model: 'a:1', status: 'failed' },
      { task_uuid: 't2', model: 'b:1', status: 'completed' },
    ];

    app.removeOllamaDownload(app.activeDownloads[0]);

    expect(app.activeDownloads.length).toBe(1);
    expect(app.activeDownloads[0].task_uuid).toBe('t2');
  });
});
