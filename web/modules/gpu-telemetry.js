/* BenchCompass — Alpine metod grubu (ES modülü)
 * web/app.js'ten ayrıldı (2026-11-05, Faz 2 modülerleştirme).
 * `this` Alpine bileşenine bağlıdır; dashboard() içine spread edilir.
 */

export const gpuTelemetryMethods = {
    // --- GPU Telemetri (Sprint 44) -------------------------------------------
    async pollGpu() {
      try {
        const d = await this.getJson(this.apiBase + '/api/telemetry/gpu');
        if (d && d.available) {
          this.gpu = d;
          this.gpuHistory.push({
            label: new Date().toLocaleTimeString(),
            usedPct: d.used_pct ?? 0,
            temp: d.temp_c ?? 0,
            power: d.power_w ?? 0,
            util: d.util_pct ?? 0,
          });
          if (this.gpuHistory.length > 100) this.gpuHistory.shift();

          // Telemetri Eşik Uyarıları (Özellik 3) — eşikler backend'den gelir
          // (tek kaynak, Y17/DRY); alan eksikse frontend fallback sabiti kullanılır.
          const alerts = [];
          const vramPct = d.used_pct ?? 0;
          const critPct = d.crit_pct ?? 96;
          const warnPct = d.warn_pct ?? 92;
          const tempCritC = d.temp_crit_c ?? 82;
          const tempWarnC = d.temp_warn_c ?? 75;
          if (vramPct >= critPct || d.level === 'crit') {
            alerts.push({
              type: 'vram',
              level: 'crit',
              message: (typeof this.t === 'function' ? this.t('gpu.alert.vramCrit', { pct: Math.round(vramPct) }) : `VRAM Kritik (%${Math.round(vramPct)})`),
            });
          } else if (vramPct >= warnPct || d.level === 'warn') {
            alerts.push({
              type: 'vram',
              level: 'warn',
              message: (typeof this.t === 'function' ? this.t('gpu.alert.vramWarn', { pct: Math.round(vramPct) }) : `VRAM Yüksek (%${Math.round(vramPct)})`),
            });
          }
          if (d.temp_c != null && d.temp_c >= tempCritC) {
            alerts.push({
              type: 'temp',
              level: 'crit',
              message: (typeof this.t === 'function' ? this.t('gpu.alert.tempCrit', { temp: Math.round(d.temp_c) }) : `Aşırı Sıcaklık (${Math.round(d.temp_c)}°C)`),
            });
          } else if (d.temp_c != null && d.temp_c >= tempWarnC) {
            alerts.push({
              type: 'temp',
              level: 'warn',
              message: (typeof this.t === 'function' ? this.t('gpu.alert.tempWarn', { temp: Math.round(d.temp_c) }) : `Yüksek Sıcaklık (${Math.round(d.temp_c)}°C)`),
            });
          }
          this.telemetryAlerts = alerts;
        } else {
          this.gpu = { available: false };
          this.telemetryAlerts = [];
        }
      } catch (e) {
        console.debug('GPU telemetri alınamadı:', e && e.message);
        this.gpu = { available: false };
        this.telemetryAlerts = [];
      }
    },
    startGpuPolling() {
      this.pollGpu();
      if (this._gpuTimer) clearInterval(this._gpuTimer);
      this._gpuTimer = setInterval(() => {
        if (!document.hidden) this.pollGpu();
      }, 3000);
    },
    gpuLevelColor(level) {
      if (level === 'crit') return '#f85149';
      if (level === 'warn') return '#d29922';
      return '#58a6ff';
    },

    // Sprint 51: NPU cihaz durumu
    async loadNpu() {
      try {
        this.npu = await this.getJson(this.apiBase + '/api/telemetry/npu');
      } catch (e) {
        console.debug('NPU telemetri alınamadı:', e && e.message);
        this.npu = { available: false };
      }
    },

    // Sprint 46: karar matrisi
    async loadMatrix() {
      this.matrixLoading = true;
      this.matrixError = '';
      try {
        this.matrixData = await this.getJson(this.apiBase + '/api/matrix');
      } catch (e) {
        console.debug('Matris alınamadı:', e && e.message);
        this.matrixData = null;
        this.matrixError = e && e.message ? e.message : 'Matris alınamadı';
      }
      this.matrixLoading = false;
    },
    matrixTierColor(cand) {
      const r = computeTier(cand, this.hardware, this.thresholds);
      if (r.tone === 'good') return '#3fb950';
      if (r.tone === 'warn' || r.tone === 'orange') return '#d29922';
      return '#f85149';
    },

    // Sprint 47: görev profili önerisi
    initProfileWeights() {
      // Matris rolleri geldiğinde slider'ları varsayılan 0 ile kur
      if (this.matrixData && this.matrixData.roles) {
        for (const r of this.matrixData.roles) {
          if (!(r.role in this.profileWeights)) this.profileWeights[r.role] = 0;
        }
      }
    },
    async recommendProfile() {
      this.profileLoading = true;
      this.profileResult = null;
      this.profileError = '';
      try {
        const r = await fetch(this.apiBase + '/api/matrix/recommend', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ weights: this.profileWeights }),
        });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        this.profileResult = await r.json();
      } catch (e) {
        console.debug('Profil önerisi alınamadı:', e && e.message);
        this.profileResult = null;
        this.profileError = e && e.message ? e.message : 'Öneri alınamadı';
      }
      this.profileLoading = false;
    },

    // Sprint 45: enerji/maliyet
    async loadEnergyModels() {
      try {
        const d = await this.getJson(this.apiBase + '/api/telemetry/energy');
        this.energyModels = d.models || [];
        if (!this.energyModel && this.energyModels.length) {
          this.energyModel = this.energyModels[0].model;
        }
      } catch (e) {
        console.debug('Enerji model listesi alınamadı:', e && e.message);
        this.energyModels = [];
      }
    },
    async loadEnergyReport() {
      if (!this.energyModel) return;
      this.energyLoading = true;
      this.energyError = '';
      this.energyReport = null;
      try {
        this.energyReport = await this.getJson(
          this.apiBase + '/api/telemetry/energy/' + encodeURIComponent(this.energyModel)
        );
      } catch (e) {
        this.energyError = e && e.message ? e.message : 'Hesap alınamadı';
      }
      this.energyLoading = false;
    },

    // P1-2: tahmin isabeti — /api/calibration/summary özetini çeker
    async loadCalibration() {
      this.calibLoading = true;
      this.calibError = '';
      try {
        this.calib = await this.getJson(this.apiBase + '/api/calibration/summary?limit=30');
      } catch (e) {
        this.calib = null;
        this.calibError = e && e.message ? e.message : 'Kalibrasyon özeti alınamadı';
      }
      this.calibLoading = false;
    },

    // P1-2: kalibrasyon bandı etiket/renk yardımcıları (accuracy_band: green/yellow/red)
    calibBandLabel(band) {
      const harita = {
        green: 'calib.bandGreen',
        yellow: 'calib.bandYellow',
        red: 'calib.bandRed',
      };
      return this.t(harita[band] || 'calib.bandInsufficient');
    },
    calibBandColor(band) {
      return { green: '#3fb950', yellow: '#d29922', red: '#f85149' }[band] || '';
    },
    renderGpuCharts() {
      if (typeof Chart === 'undefined') return;
      // Sprint 52 (K12): grafik destroy/recreate yalnızca sekme açıkken —
      // poll arka planda sürse de (sidebar mini widget) gereksiz render yok.
      if (this.view !== 'telemetri') return;
      const hist = this.gpuHistory;
      const labels = hist.map(p => p.label);
      const accent = (getComputedStyle(document.documentElement)
        .getPropertyValue('--accent') || '').trim() || '#58a6ff';
      const mk = (id, field, color, max) => {
        const el = document.getElementById(id);
        if (!el) return;
        if (this._gpuCharts[id]) this._gpuCharts[id].destroy();
        this._gpuCharts[id] = new Chart(el, {
          type: 'line',
          data: {
            labels,
            datasets: [{
              data: hist.map(p => p[field]),
              borderColor: color,
              backgroundColor: color + '22',
              tension: 0.25,
              pointRadius: 0,
              borderWidth: 2,
              fill: true,
            }],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            plugins: { legend: { display: false } },
            scales: {
              y: { beginAtZero: true, ...(max ? { suggestedMax: max } : {}) },
            },
          },
        });
      };
      mk('gpuChartVram', 'usedPct', accent, 100);
      mk('gpuChartTemp', 'temp', '#d29922', 100);
      mk('gpuChartPower', 'power', '#f85149');
      mk('gpuChartUtil', 'util', '#3fb950', 100);
    },

    async checkStatuses() {
      // Dashboard API durumu
      try {
        const r = await fetch(this.apiBase + '/health');
        this.statusDashboard = r.ok;
      } catch { this.statusDashboard = false; }

      // Collector API durumu
      try {
        const r = await fetch(this.collectorBase + '/health');
        this.statusCollector = r.ok;
      } catch { this.statusCollector = false; }

      // Ollama durumu (CORS engeline takılmamak için backend proxy üzerinden kontrol edilir)
      try {
        const r = await fetch(this.apiBase + '/api/ollama/status');
        const data = await r.json();
        this.statusOllama = (r.ok && data.ok === true && data.status === 'online');
      } catch {
        // Fallback: doğrudan dene
        try {
          const r2 = await fetch('http://localhost:11434/api/tags');
          this.statusOllama = r2.ok;
        } catch {
          this.statusOllama = false;
        }
      }
    },

    toggleAutoRefresh() {
      this.autoRefresh = !this.autoRefresh;
      if (this.autoRefresh) {
        this.autoRefreshTimer = setInterval(() => {
          this.refreshFromDb();
          this.collectorStatus();
        }, 30000); // 30 saniye
        this.toast(window.t ? window.t('toast.autoRefresh') : 'Oto-Yenileme', window.t ? window.t('toast.autoRefreshOn') : 'Dashboard 30 saniyede bir yenilenecek.', 'info', 3000);
      } else {
        if (this.autoRefreshTimer) {
          clearInterval(this.autoRefreshTimer);
          this.autoRefreshTimer = null;
        }
        this.toast(window.t ? window.t('toast.autoRefresh') : 'Oto-Yenileme', window.t ? window.t('toast.autoRefreshOff') : 'Oto-yenileme durduruldu.', 'info', 3000);
      }
    },

    get statusIcon() {
      const on = '<span style="color:var(--success)">●</span>';
      const off = '<span style="color:var(--muted)">○</span>';
      const unk = '<span style="color:var(--muted)">○</span>';
      return {
        dashboard: this.statusDashboard === true ? on : this.statusDashboard === false ? off : unk,
        collector: this.statusCollector === true ? on : this.statusCollector === false ? off : unk,
        ollama: this.statusOllama === true ? on : this.statusOllama === false ? off : unk,
      };
    },
};
