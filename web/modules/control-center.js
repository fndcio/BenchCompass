/* BenchCompass — Alpine metod grubu (ES modülü)
 * web/app.js'ten ayrıldı (2026-11-05, Faz 2 modülerleştirme).
 * `this` Alpine bileşenine bağlıdır; dashboard() içine spread edilir.
 */

export const controlCenterMethods = {
    // --- Sprint 53: Control Center Metodları ---
    async loadControlCenter() {
      this.ccLoading = true;
      try {
        const [status, flags, versions, recent, diag, docs, dbInfo, asr] = await Promise.all([
          this.getJson(this.apiBase + '/api/cc/status').catch(() => null),
          this.getJson(this.apiBase + '/api/cc/flags').catch(() => ({ flags: [], counts: {}, total: 0 })),
          this.getJson(this.apiBase + '/api/cc/versions').catch(() => null),
          this.getJson(this.apiBase + '/api/cc/recent?limit=15').catch(() => ({ events: [] })),
          this.getJson(this.apiBase + '/api/cc/diagnostics').catch(() => null),
          this.getJson(this.apiBase + '/api/cc/docs').catch(() => ({ documents: [] })),
          this.getJson(this.apiBase + '/api/cc/db-info').catch(() => null),
          this.getJson(this.apiBase + '/api/asr/status').catch(() => null),
        ]);
        if (status) this.ccStatus = status;
        if (flags) this.ccFlags = flags;
        if (versions) this.ccVersions = versions;
        if (recent && recent.events) this.ccRecent = recent.events;
        if (diag) this.ccDiagnostics = diag;
        if (docs && docs.documents) this.ccDocs = docs.documents;
        if (dbInfo) this.ccDbInfo = dbInfo;
        if (asr) this.asrStatus = asr;
        await this.loadLaunchers();
      } catch (e) {
        console.error('CC load error:', e);
      } finally {
        this.ccLoading = false;
      }
    },

    async loadLaunchers() {
      try {
        const res = await this.getJson(this.apiBase + '/api/control/launchers');
        if (res && res.launchers) this.launchers = res.launchers;
      } catch (e) {
        console.error('Launchers load error:', e);
      }
    },

    async triggerLauncher(name) {
      if (this.launchingScript) return;
      this.launchingScript = name;
      try {
        const res = await fetch(this.apiBase + '/api/control/launch?name=' + encodeURIComponent(name), { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
          alert('🚀 Başlatıldı: ' + name);
        } else {
          alert('⚠️ Hata: ' + (data.detail || 'Bilinmeyen hata'));
        }
      } catch (e) {
        alert('⚠️ Bağlantı hatası: ' + e.message);
      } finally {
        this.launchingScript = null;
      }
    },

    async loadLocalModels() {
      this.localModelsLoading = true;
      try {
        const data = await this.getJson(this.apiBase + '/api/models/local-fs');
        if (data && data.models) {
          this.localModels = data.models;
          this.localModelsHw = data.hardware;
        }
      } catch (e) {
        console.error('Local models error:', e);
      } finally {
        this.localModelsLoading = false;
      }
    },

    async rescanLocalModels() {
      this.localModelsLoading = true;
      try {
        const res = await fetch(this.apiBase + '/api/models/local-fs/rescan', { method: 'POST' });
        const data = await res.json();
        if (res.ok && data.models) {
          this.localModels = data.models;
          alert('✨ ' + data.models.length + ' adet yerel model önbelleğe alındı.');
        }
      } catch (e) {
        alert('Yeniden tarama hatası: ' + e.message);
      } finally {
        this.localModelsLoading = false;
      }
    },

    openTierWhy(model) {
      if (!model) return;
      const t = this.tierOf(model);
      const rv = model.required_vram_gb != null ? model.required_vram_gb : 0;
      const rr = model.required_ram_gb != null ? model.required_ram_gb : 0;
      const hwVram = this.hardware?.vram_gb || 12;
      const hwRam = this.hardware?.ram_gb || 32;
      const vramMargin = t.vram_margin_gb != null ? t.vram_margin_gb : (hwVram - rv);
      const ramMargin = t.ram_margin_gb != null ? t.ram_margin_gb : (hwRam - rr);
      const cmd = t.verify_cmd || ('llmfit check ' + (model.hf_id || model.name || ''));
      this.tierWhyData = {
        model_name: model.name || model.hf_id || 'Model',
        tier: t.tier,
        tone: t.tone,
        explanation: t.explanation || `VRAM marjı: ${(vramMargin >= 0 ? '+' : '') + vramMargin.toFixed(1)} GB (donanım: ${hwVram} GB, model: ${rv} GB), RAM marjı: ${(ramMargin >= 0 ? '+' : '') + ramMargin.toFixed(1)} GB`,
        inputs: t.inputs || {
          vram_gb: hwVram,
          required_vram_gb: rv,
          ram_gb: hwRam,
          required_ram_gb: rr,
          run_mode: model.run_mode || ''
        },
        vram_margin_gb: vramMargin,
        ram_margin_gb: ramMargin,
        verify_cmd: cmd
      };
      this.tierWhyModalOpen = true;
    },

    async runArenaDuel() {
      if (!this.arenaModelA || !this.arenaModelB) {
        alert(window.t ? window.t('arena.selectBoth') : 'Lütfen karşılaştırılacak iki modeli seçin.');
        return;
      }
      this.arenaRunning = true;
      this.arenaResult = null;
      this.arenaVoteResult = null;
      try {
        const payload = {
          model_a: this.arenaModelA,
          model_b: this.arenaModelB,
          prompt: this.arenaPrompt,
          max_tokens: 120,
          blind: Boolean(this.arenaBlind),
        };
        const res = await fetch(this.apiBase + '/api/arena/duel', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (res.ok) {
          this.arenaResult = data;
        } else {
          const detail = data.detail || (window.t ? window.t('arena.unknownError') : 'Bilinmeyen hata');
          alert((window.t ? window.t('arena.duelError') : 'Arena hatası:') + ' ' + detail);
        }
      } catch (e) {
        alert((window.t ? window.t('arena.connError') : 'Arena bağlantı hatası:') + ' ' + e.message);
      } finally {
        this.arenaRunning = false;
      }
    },

    async voteArena(choice) {
      if (!this.arenaResult || !this.arenaResult.duel_id) return;
      this.arenaVoting = true;
      try {
        const res = await fetch(this.apiBase + '/api/arena/vote', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            duel_id: this.arenaResult.duel_id,
            choice: choice,
          }),
        });
        const data = await res.json();
        if (res.ok && data.data) {
          this.arenaVoteResult = data.data;
          if (typeof this.toast === 'function') {
            const title = window.t ? window.t('arena.toastTitle') : 'Oy Kaydedildi';
            const body = window.t ? window.t('arena.toastBody') : 'Elo puanları güncellendi.';
            this.toast(title, body, 'success', 3000);
          }
          await this.loadArenaLeaderboard();
        } else {
          const detail = data.detail || (window.t ? window.t('arena.unknownError') : 'Bilinmeyen hata');
          alert((window.t ? window.t('arena.voteError') : 'Oylama hatası:') + ' ' + detail);
        }
      } catch (e) {
        alert((window.t ? window.t('arena.voteConnError') : 'Oylama bağlantı hatası:') + ' ' + e.message);
      } finally {
        this.arenaVoting = false;
      }
    },

    async loadArenaLeaderboard() {
      this.arenaLeaderboardLoading = true;
      this.arenaLeaderboardError = '';
      try {
        const res = await fetch(this.apiBase + '/api/arena/leaderboard');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        this.arenaLeaderboard = data.leaderboard || [];
      } catch (e) {
        console.debug('Arena liderlik tablosu alınamadı:', e && e.message);
        this.arenaLeaderboard = [];
        this.arenaLeaderboardError = e && e.message ? e.message : 'Liderlik tablosu alınamadı';
      } finally {
        this.arenaLeaderboardLoading = false;
      }
    },

    _shareCardPalette() {
      // Kart renkleri tema duyarlıdır: aktif temanın CSS değişkenlerinden okunur
      // (gpu-telemetry.js renderGpuCharts'taki --accent deseninin aynısı).
      const cs = typeof getComputedStyle === 'function'
        ? getComputedStyle(document.documentElement)
        : null;
      const v = (name, fallback) => ((cs ? cs.getPropertyValue(name) : '') || '').trim() || fallback;
      return {
        bg1: v('--bg', '#0a0a09'),
        bg2: v('--surface-2', '#161612'),
        border: v('--border', '#2a2a24'),
        text: v('--text', '#eaeaea'),
        muted: v('--muted', '#7a7a72'),
        success: v('--success', '#4af626'),
        warn: v('--warn', '#f0a030'),
        inv: v('--inv', '#0a0a09'),
      };
    },

    generateArenaShareCard() {
      if (!this.arenaResult || !this.arenaResult.results) return;
      const resA = this.arenaResult.results.model_a || {};
      const resB = this.arenaResult.results.model_b || {};
      const nameA = this.arenaVoteResult?.revealed?.model_a ?? resA.model ?? 'Model A';
      const nameB = this.arenaVoteResult?.revealed?.model_b ?? resB.model ?? 'Model B';
      const T = (key, vars) => (typeof this.t === 'function' ? this.t(key, vars) : null);
      const P = this._shareCardPalette();

      // Oylama sonrası gerçek Elo puanı (API: elo_changes[].new_elo) ve
      // liderlik tablosundan toplam maç sayısı (total_matches).
      const eloA = this.arenaVoteResult?.elo_changes?.[nameA]?.new_elo;
      const eloB = this.arenaVoteResult?.elo_changes?.[nameB]?.new_elo;
      const lb = Array.isArray(this.arenaLeaderboard) ? this.arenaLeaderboard : [];
      const matchesA = lb.find((e) => e && e.model === nameA)?.total_matches;
      const matchesB = lb.find((e) => e && e.model === nameB)?.total_matches;
      const eloLine = (elo, matches) => [
        elo != null ? (T('arena.cardElo', { elo: Math.round(elo) }) || `ELO: ${Math.round(elo)}`) : null,
        matches != null ? (T('arena.cardMatches', { n: matches }) || `Maç: ${matches}`) : null,
      ].filter(Boolean).join(' · ');

      const canvas = document.createElement('canvas');
      canvas.width = 800;
      canvas.height = 460;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      // Arka plan: tema duyarlı gradient
      const bgGrad = ctx.createLinearGradient(0, 0, 800, 460);
      bgGrad.addColorStop(0, P.bg1);
      bgGrad.addColorStop(1, P.bg2);
      ctx.fillStyle = bgGrad;
      ctx.fillRect(0, 0, 800, 460);

      // Çerçeve
      ctx.strokeStyle = P.border;
      ctx.lineWidth = 3;
      ctx.strokeRect(1, 1, 798, 458);

      // Başlık
      ctx.fillStyle = P.warn;
      ctx.font = 'bold 22px system-ui, -apple-system, sans-serif';
      ctx.fillText(T('arena.cardTitle') || '⚡ BENCHCOMPASS ARENA DÜELLOSU', 40, 48);

      // Donanım Alt Başlığı
      const devName = this.hardware?.device_name || 'Yerel Donanım';
      const vram = this.hardware?.vram_gb ? `${this.hardware.vram_gb} GB VRAM` : '';
      ctx.fillStyle = P.muted;
      ctx.font = '13px monospace';
      ctx.fillText(`${T('arena.cardHardware') || 'Donanım'}: ${devName} ${vram ? '· ' + vram : ''}`, 40, 72);

      // Model A Kutusu
      ctx.fillStyle = P.bg2;
      ctx.strokeStyle = P.border;
      ctx.lineWidth = 1;
      ctx.beginPath();
      if (typeof ctx.roundRect === 'function') {
        ctx.roundRect(40, 95, 345, 230, 8);
      } else {
        ctx.rect(40, 95, 345, 230);
      }
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = P.text;
      ctx.font = 'bold 16px monospace';
      ctx.fillText(nameA.length > 24 ? nameA.slice(0, 22) + '...' : nameA, 60, 130);

      ctx.fillStyle = P.success;
      ctx.font = 'bold 22px system-ui, sans-serif';
      ctx.fillText(`${resA.tok_per_sec || 0} tok/s`, 60, 175);

      ctx.fillStyle = P.muted;
      ctx.font = '13px monospace';
      ctx.fillText(`TTFT: ${resA.ttft_ms || 0} ms${resA.ttft_method && resA.ttft_method !== 'measured' ? (T('arena.ttftEstimated') || ' (tahmini)') : ''}`, 60, 210);
      ctx.fillText(`Tokens: ${resA.total_tokens || 0}`, 60, 235);
      const lineA = eloLine(eloA, matchesA);
      if (this.arenaVoteResult && lineA) {
        ctx.fillStyle = P.warn;
        ctx.fillText(lineA, 60, 252);
      }

      if (this.arenaResult.winner === resA.model && !this.arenaResult.blind) {
        ctx.fillStyle = P.success;
        ctx.beginPath();
        if (typeof ctx.roundRect === 'function') {
          ctx.roundRect(60, 260, 110, 28, 4);
        } else {
          ctx.rect(60, 260, 110, 28);
        }
        ctx.fill();
        ctx.fillStyle = P.inv;
        ctx.font = 'bold 12px system-ui, sans-serif';
        ctx.fillText(T('arena.cardWinner') || '🏆 KAZANAN', 75, 279);
      }

      // Model B Kutusu
      ctx.fillStyle = P.bg2;
      ctx.strokeStyle = P.border;
      ctx.lineWidth = 1;
      ctx.beginPath();
      if (typeof ctx.roundRect === 'function') {
        ctx.roundRect(415, 95, 345, 230, 8);
      } else {
        ctx.rect(415, 95, 345, 230);
      }
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = P.text;
      ctx.font = 'bold 16px monospace';
      ctx.fillText(nameB.length > 24 ? nameB.slice(0, 22) + '...' : nameB, 435, 130);

      ctx.fillStyle = P.success;
      ctx.font = 'bold 22px system-ui, sans-serif';
      ctx.fillText(`${resB.tok_per_sec || 0} tok/s`, 435, 175);

      ctx.fillStyle = P.muted;
      ctx.font = '13px monospace';
      ctx.fillText(`TTFT: ${resB.ttft_ms || 0} ms${resB.ttft_method && resB.ttft_method !== 'measured' ? (T('arena.ttftEstimated') || ' (tahmini)') : ''}`, 435, 210);
      ctx.fillText(`Tokens: ${resB.total_tokens || 0}`, 435, 235);
      const lineB = eloLine(eloB, matchesB);
      if (this.arenaVoteResult && lineB) {
        ctx.fillStyle = P.warn;
        ctx.fillText(lineB, 435, 252);
      }

      if (this.arenaResult.winner === resB.model && !this.arenaResult.blind) {
        ctx.fillStyle = P.success;
        ctx.beginPath();
        if (typeof ctx.roundRect === 'function') {
          ctx.roundRect(435, 260, 110, 28, 4);
        } else {
          ctx.rect(435, 260, 110, 28);
        }
        ctx.fill();
        ctx.fillStyle = P.inv;
        ctx.font = 'bold 12px system-ui, sans-serif';
        ctx.fillText(T('arena.cardWinner') || '🏆 KAZANAN', 450, 279);
      }

      // ELO & Sonuç Bandı (Alt Kutu)
      ctx.fillStyle = P.bg2;
      ctx.strokeStyle = P.border;
      ctx.beginPath();
      if (typeof ctx.roundRect === 'function') {
        ctx.roundRect(40, 345, 720, 50, 6);
      } else {
        ctx.rect(40, 345, 720, 50);
      }
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = P.text;
      ctx.font = '13px monospace';
      if (this.arenaVoteResult) {
        const deltaA = this.arenaVoteResult.elo_changes?.[nameA]?.delta ?? 0;
        const deltaB = this.arenaVoteResult.elo_changes?.[nameB]?.delta ?? 0;
        const signA = deltaA >= 0 ? '+' : '';
        const signB = deltaB >= 0 ? '+' : '';
        const voteDone = T('arena.cardVoteDone') || 'Oylama Tamamlandı';
        const eloChange = T('arena.cardEloChange') || 'ELO Değişimi';
        ctx.fillText(`${voteDone} · ${eloChange}: Model A (${signA}${deltaA}) | Model B (${signB}${deltaB})`, 55, 375);
      } else {
        ctx.fillText(T('arena.cardBlindNote') || 'Yerel Çift-Kör Model Düellosu · Gerçek Zamanlı Performans Karşılaştırması', 55, 375);
      }

      // Filigran / Altbilgi — sürüm /api/cc/status'tan (tek kaynak), fallback rc sabiti
      const appVer = this.ccStatus?.version || '0.28.0-rc.2';
      ctx.fillStyle = P.muted;
      ctx.font = '11px monospace';
      ctx.fillText(`BenchCompass v${appVer} • ${T('arena.cardFooter') || 'Yerel LLM Benchmark ve Değerlendirme Paneli'}`, 40, 430);

      this.arenaShareImage = canvas.toDataURL('image/png');
      this.arenaShareModalOpen = true;
    },

    downloadArenaShareCard() {
      if (!this.arenaShareImage) return;
      const a = document.createElement('a');
      a.download = `benchcompass-arena-${Date.now()}.png`;
      a.href = this.arenaShareImage;
      a.click();
    },

    async copyArenaShareCard() {
      if (!this.arenaShareImage) return;
      try {
        const res = await fetch(this.arenaShareImage);
        const blob = await res.blob();
        if (navigator.clipboard && navigator.clipboard.write && typeof ClipboardItem !== 'undefined') {
          await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
          this.arenaShareCopied = true;
          setTimeout(() => { this.arenaShareCopied = false; }, 2500);
        } else {
          this.downloadArenaShareCard();
        }
      } catch (e) {
        console.debug('Panoya kopyalama başarısız, indiriliyor:', e);
        this.downloadArenaShareCard();
      }
    },

    async pullOllamaModel(targetModel) {
      const modelName = (targetModel || this.pullModelInput || '').trim();
      if (!modelName) return;
      const tt = (key, vars) => (typeof this.t === 'function' ? this.t(key, vars) : null);

      if (!Array.isArray(this.activeDownloads)) this.activeDownloads = [];
      // Mükerrer indirme engeli: aynı model kuyrukta aktifse yeni kayıt açma.
      if (this.activeDownloads.some((d) => d.model === modelName && d.status === 'running')) {
        if (typeof this.toast === 'function') {
          this.toast(tt('pull.duplicate', { model: modelName }) || `${modelName} zaten indirme kuyruğunda.`, modelName, 'error', 4000);
        }
        return;
      }
      // Ollama etiket doğrulaması: HF repo kimliği (örn. Qwen/Qwen2.5-7B) pull'da bulunamaz —
      // geçerli Ollama etiketleri tamamen küçük harftir (özel registry'ler dahil).
      if (/[A-Z]/.test(modelName)) {
        if (typeof this.toast === 'function') {
          this.toast(tt('pull.invalidName', { model: modelName }) || `${modelName} bir HuggingFace repo kimliğine benziyor — Ollama etiketi bekleniyor.`, modelName, 'error', 6000);
        }
        return;
      }

      const dlItem = {
        task_uuid: 'pending-' + Date.now(),
        model: modelName,
        progress: 0,
        detail: tt('pull.downloading') || 'İndiriliyor...',
        status: 'running',
      };
      this.activeDownloads.push(dlItem);
      // Alpine reactivity (E2E bulgusu): push sonrası ham dlItem referansı
      // üzerindeki atamalar render tetiklemez — dizinin reaktif elemanını
      // (proxy) referans alıp tüm güncellemeler onun üzerinden yapılır.
      const dlRef = this.activeDownloads[this.activeDownloads.length - 1];

      try {
        const res = await fetch(`${this.apiBase || ''}/api/ollama/pull`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model: modelName }),
        });
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const data = await res.json();
        if (!data.ok || !data.task_uuid) {
          throw new Error(data.error || 'İndirme başlatılamadı');
        }

        dlRef.task_uuid = data.task_uuid;
        this.pullModelInput = '';

        // Poll task status — sızıntısız: ardışık hata sayacı + toplam zaman aşımı.
        const MAX_CONSEC_ERR = 5;
        const deadline = Date.now() + 35 * 60 * 1000; // backend pull timeout (1800s) ile hizalı
        let errCount = 0;
        const pollTimer = setInterval(async () => {
          const failItem = (msg) => {
            clearInterval(pollTimer);
            dlRef.status = 'failed';
            dlRef.detail = msg;
            if (typeof this.toast === 'function') {
              this.toast(msg, modelName, 'error', 5000);
            }
          };
          if (Date.now() > deadline) {
            failItem(tt('pull.timeout') || 'İndirme zaman aşımına uğradı (35 dk) — tekrar deneyin.');
            return;
          }
          try {
            const taskRes = await fetch(`${this.apiBase || ''}/api/tasks/${dlRef.task_uuid}`);
            if (!taskRes.ok) {
              errCount += 1;
              if (errCount >= MAX_CONSEC_ERR) {
                failItem(tt('pull.lostTask') || 'İndirme görevi bulunamadı (arka plan servisi yeniden başlamış olabilir) — tekrar deneyin.');
              }
              return;
            }
            errCount = 0;
            const task = await taskRes.json();
            dlRef.progress = task.progress ?? dlRef.progress;
            if (task.detail) dlRef.detail = task.detail;

            if (task.status === 'completed') {
              clearInterval(pollTimer);
              dlRef.status = 'completed';
              dlRef.progress = 100;
              dlRef.detail = tt('pull.success') || 'Model başarıyla indirildi!';
              if (typeof this.toast === 'function') {
                this.toast(dlRef.detail, modelName, 'success', 4000);
              }
              if (typeof this.loadOllamaModels === 'function') this.loadOllamaModels();
              setTimeout(() => {
                this.activeDownloads = this.activeDownloads.filter(d => d.task_uuid !== dlRef.task_uuid);
              }, 4000);
            } else if (task.status === 'failed') {
              clearInterval(pollTimer);
              dlRef.status = 'failed';
              dlRef.detail = `${tt('pull.error') || 'İndirme hatası:'} ${task.error || ''}`;
              if (typeof this.toast === 'function') {
                this.toast(dlRef.detail, modelName, 'error', 5000);
              }
            }
          } catch (pollErr) {
            errCount += 1;
            if (errCount >= MAX_CONSEC_ERR) {
              failItem(`${tt('pull.error') || 'İndirme hatası:'} ${pollErr && pollErr.message ? pollErr.message : pollErr}`);
            }
          }
        }, 1000);
      } catch (err) {
        dlRef.status = 'failed';
        dlRef.detail = `${tt('pull.error') || 'İndirme hatası:'} ${err.message || err}`;
        if (typeof this.toast === 'function') {
          this.toast(dlRef.detail, modelName, 'error', 5000);
        }
      }
    },

    async retryOllamaDownload(dlItem) {
      // Başarısız indirmeyi kuyruktan düşürüp aynı modelle yeniden başlatır.
      if (!dlItem || !dlItem.model) return;
      this.removeOllamaDownload(dlItem);
      await this.pullOllamaModel(dlItem.model);
    },

    removeOllamaDownload(dlItem) {
      // İndirme kaydını kuyruktan kaldırır (failed kayıtlar için elle temizlik).
      if (!Array.isArray(this.activeDownloads)) return;
      this.activeDownloads = this.activeDownloads.filter((d) => d.task_uuid !== dlItem.task_uuid);
    },

    async loadAsrStatus() {
      this.asrLoading = true;
      this.asrError = '';
      try {
        const res = await fetch(`${this.apiBase || ''}/api/asr/status`);
        if (res.ok) {
          this.asrStatus = await res.json();
        } else {
          // Dürüst hata durumu (denetim kapanışı): panel sessizce kaybolmaz.
          this.asrError = (typeof this.t === 'function' ? this.t('asr.httpError', { status: res.status }) : `HTTP ${res.status}`);
        }
      } catch (e) {
        this.asrError = (typeof this.t === 'function' ? this.t('asr.connError') : 'ASR durumu alınamadı') + (e && e.message ? `: ${e.message}` : '');
      } finally {
        this.asrLoading = false;
      }
    },

    get filteredSearchResults() {
      if (!this.searchQuery) return [];
      const q = this.searchQuery.toLowerCase().trim();
      const res = [];
      const views = [
        { title: 'Genel Bakış / Overview', view: 'overview', icon: '📊', type: 'View' },
        { title: 'Kontrol Merkezi / Control Center', view: 'control-center', icon: '🏠', type: 'View' },
        { title: 'Medya Kiti & Hub', view: 'mediakit', icon: '🚀', type: 'View' },
        { title: 'Modellerim (Ollama)', view: 'modellerim', icon: '🖥️', type: 'View' },
        { title: 'Yerel GGUF Modelleri / Local Models', view: 'local-models', icon: '📦', type: 'View' },
        { title: 'Yerel Model Arena / Model Arena', view: 'arena', icon: '⚔️', type: 'View' },
        { title: 'Benchmark Geçmişi / History', view: 'history', icon: '📈', type: 'View' },
        { title: 'Grafikler / Charts', view: 'charts', icon: '📉', type: 'View' },
        { title: 'Karar Matrisi / Matrix', view: 'matris', icon: '🧭', type: 'View' },
        { title: 'Telemetri & Enerji / Telemetry', view: 'telemetri', icon: '📡', type: 'View' },
        { title: 'Veri Toplayıcı / Collector', view: 'collector', icon: '📥', type: 'View' },
        { title: 'Benchmark Çalıştır / Run', view: 'benchmark', icon: '⚡', type: 'View' },
        { title: 'Model Mağazası / Store', view: 'magaza', icon: '🏪', type: 'View' },
        { title: 'Değerlendirme Raporu / Eval Report', view: 'rapor', icon: '📋', type: 'View' },
        { title: 'Kodlama Değerlendirmesi / Code Eval', view: 'kodlama', icon: '🧪', type: 'View' },
        { title: 'API Dokümantasyonu / API Docs', view: 'api', icon: '🔌', type: 'View' },
        { title: 'Ayarlar / Settings', view: 'settings', icon: '⚙️', type: 'View' },
        { title: 'Denetim Paneli / Audit Panel', view: 'denetim', icon: '🛡️', type: 'View' },
        { title: 'Kullanım Kılavuzu / User Guide', view: 'guide', icon: '📖', type: 'View' },
      ];
      views.forEach(v => {
        if (v.title.toLowerCase().includes(q) || (v.view && v.view.toLowerCase().includes(q))) res.push(v);
      });
      (this.latest || []).forEach(m => {
        if ((m.name && m.name.toLowerCase().includes(q)) || (m.notes && m.notes.toLowerCase().includes(q))) {
          res.push({
            title: m.name + (m.notes ? ' (' + m.notes.slice(0, 35) + ')' : ''),
            view: 'overview',
            icon: '🤖',
            type: 'Model',
            modelName: m.name,
          });
        }
      });
      (this.ccDocs || []).forEach(d => {
        if (d.name.toLowerCase().includes(q) || d.path.toLowerCase().includes(q)) {
          res.push({ title: d.name, path: d.path, icon: '📄', type: 'Doc' });
        }
      });
      return res.slice(0, 12);
    },

    selectSearchResult(item) {
      if (item.view) {
        this.view = item.view;
        if (item.view === 'control-center') this.loadControlCenter();
        if (item.view === 'modellerim') this.loadOllamaModels();
        if (item.view === 'local-models' && typeof this.loadLocalModels === 'function') this.loadLocalModels();
        if (item.view === 'arena' && typeof this.loadArenaLeaderboard === 'function') this.loadArenaLeaderboard();
        if (item.view === 'matris' && typeof this.loadMatrix === 'function') this.loadMatrix();
        if (item.view === 'telemetri') {
          if (typeof this.loadEnergyModels === 'function') this.loadEnergyModels();
          if (typeof this.loadCalibration === 'function') this.loadCalibration();
        }
        if (item.view === 'charts' && typeof this.renderCharts === 'function') {
          if (this.$nextTick) this.$nextTick(() => this.renderCharts());
          else this.renderCharts();
        }
        if (item.view === 'kodlama' && typeof this.loadEvalQuality === 'function') this.loadEvalQuality();
        if (item.view === 'denetim' && typeof this.auditAc === 'function') this.auditAc();
        if (item.modelName) {
          this.search = item.modelName;
        }
      }
      this.searchModalOpen = false;
      this.searchQuery = '';
    },
};
