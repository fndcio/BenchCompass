/* BenchCompass — Grafik çizim metodları (ES modülü)
 * web/app.js'ten ayrıldı (2026-11-05, Özellik 4 modülerleştirme).
 * `this` Alpine bileşenine bağlıdır; dashboard() içine DASHBOARD_MIXINS ile dahil edilir.
 */

import { prepareExtraChartData } from './eval-helpers.js';

export const chartMethods = {
    // --- Charts (Sprint 4'te mevcut davranış korundu, tema-aware renkler eklendi) ---
    renderCharts() {
      // Sadece charts görünür olduğunda çağrılır (x-effect)
      if (this.view !== 'charts') return;
      // Chart.js instances'ı yok et
      Object.values(this.charts).forEach(c => { try { c.destroy(); } catch (err) { console.debug(err); } });
      this.charts = {};

      const labels = this.history.map(r => r.name || ('run-' + r.id));
      const modelFilter = this.chartModel;
      const matchesModel = (m) => !modelFilter || m.name === modelFilter;
      const topFits = this.history.map(r =>
        Math.max(...(r.models || []).filter(matchesModel).map(m => m.fitScore || 0), 0)
      );

      const byUse = {};
      this.history.forEach(r => { if (!byUse[r.use_case]) byUse[r.use_case] = []; });
      Object.keys(byUse).forEach(k => {
        byUse[k] = this.history.filter(r => r.use_case === k).map(r => ({
          x: r.name || ('run-' + r.id),
          y: Math.max(...(r.models || []).filter(matchesModel).map(m => m.fitScore || 0), 0),
        }));
      });

      const app = {};
      const avg = {};
      this.history.forEach(r => (r.models || []).filter(matchesModel).forEach(m => {
        app[m.name] = (app[m.name] || 0) + 1;
        avg[m.name] = avg[m.name] || [];
        avg[m.name].push(m.fitScore || 0);
      }));
      const topApp = Object.entries(app).sort((a, b) => b[1] - a[1]).slice(0, 8);
      const topAvg = Object.entries(avg).map(([k, v]) => [k, v.reduce((a, b) => a + b, 0) / v.length]).sort((a, b) => b[1] - a[1]).slice(0, 6);

      // Tema-aware renkler (CSS token'larından oku)
      const css = getComputedStyle(document.documentElement);
      const C = {
        primary: css.getPropertyValue('--primary').trim() || '#4f98a3',
        success: css.getPropertyValue('--success').trim() || '#6daa45',
        warn: css.getPropertyValue('--warn').trim() || '#e8af34',
        error: css.getPropertyValue('--error').trim() || '#d163a7',
      };

      const el = id => document.getElementById(id);
      if (!el('fitTrendChart')) return;

      this.charts.fit = new Chart(el('fitTrendChart'), {
        type: 'line',
        data: { labels, datasets: [{ label: 'Top fit', data: topFits, borderColor: C.primary, backgroundColor: C.primary + '2e', fill: true, tension: .25 }] },
        options: { responsive: true, maintainAspectRatio: false },
      });
      this.charts.use = new Chart(el('useCaseTrendChart'), {
        type: 'line',
        data: {
          labels,
          datasets: Object.entries(byUse)
            .filter(([name]) => this.chartUseCase === 'all' || name === this.chartUseCase)
            .map(([name, vals], i) => ({ label: name, data: labels.map(l => { const f = vals.find(v => v.x === l); return f ? f.y : null; }), borderColor: [C.success, C.warn, C.error, C.primary][i % 4], spanGaps: true, tension: .25 })),
        },
        options: { responsive: true, maintainAspectRatio: false },
      });
      this.charts.app = new Chart(el('appearanceChart'), {
        type: 'bar',
        data: { labels: topApp.map(x => x[0]), datasets: [{ label: 'Appearances', data: topApp.map(x => x[1]), backgroundColor: C.warn }] },
        options: { responsive: true, maintainAspectRatio: false, indexAxis: 'y' },
      });
      this.charts.avg = new Chart(el('avgFitChart'), {
        type: 'bar',
        data: { labels: topAvg.map(x => x[0]), datasets: [{ label: 'Avg fit', data: topAvg.map(x => Number(x[1].toFixed(1))), backgroundColor: C.error }] },
        options: { responsive: true, maintainAspectRatio: false },
      });

      // --- Sprint 5: 3 yeni grafik (Kriter #11) ---
      this._renderCompatTimeChart(C, labels);
      this._renderUseCaseTopChart(C, labels);
      this._renderVramHistChart(C);

      // --- Sprint 15: 5 ekstra grafik (s9 endpoint'i) ---
      this._renderExtraCharts(C);
    },

    /** Sprint 15 — `/api/grafiks/ekstra` verisini çeker, 5 s9 grafiğini çizer.
     *  Veri yoksa/hata olursa empty-state bayrağı set eder (sayfa çökmez — G2). */
    async _renderExtraCharts(C) {
      const el = id => document.getElementById(id);
      const canvases = ['s9RadarChart', 's9ScatterChart', 's9FitPieChart', 's9MoeChart', 's9CapsPieChart'];
      const anyCanvas = canvases.some(id => el(id));
      if (!anyCanvas) return;
      let raw;
      try {
        raw = await this.getJson(this.apiBase + '/api/grafiks/ekstra');
      } catch (e) {
        this.extraChartsEmpty = true;
        this.extraChartsError = 'Grafik verisi alınamadı (backend erişilebilir değil).';
        return;
      }
      const data = prepareExtraChartData(raw);
      this.extraChartsError = '';
      if (!data || !data.hasData) {
        this.extraChartsEmpty = true;
        return;
      }
      this.extraChartsEmpty = false;
      this._drawS9Radar(C, el, data.radar);
      this._drawS9Scatter(C, el, data.scatter);
      this._drawS9FitPie(C, el, data.fitLevel);
      this._drawS9MoeChart(C, el, data.moeTrend);
      this._drawS9CapsPie(C, el, data.caps);
    },

    /** Skor bileşenleri radarı — top 5 modelin fit/quality/speed/context boyutları. */
    _drawS9Radar(C, el, radar) {
      const node = el('s9RadarChart');
      if (!node || !radar.length) return;
      const colors = [C.success, C.warn, '#e8843a', C.error, C.primary];
      const datasets = radar.map((m, i) => ({
        label: m.name,
        data: [m.fit, m.quality, m.speed, m.context],
        borderColor: colors[i % colors.length],
        backgroundColor: colors[i % colors.length] + '2a',
        pointRadius: 2,
        borderWidth: 1.5,
      }));
      this.charts.s9Radar = new Chart(node, {
        type: 'radar',
        data: { labels: ['Fit', 'Quality', 'Speed', 'Context'], datasets },
        options: {
          responsive: true, maintainAspectRatio: false,
          scales: { r: { beginAtZero: true, max: 100, ticks: { stepSize: 25, display: false } } },
          plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, font: { size: 9 } } } },
        },
      });
    },

    /** Parametre x Hız scatter — büyük model gerçekten yavaş mı? */
    _drawS9Scatter(C, el, scatter) {
      const node = el('s9ScatterChart');
      if (!node || !scatter.length) return;
      this.charts.s9Scatter = new Chart(node, {
        type: 'scatter',
        data: {
          datasets: [{
            label: 'Model',
            data: scatter.map(p => ({ x: p.x, y: p.y })),
            backgroundColor: C.primary,
            pointRadius: 5,
          }],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          scales: {
            x: { title: { display: true, text: 'Parametre (B)' } },
            y: { title: { display: true, text: 'Tahmini hız (tok/s)' }, beginAtZero: true },
          },
          plugins: {
            tooltip: {
              callbacks: {
                label: (ctx) => {
                  const name = scatter[ctx.dataIndex]?.name || '';
                  return `${name}  (${ctx.parsed.x}B param, ${ctx.parsed.y} tok/s)`;
                },
              },
            },
          },
        },
      });
    },

    /** fit_level dağılımı — pastayı gösterir. */
    _drawS9FitPie(C, el, fitLevel) {
      const node = el('s9FitPieChart');
      if (!node || !Object.keys(fitLevel).length) return;
      const colors = [C.success, C.warn, '#e8843a', C.error, C.primary];
      const entries = Object.entries(fitLevel);
      this.charts.s9FitPie = new Chart(node, {
        type: 'pie',
        data: {
          labels: entries.map(e => e[0]),
          datasets: [{ data: entries.map(e => e[1]), backgroundColor: entries.map((_, i) => colors[i % colors.length]) }],
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } } },
      });
    },

    /** MoE oranı zaman serisi — yüzde çizgisi. */
    _drawS9MoeChart(C, el, moeTrend) {
      const node = el('s9MoeChart');
      if (!node || !moeTrend.length) return;
      this.charts.s9Moe = new Chart(node, {
        type: 'line',
        data: {
          labels: moeTrend.map(r => r.run),
          datasets: [{
            label: 'MoE oranı (%)',
            data: moeTrend.map(r => r.pct),
            borderColor: C.error,
            backgroundColor: C.error + '2e',
            fill: true,
            tension: .25,
            spanGaps: true,
          }],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          scales: { y: { beginAtZero: true, max: 100, ticks: { callback: v => v + '%' } } },
        },
      });
    },

    /** Capabilities dağılımı — model yeteneklerinin pastası. */
    _drawS9CapsPie(C, el, caps) {
      const node = el('s9CapsPieChart');
      if (!node || !Object.keys(caps).length) return;
      const colors = [C.primary, C.success, C.warn, '#e8843a', C.error];
      const entries = Object.entries(caps);
      this.charts.s9Caps = new Chart(node, {
        type: 'pie',
        data: {
          labels: entries.map(e => e[0]),
          datasets: [{ data: entries.map(e => e[1]), backgroundColor: entries.map((_, i) => colors[i % colors.length]) }],
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } } },
      });
    },

    /** Sprint 5.3.a — Uyumluluk dağılımı zaman serisi (stacked area).
     *  Her snapshot için o anki modellerin tier dağılımını sayar.
     *  Donanım profiliyle canlı hesaplanır (tier DB'ye yazılmıyor). */
    _renderCompatTimeChart(C, labels) {
      const el = id => document.getElementById(id);
      if (!el('compatTimeChart')) return;
      const tiers = ['Tam Uyumlu', 'Uyumlu (Sınırda)', 'Dikkatli Kullan', 'Uygun Değil'];
      const colors = [C.success, C.warn, '#e8843a', C.error];
      // History'yi eskiden yeniye sırala (zaman ekseninin düzgün olması için)
      const ordered = [...this.history].slice().reverse();
      const timeLabels = ordered.map(r => r.name || ('run-' + r.id));
      const datasets = tiers.map((tier, i) => ({
        label: tier,
        data: ordered.map(r => (r.models || []).filter(m => this.tierOf(m).tier === tier).length),
        borderColor: colors[i],
        backgroundColor: colors[i] + '4d',
        fill: true,
        tension: .25,
      }));
      this.charts.compatTime = new Chart(el('compatTimeChart'), {
        type: 'line',
        data: { labels: timeLabels, datasets },
        options: {
          responsive: true, maintainAspectRatio: false,
          scales: {
            y: { stacked: true, beginAtZero: true, ticks: { precision: 0 } },
            x: { stacked: true },
          },
          interaction: { intersect: false, mode: 'index' },
        },
      });
    },

    /** Sprint 5.3.b — Use-case bazlı top model trendi.
     *  Seçili use-case'teki her snapshot'ın en yüksek fit skorlu modelini
     *  zaman içinde çizer. Sprint 15: 'all' = filtre yok, model filtresi destekli. */
    _renderUseCaseTopChart(C, labels) {
      const el = id => document.getElementById(id);
      if (!el('useCaseTopChart')) return;
      const ordered = [...this.history].slice().reverse();
      const timeLabels = ordered.map(r => r.name || ('run-' + r.id));
      const uc = this.chartUseCase;
      const modelFilter = this.chartModel;
      const matchesRun = (m) => {
        if (uc !== 'all' &&
            !(m.useCase || '').toLowerCase().includes(uc) &&
            !(m.use_case || '').toLowerCase().includes(uc) &&
            !(m.name || '').toLowerCase().includes(uc)) return false;
        if (modelFilter && m.name !== modelFilter) return false;
        return true;
      };
      const topFitData = ordered.map(r => {
        const models = (r.models || []).filter(matchesRun);
        return models.length ? Math.max(...models.map(m => m.fitScore || 0)) : null;
      });
      const topModelNames = ordered.map(r => {
        const models = (r.models || []).filter(matchesRun);
        if (!models.length) return '';
        const top = models.slice().sort((a, b) => (b.fitScore || 0) - (a.fitScore || 0))[0];
        return top.name;
      });
      this.charts.useCaseTop = new Chart(el('useCaseTopChart'), {
        type: 'line',
        data: {
          labels: timeLabels,
          datasets: [{
            label: `${uc === 'all' ? 'Tüm kategoriler' : uc} top-1 fit` + (modelFilter ? ' (' + modelFilter + ')' : ''),
            data: topFitData,
            borderColor: C.primary,
            backgroundColor: C.primary + '2e',
            fill: true,
            tension: .25,
            spanGaps: true,
          }],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: {
            tooltip: {
              callbacks: {
                afterLabel: (ctx) => {
                  const idx = ctx.dataIndex;
                  return topModelNames[idx] ? 'Top model: ' + topModelNames[idx] : '';
                },
              },
            },
          },
        },
      });
    },

    /** Sprint 5.3.c — VRAM/RAM ihtiyaç dağılımı (anlık histogram).
     *  Aktif latest model havuzunun tier bazında dağılımını bar chart olarak
     *  gösterir. Tarih bağımsız — o anki donanıma göre. */
    _renderVramHistChart(C) {
      const el = id => document.getElementById(id);
      if (!el('vramHistChart')) return;
      const tiers = ['Tam Uyumlu', 'Uyumlu (Sınırda)', 'Dikkatli Kullan', 'Uygun Değil'];
      const colors = [C.success, C.warn, '#e8843a', C.error];
      const counts = tiers.map(t => this.latest.filter(m => this.tierOf(m).tier === t).length);
      this.charts.vramHist = new Chart(el('vramHistChart'), {
        type: 'bar',
        data: {
          labels: tiers,
          datasets: [{
            label: 'Model sayısı',
            data: counts,
            backgroundColor: colors,
            borderWidth: 0,
          }],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          indexAxis: 'y',
          scales: { x: { beginAtZero: true, ticks: { precision: 0 } } },
        },
      });
    },
};
