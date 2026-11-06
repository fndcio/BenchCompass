// Sprint 47: Görev profili öneri motoru frontend testleri.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import '../../web/app.js';

const d = () => globalThis.dashboard();

describe('initProfileWeights', () => {
  it('matris rolleri geldiğinde slider değerleri 0 ile kurulur', () => {
    const state = d();
    state.profileWeights = {};
    state.matrixData = { roles: [{ role: 'reasoning' }, { role: 'coding' }] };
    state.initProfileWeights();
    expect(state.profileWeights).toEqual({ reasoning: 0, coding: 0 });
  });

  it('mevcut ağırlıklar ezilmez', () => {
    const state = d();
    state.profileWeights = { reasoning: 80 };
    state.matrixData = { roles: [{ role: 'reasoning' }, { role: 'chat' }] };
    state.initProfileWeights();
    expect(state.profileWeights.reasoning).toBe(80);
    expect(state.profileWeights.chat).toBe(0);
  });
});

describe('recommendProfile', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('POST + ağırlıklar doğru gövdeyle gönderilir', async () => {
    const mock = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({
        roles: ['reasoning'], weights_used: { reasoning: 60 },
        recommendations: [{ name: 'qwen3:8b', weighted_score: 84, required_vram_gb: 6 }],
        model_count: 1,
      }),
    });
    const state = d();
    state.profileWeights = { reasoning: 60, coding: 40 };
    await state.recommendProfile();
    const [url, opts] = mock.mock.calls[0];
    expect(url).toContain('/api/matrix/recommend');
    expect(opts.method).toBe('POST');
    expect(JSON.parse(opts.body)).toEqual({ weights: { reasoning: 60, coding: 40 } });
    expect(state.profileResult.recommendations[0].name).toBe('qwen3:8b');
  });

  it('HTTP hatası → graceful (result null, loading false)', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({ ok: false, status: 500 });
    const state = d();
    state.profileWeights = { reasoning: 50 };
    await state.recommendProfile();
    expect(state.profileResult).toBeNull();
    expect(state.profileLoading).toBe(false);
  });
});
