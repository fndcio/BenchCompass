import { describe, expect, it } from 'vitest';
import '../../web/app.js';

describe('Charts Mixin paritesi (Özellik 4 — denetim kapanışı)', () => {
  it('charts.js mixin metodları dashboard() örneğinde birleşmiş', () => {
    const app = globalThis.dashboard();
    const chartMethods = [
      'renderCharts',
      '_renderExtraCharts',
      '_drawS9Radar',
      '_drawS9Scatter',
      '_drawS9FitPie',
      '_drawS9MoeChart',
      '_drawS9CapsPie',
      '_renderCompatTimeChart',
      '_renderUseCaseTopChart',
      '_renderVramHistChart',
    ];
    for (const m of chartMethods) {
      expect(typeof app[m], `app.${m}`).toBe('function');
    }
  });
});

describe('prepareExtraChartData (Sprint 15 — s9 grafik veri adaptörü)', () => {
  const sampleRaw = {
    score_components_radar: [
      { name: 'Hy3', fit: 92, quality: 85, speed: 40, context: 262144 },
      { name: 'DeepSeek V4 Flash', fit: 89, quality: 80, speed: 38, context: 1048576 },
    ],
    param_speed_scatter: [
      { p: 13, s: 42, n: 'Hy3' },
      { p: 47, s: 20, n: 'Mixtral-8x22B' },
    ],
    fit_level_distribution: { Perfect: 2, Good: 3, Unknown: 1 },
    moe_trend: [
      { run: 'nightly-1', total: 10, moe: 2, pct: 20.0 },
      { run: 'nightly-2', total: 10, moe: 3, pct: 30.0 },
    ],
    capabilities_pie: { 'Tool Use': 3, Vision: 2, Reasoning: 5 },
  };

  it('normalizes radar to first 5 models with 4 score dims', () => {
    const d = prepareExtraChartData(sampleRaw);
    expect(d.radar).toHaveLength(2);
    expect(d.radar[0]).toEqual({ name: 'Hy3', fit: 92, quality: 85, speed: 40, context: 262144 });
  });

  it('maps scatter to {x,y,name} points', () => {
    const d = prepareExtraChartData(sampleRaw);
    expect(d.scatter[0]).toEqual({ x: 13, y: 42, name: 'Hy3' });
    expect(d.scatter[1].name).toBe('Mixtral-8x22B');
  });

  it('keeps fit_level and capabilities as label->count maps', () => {
    const d = prepareExtraChartData(sampleRaw);
    expect(d.fitLevel).toEqual({ Perfect: 2, Good: 3, Unknown: 1 });
    expect(d.caps).toEqual({ 'Tool Use': 3, Vision: 2, Reasoning: 5 });
  });

  it('normalizes moe_trend to run/total/moe/pct', () => {
    const d = prepareExtraChartData(sampleRaw);
    expect(d.moeTrend).toEqual([
      { run: 'nightly-1', total: 10, moe: 2, pct: 20 },
      { run: 'nightly-2', total: 10, moe: 3, pct: 30 },
    ]);
  });

  it('sets hasData=false when all sections empty', () => {
    const d = prepareExtraChartData({});
    expect(d.hasData).toBe(false);
  });

  it('handles missing quality by defaulting to 0', () => {
    const raw = { score_components_radar: [{ name: 'X', fit: 50, speed: 10, context: 8192 }] };
    const d = prepareExtraChartData(raw);
    expect(d.radar[0].quality).toBe(0);
  });

  it('returns null for non-object input', () => {
    expect(prepareExtraChartData(null)).toBeNull();
    expect(prepareExtraChartData('nope')).toBeNull();
  });
});
