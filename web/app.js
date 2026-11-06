/* BenchCompass — Sprint 4 ana Alpine.js bileşeni
 *
 * İçerik:
 *   1. Yardımcılar: esc, ctx, shortModelName, renderNotesParts, parseNotesFlags
 *   2. computeTier() — api/compat.py ile BİREBİR AYNI formül (Bölüm 2.2)
 *   3. dashboard() — Alpine bileşeni: state, fetch, filtreleme, sıralama,
 *      preset'ler, history, charts, collector, snapshot
 *
 * KRİTİK DESEN: Tier DB'ye yazılmaz, her render'da frontend'de hesaplanır.
 * Donanım profili değişince tüm tier'lar anında güncellenir.
 */

// --- Modüller (Faz 2: app.js modülerleştirme) -------------------------------
import {
  esc, ctx, shortModelName, renderNotesParts, parseNotesFlags,
  fmtMb, fmtW, fmtPct,
} from './modules/format.js';
import { evalGecerliMi, evalTgGuvenilirMi, prepareExtraChartData } from './modules/eval-helpers.js';
import { computeTier, computeContextFlag, buildTooltip } from './modules/tier.js';
import { demoDb } from './modules/demo-data.js';
import { gpuTelemetryMethods } from './modules/gpu-telemetry.js';
import { guideMethods } from './modules/guide.js';
import { controlCenterMethods } from './modules/control-center.js';
import { chartMethods } from './modules/charts.js';
import { settingsMethods } from './modules/settings.js';
import { auditMethods } from './modules/audit.js';


// --- Uyumluluk motoru: web/modules/tier.js (api/compat.py G8 mirror) -------

// --- Demo veri: web/modules/demo-data.js ------------------------------------

// --- Alpine bileşeni --------------------------------------------------------

const DASHBOARD_MIXINS = [
  gpuTelemetryMethods,
  guideMethods,
  controlCenterMethods,
  chartMethods,
  settingsMethods,
  auditMethods,
];

function dashboard() {
  const component = {
    // --- State ---
    view: 'overview',
    apiBase: 'http://localhost:8788',
    collectorBase: 'http://localhost:8790',
    lang: 'tr',

    latest: [],
    history: [],
    source: '-',
    hardware: { vram_gb: 12, ram_gb: 32 },
    thresholds: { vram_full_margin: 2.0, ram_full_margin: 4.0, vram_caution_margin: -1.5 },

    // Sprint 44: canlı GPU telemetri (3 sn poll; sekmede zaman serisi)
    gpu: { available: false },
    telemetryAlerts: [],
    gpuHistory: [],
    _gpuTimer: null,
    _gpuCharts: {},

    // Sprint 45: enerji/maliyet analizi (telemetri sekmesi)
    energyModels: [],
    energyModel: '',
    energyReport: null,
    energyError: '',
    energyLoading: false,

    // P1-2: tahmin isabeti (kalibrasyon) durumu
    calib: null,
    calibLoading: false,
    calibError: '',

    // Sprint 46: veri-güdümlü karar matrisi (matris sekmesi)
    matrixData: null,
    matrixLoading: false,
    matrixError: '',

    // Sprint 47: görev profili önerisi (matris sekmesi)
    profileWeights: {},
    profileResult: null,
    profileLoading: false,
    profileError: '',

    // Sprint 51: NPU telemetri durumu (telemetri sekmesi)
    npu: { available: false },

    // Sprint 53: Control Center (Operasyonel Karargah)
    ccStatus: null,
    ccFlags: { flags: [], counts: { critical: 0, high: 0, medium: 0, low: 0 }, total: 0 },
    ccVersions: null,
    ccRecent: [],
    ccDiagnostics: null,
    ccDocs: [],
    ccDbInfo: null,
    ccLoading: false,
    // Sprint 53 / ADR-0012: Başlatıcılar ve Yerel Model Keşfi
    launchers: [],
    launchingScript: null,
    localModels: [],
    localModelsLoading: false,
    localModelsHw: null,
    // Sprint 53 / ADR-0012: Local Model Arena
    arenaModelA: '',
    arenaModelB: '',
    arenaPrompt: 'Hızlıca 3 maddede yerel yapay zeka çalıştırmanın avantajlarını yaz.',
    arenaRunning: false,
    arenaResult: null,
    arenaBlind: false,
    arenaVoteResult: null,
    arenaVoting: false,
    arenaLeaderboard: [],
    arenaLeaderboardLoading: false,
    arenaLeaderboardError: '',
    arenaShareModalOpen: false,
    arenaShareImage: '',
    arenaShareCopied: false,
    activeDownloads: [],
    pullModelInput: '',
    asrStatus: null,
    asrLoading: false,
    asrError: '',
    // 0.28.0-rc.2: Canlı Arayüz Denetim Paneli (ADR-0002 / G12)
    auditItems: [],
    auditKararFiltre: '',
    auditArama: '',
    auditPromptMetni: '',
    searchModalOpen: false,
    searchQuery: '',

    // Sprint 6: Ayarlar sekmesi — tüm donanim config (config/hardware_profile.json)
    hardwareConfig: null,   // tüm config (active_profile + profiles[] + tier_thresholds)
    settingsForm: {         // form input'ları için kopya
      device_name: '', cpu: '', gpu: '', vram_gb: 12, ram_gb: 32,
      npu_tops: null, storage_gb: null, os: '', cuda_version: '',
    },
    settingsMsg: '',
    settingsAdvancedOpen: false,
    thresholdsForm: { vram_full_margin: 2.0, ram_full_margin: 4.0, vram_caution_margin: -1.5 },

    // Filtreleme/sıralama state
    search: '',
    useFilter: 'all',
    sortBy: 'fit',
    onlyCompatible: false,
    onlyFavorites: false,
    notesSearch: '',
    compactCards: false,
    tierQuickFilter: null,
    minContext: 0,
    viewTimeline: false,
    activityLog: [],
    // --- Yeni Ozellik State'leri ---
    doctorReport: null,
    doctorLoading: false,
    benchcompassFitData: null,
    benchcompassFitLoading: false,
    providerConfig: null,
    providerLoading: false,
    cacheStatus: null,
    reportLoading: false,
    showDoctor: false,
    showBenchcompassFit: false,

    // Sprint 27: LLMFit Benchmark Eval rapor durumu ([ RAPOR ] boş durumu — C1)
    evalReportExists: false,
    evalReportChecked: false,
    evalReportUpdatedAt: null,

    // Sprint 34: Geçmiş koşu listesi (benchmarks zaman serisi — P2)
    evalHistory: [],
    evalHistoryLoading: false,

    // Sprint 54: Kodlama Değerlendirmesi sekmesi — /api/eval/quality
    // { total, ozet: [...], kayitlar: [...] } | null (yüklenmedi/hata)
    evalQuality: null,
    evalQualityLoading: false,
    evalQualityError: '',

    // Adım 3: McNemar eşli karşılaştırma — /api/eval/compare
    compareModelA: '',
    compareModelB: '',
    evalCompare: null,
    evalCompareLoading: false,
    evalCompareError: '',

    // Snapshot
    snapshotName: '',
    snapshotMsg: '',

    // Sprint 17: history toplu/seçerek silme
    selectedHistoryIds: [],
    historyDeleteMsg: '',

    // API/Collector log
    apiLog: 'API logları burada.',
    apiInfo: 'Hazır.',
    jsonOutput: '',
    collectorLog: 'Collector logları burada görünür.',
    collectorInfo: 'Collector bekleniyor.',

    // History karşılaştırma
    compareA: 0,
    compareB: 1,
    compareResult: [],

    // Charts
    charts: {},
    chartUseCase: 'all',  // Sprint 5/15: use-case trend grafiği için seçili değer (all = filtre yok)
    chartModel: '',       // Sprint 15: model filtresi ('' = tüm modeller)
    extraChartsEmpty: false,  // Sprint 15: s9 ekstra grafiklerin boş state'i
    extraChartsError: '',     // Sprint 15: s9 endpoint hata mesajı

    // Sprint 8: llmfit proxy state'leri
    modelDetail: null,             // info modal içeriği
    modelDetailOpen: false,
    modelDetailLoading: false,
    modelDetailError: '',

    // Upgrade Simulator (Ayarlar sekmesi)
    simOpen: false,
    simVram: 12,
    simRam: 32,
    simContext: 8192,
    simResults: [],
    simLoading: false,
    simError: '',

    // Model Karsilastirma (diff modal)
    diffOpen: false,
    diffLoading: false,
    diffError: '',
    diffData: null,
    diffCandidates: [],  // secili 2 model (model adi)

    // Karar asistani: llmfit recommend ciktisi
    recommendData: null,
    recommendLoading: false,
    // Sprint 21: frontier baseline karşılaştırması
    baselineData: null,
    baselineLoading: false,
    baselineError: '',

    // Sprint 9: Benchmark
    benchmarkModel: 'qwen3:8b',
    benchmarkProvider: 'ollama',
    benchmarkShare: false,
    benchmarkLoading: false,
    benchmarkResult: null,
    benchmarkTaskId: null,
    benchmarkTimer: null,
    benchmarkHistory: [],

    // Adım 4: eşzamanlılık stresi — /api/benchmark/concurrent
    concurrentResults: null,
    concurrentLoading: false,
    concurrentError: '',

    // Adım 5: interconnect / çoklu GPU simülatörü — /api/compat/simulate
    interconnectGpuCount: 1,
    interconnectType: 'single',
    interconnectResult: null,
    interconnectLoading: false,
    interconnectError: '',

    // Adım 6: red-team — /api/eval/redteam-plan + /api/eval/redteam/grade
    redteamTasks: [],
    redteamTaskId: '',
    redteamResponse: '',
    redteamResult: null,
    redteamLoading: false,
    redteamError: '',

    // Sprint 10: Ollama modellerim
    installedModels: [],
    installedModelsLoading: false,
    installedModelsError: '',
    runningOllamaModels: [],
    benchmarkAllTaskId: null,
    benchmarkAllTotal: 0,
    benchmarkAllProgress: 0,
    benchmarkAllRunning: false,

    // Test Chat & Inference Doğrulama State
    chatModalOpen: false,
    chatModelName: '',
    chatPrompt: 'Merhaba, sen kimsin? Yeteneklerini ve ne yapabileceğini tek cümleyle özetle.',
    chatResponse: null,
    chatLoading: false,
    chatError: '',
    tierWhyModalOpen: false,
    tierWhyData: null,

    // Sprint 9: Model Magazasi
    storeQuery: '',
    storeResults: [],
    storeSource: 'hf',   // Sprint 19: 'local-catalog' | 'hf' | 'none'
    // Sprint 25: Magaza filtreleri
    storeProviders: [],  // /api/catalog provders (filtre select seçenekleri)
    storeProvider: '',
    storeUseCase: '',
    storeMoe: false,
    storeMinCtx: 0,
    downloadedModels: [],
    runningServers: [],

    // --- Kilavuz State ---
    guideSearch: '',
    guideOpenSections: {
      welcome: true,
      quickstart: false,
      tier: false,
      hardware: false,
      moe: false,
      runtime: false,
      benchmark: false,
      decision: false,
      charts: false,
      collector: false,
      store: false,
      compare: false,
      upgrade: false,
      ollama: false,
      rapor: false,
      faq: false,
      shortcuts: false,
      testing: false,
      dictionary: false,
    },
    guideDictionaryOpen: {},
    guideDictionary: [
      { term: 'LLM', simple: 'Çok okumuş bir robot beyin: yazıyla konuşan, sorulara cevap veren yapay zeka modeli.', technical: 'Large Language Model — milyarlarca parametreyle eğitilmiş sinir ağı.' },
      { term: 'Token', simple: 'Metnin parçalandığı küçük kelime parçaları. Model bir seferde bunlardan okur/yazar.', technical: 'Kelime altı birim; 1 token ≈ 0.75 kelime (İngilizce).' },
      { term: 'VRAM', simple: 'Ekran kartının (GPU) hafızası. Büyük masa gibi — model ne kadar büyükse o kadar yer ister.', technical: 'Video RAM — GPU veri tutma alanı (GB cinsinden).' },
      { term: 'RAM', simple: 'Bilgisayarın ana hafızası. Yan masa gibi — sistem ve modeller burada çalışır.', technical: 'Random Access Memory — CPU için geçici çalışma belleği.' },
      { term: 'MoE', simple: '8 aşçılı lokanta: her siparişte sadece 1-2 aşçı çalışır. Hepsi çalışsaydı daha çok yer kaplardı.', technical: 'Mixture-of-Experts — aktif/toplam parametre ayrımıyla VRAM tasarrufu.' },
      { term: 'GGUF', simple: 'Modellerin saklandığı konserve kutusu formatı. llama.cpp ve arkadaşları bunu okur.', technical: 'GGUF — GGML tabanlı quantize edilmiş model formatı.' },
      { term: 'Quantizasyon', simple: 'Modelin beynini küçültme işlemi: çok kesin sayıları az kesin yaparak daha az yer kaplatma.', technical: 'Kesinliği (fp16→int4) düşürerek boyut/hız optimize etme.' },
      { term: 'tok/s', simple: 'Saniyede üretilen kelime parçası sayısı. Arabanın hız göstergesi gibi.', technical: 'Token per second — inference hız ölçüsü.' },
      { term: 'TTFT', simple: 'Soruyu yazıp Enter tuşuna bastıktan sonra ilk cevabın gelmesi için geçen süre.', technical: 'Time To First Token — ilk token üretim gecikmesi (ms).' },
      { term: 'Context Window', simple: 'Modelin aynı anda hatırlayabildiği metin uzunluğu. Kısa olursa sohbetin başını unutur.', technical: 'Tek seferde işlenebilen maksimum token sayısı (örn. 4K/8K/128K).' },
      { term: 'Fit Skoru', simple: 'Modelin senin donanımına uyum puanı. 100 değerine yaklaştıkça tam senin için demektir.', technical: 'llmfit uyumluluk skoru (0-100) — donanım ve kullanım senaryosuna göre hesaplanır.' },
      { term: 'Tier', simple: 'Modelin bilgisayarında rahat çalışıp çalışamayacağını söyleyen seviye: Tam Uyumlu / Sınırda / Dikkatli / Uygun Değil.', technical: '4 seviyeli uyumluluk sınıflandırması (api/compat.py).' },
      { term: 'Offload', simple: 'Modelin sığmadığı GPU alanından taşan kısmının CPU/RAM ortamına taşınması. Yavaşlar ama çalışır.', technical: 'Katmanların GPU→CPU taşınması (CPU offload).' },
      { term: 'Inference', simple: 'Modelin düşünüp cevap üretme işlemi. Yazdığın her soruya cevap bu işlemin sonucudur.', technical: 'Modelin eğitim sonrası yeni girdiyle çıktı üretme süreci.' },
    ],

    // --- Ek Ozellikler ---
    autoRefresh: false,
    autoRefreshTimer: null,
    statusDashboard: null,
    statusCollector: null,
    statusOllama: null,
    lastUpdated: null,
    favorites: [],
    lastLog: '',

    // --- Init ---
    async init() {
      // Klavye kisayollari — kullanici etkileşimi backend yuklenmesini beklemez.
      // Listener en basta kaydedilir; boylece gec kalan fetch'ler kisa yollari engellemez.
      document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
          e.preventDefault();
          this.searchModalOpen = !this.searchModalOpen;
          if (this.searchModalOpen) {
            this.$nextTick(() => {
              const el = document.getElementById('global-search-input');
              if (el) el.focus();
            });
          }
          return;
        }
        if (e.key === 'Escape' && this.searchModalOpen) {
          this.searchModalOpen = false;
          return;
        }
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return;
        const key = e.key.toLowerCase();
        const map = {
          '0': 'control-center', 'g': 'overview', 'm': 'modellerim', 'h': 'history',
          'c': 'charts', 'l': 'collector', 'b': 'benchmark',
          's': 'magaza', 'a': 'api', 'y': 'settings', 'k': 'guide',
          '?': 'guide',
        };
        if (map[key]) {
          this.view = map[key];
          if (map[key] === 'control-center') this.loadControlCenter();
          if (map[key] === 'modellerim') this.loadOllamaModels();
          if (map[key] === 'charts') this.$nextTick(() => this.renderCharts());
        }
      });

      // Tema yüklemesi — localStorage'da kayitli tercih
      const saved = localStorage.getItem('benchcompass-theme');
      this.theme = saved || (matchMedia('(prefers-color-scheme:dark)').matches ? 'dark' : 'light');
      this.applyTheme();
      // Dil yüklemesi — i18n katmani (ADR-0009), <html lang> senkronize edilir
      this.lang = window.getLang ? window.getLang() : 'tr';
      if (window.setLang && document.documentElement.getAttribute('lang') !== this.lang) {
        window.setLang(this.lang);
      }
      // Sayfa başlığını dil ile senkronize et
      document.title = window.t ? window.t('app.title') : 'BenchCompass';
      // Donanım profilini çek
      try {
        const hw = await this.getJson(this.apiBase + '/api/hardware');
        this.applyHardwareConfig(hw);
      } catch (e) {
        console.warn('Donanım profili alınamadı, varsayılan kullanılıyor:', e.message);
      }
      // Dashboard verisi
      await this.refreshFromDb();

      // Sistem durumu kontrolleri
      this.checkStatuses();

      // Kayitli favorileri yukle
      try {
        const saved = localStorage.getItem('benchcompass-favorites');
        if (saved) this.favorites = JSON.parse(saved);
      } catch (err) { console.debug(err); }

      // Kayitli filtre tercihlerini yukle
      this._loadFilterState();

      // Provider yapilandirmasini yukle
      this.loadProviderConfig();
      // Magaza filtre seceneklerini yukle (Sprint 25)
      this.loadStoreProviders();
      // Canlı GPU telemetri poll'u (Sprint 44) — sekme gizliyken durur
      this.startGpuPolling();
    },

    // --- Veri çekme ---
    async getJson(url) {
      const r = await fetch(url);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return await r.json();
    },

    async refreshFromDb() {
      try {
        const data = await this.getJson(this.apiBase + '/api/dashboard/summary');
        this.apiInfo = 'DB summary alındı.';
        this.jsonOutput = JSON.stringify(data, null, 2);
        this.latest = data.latest?.models || [];
        this.history = data.history || [];
        this.source = data.source || 'sqlite';
        // Compare default'ları ayarla
        if (this.history.length > 1) {
          this.compareA = 0;
          this.compareB = this.history.length - 1;
        }
        this.log('apiLog', 'Dashboard summary çekildi');
        // Son güncelleme zamanını kaydet
        this.lastUpdated = new Date().toLocaleTimeString('tr-TR');
        this._addActivity('DB yenilendi (' + this.latest.length + ' model)');
        this.toast('Veriler Güncellendi', this.latest.length + ' model ve ölçüm verisi yüklendi.', 'success', 3000);
        // Sprint 6 Ekstra 2: uyumluluk iyileşme bildirimi
        this._checkCompatibilityImprovements();
      } catch (err) {
        this.apiInfo = 'DB summary alınamadı.';
        this.log('apiLog', 'Hata: ' + err.message);
        this.toast('Veri Güncelleme Hatası', err.message, 'error', 4000);
      }
    },

    applyDemo() {
      this.latest = demoDb.latest.models;
      this.history = demoDb.history;
      this.source = 'demo-sqlite';
      this.jsonOutput = JSON.stringify(demoDb, null, 2);
      this._addActivity('Demo verisi yuklendi');
      this.toast('Demo Modu', 'Demo verileri başarıyla yüklendi.', 'info', 3000);
    },

    // --- Tier hesaplama (her model için) ---
    tierOf(m) {
      void this.lang;
      return computeTier(m, this.hardware, this.thresholds);
    },

    // --- Filtrelenmiş + sıralanmış modeller (Kriter #7, #13) ---
    // Memoization: Aynı input kombinasyonu tekrar gelirse hesaplamayı atla.
    _filterCacheKey: null,
    _filterCacheVal: null,
    get filteredModels() {
      void this.lang;
      // Cache key: filter inputs + veri referansi (length + ilk id)
      const dataSig = this.latest.length + ':' + (this.latest[0]?.name || '');
      const key = `${dataSig}|${this.lang}|${this.search}|${this.useFilter}|${this.sortBy}|${this.onlyCompatible}|${this.onlyFavorites}|${this.notesSearch}|${this.minContext}|${this.tierQuickFilter}|${this.hardware.vram_gb}|${this.hardware.ram_gb}`;
      if (this._filterCacheKey === key) return this._filterCacheVal;

      const q = this.search.trim().toLowerCase();
      const nq = this.notesSearch.trim().toLowerCase();
      let rows = this.latest.filter(m => {
        const nameOk = !q || (m.name || '').toLowerCase().includes(q) || String(m.provider || '').toLowerCase().includes(q);
        const useOk = this.useFilter === 'all' || (m.useCase || '') === this.useFilter;
        const tierOk = !this.onlyCompatible || this.tierOf(m).tier === 'Tam Uyumlu';
        const favOk = !this.onlyFavorites || this.favorites.includes(m.name);
        const tierQuickOk = !this.tierQuickFilter || this.tierOf(m).tier === this.tierQuickFilter;
        const ctxOk = !this.minContext || (m.contextWindow || 0) >= this.minContext;
        const notesOk = !nq || (m.notes && String(m.notes).toLowerCase().includes(nq));
        return nameOk && useOk && tierOk && favOk && tierQuickOk && ctxOk && notesOk;
      });

      // Sıralama — mevcut fit/name/context + yeni vram/hız/parametre
      const cmp = {
        fit: (a, b) => (b.fitScore || 0) - (a.fitScore || 0),
        name: (a, b) => (a.name || '').localeCompare(b.name || ''),
        context: (a, b) => (b.contextWindow || 0) - (a.contextWindow || 0),
        vram: (a, b) => (a.required_vram_gb || 9999) - (b.required_vram_gb || 9999),  // en rahat sığan (en az required)
        speed: (a, b) => (b.estimated_speed_tok_s || 0) - (a.estimated_speed_tok_s || 0),
        param: (a, b) => (b.param_count_b || 0) - (a.param_count_b || 0),
      }[this.sortBy] || cmp.fit;
      rows = rows.slice().sort(cmp);

      this._filterCacheKey = key;
      this._filterCacheVal = rows;
      return rows;
    },

    // --- KPI hesaplama (computed) ---
    get topModel() {
      return this.filteredModels[0] || null;
    },
    get kFit() {
      if (!this.filteredModels.length) return '-';
      return Math.max(...this.filteredModels.map(x => x.fitScore || 0));
    },
    get useCases() {
      return new Set(this.history.map(h => h.use_case).filter(Boolean)).size;
    },

    // --- Karar asistanı (Bölüm 5, Kriter #8) ---
    // Kullanıcı bir use-case seçer, sistem:
    //   1. O use-case'e uygun modelleri filtreler
    //   2. Tier Tam Uyumlu/Sınırda olanları öne çıkarır
    //   3. En yüksek fit'li 1 modeli "Önerilen", 2 alternatif gösterir
    //   4. Tek satır gerekçe yazar
    decisionUseCase: 'coding',  // coding/chat/longcontext/research

    get decisionCandidates() {
      // use-case'e göre filtrele. llmfit 'useCase' serbest metin doner
      // ("Instruction following, chat" gibi), bu yüzden alt-dize eslesmesi kullaniriz.
      const keywords = {
        coding: ['cod', 'codeqwen', 'deepseek-coder', 'starcoder'],
        chat: ['chat', 'instruct', 'conversation', 'dialogue'],
        longcontext: [],  // context_length_supported >= 65536 olanlari secer
        research: ['instruct', 'llama', 'qwen', 'mistral', 'gemma'],
      };
      const kws = keywords[this.decisionUseCase] || [];
      const useCaseFilter = (m) => {
        if (this.decisionUseCase === 'longcontext') {
          return (m.context_length_supported || 0) >= 65536;
        }
        const txt = ((m.name || '') + ' ' + (m.useCase || '') + ' ' + (m.notes || '')).toLowerCase();
        return kws.some(k => txt.includes(k));
      };
      const candidates = this.latest.filter(useCaseFilter).map(m => {
        const t = this.tierOf(m);
        return { model: m, tier: t.tier, tone: t.tone, vram_margin: t.vram_margin_gb };
      });
      // Tier sirasi: Tam Uyumlu once, sonra Sinirda, sonra Dikkatli, sonra Uygun Degil
      const tierOrder = { 'Tam Uyumlu': 0, 'Uyumlu (Sınırda)': 1, 'Dikkatli Kullan': 2, 'Uygun Değil': 3 };
      // Önce tier sirala, sonra hibrit fit (fitScore + family_score boost — Sprint 21)
      candidates.sort((a, b) => {
        const ta = tierOrder[a.tier] ?? 9;
        const tb = tierOrder[b.tier] ?? 9;
        if (ta !== tb) return ta - tb;
        return (this._hybridFit(b.model) || 0) - (this._hybridFit(a.model) || 0);
      });
      // İlk 3'ü al: 1 öneri + 2 alternatif
      return candidates.slice(0, 3);
    },

    /** Sprint 21: fitScore + family_score hibrit (aile verisi varsa %30 ağırlık). */
    _hybridFit(m) {
      const base = m.fitScore || 0;
      const fam = m.family_score;
      if (fam == null) return base;
      return base + fam * 0.3;
    },

    /** Sprint 23 G4: benchmark kaynak rozeti (real/community/estimate ayrımı). */
    benchmarkSourceLabel(source) {
      void this.lang;
      if (source === 'real') return window.t ? window.t('source.local') : 'GERÇEK YEREL ÖLÇÜM';
      if (source === 'community') return window.t ? window.t('source.community') : 'TOPLULUK ÖLÇÜMÜ';
      return window.t ? window.t('source.predicted') : 'TAHMİN';
    },

    get decisionRecommended() {
      return this.decisionCandidatesHybrid[0] || null;
    },

    get decisionAlternatives() {
      return this.decisionCandidatesHybrid.slice(1, 3);
    },

    get decisionReason() {
      void this.lang;
      const rec = this.decisionRecommended;
      if (!rec) return window.t ? window.t('decision.noCandidate') : 'Bu kategori için uygun model bulunamadı.';
      const ucLabel = {
        general: 'decision.useCases.general',
        coding: 'decision.useCases.coding',
        reasoning: 'decision.useCases.reasoning',
        chat: 'decision.useCases.chat',
        multimodal: 'decision.useCases.multimodal',
        embedding: 'decision.useCases.embedding',
        longcontext: 'decision.useCases.longctx',
        research: 'decision.useCases.research',
      }[this.decisionUseCase] || 'decision.useCases.fallback';
      const score = rec.model.fitScore || rec.model.score || '?';
      const vramPay = rec.vram_margin != null
        ? (window.t ? window.t('decision.vramMargin', { margin: rec.vram_margin.toFixed(1) }) : `VRAM'inde ${rec.vram_margin.toFixed(1)} GB pay bırakıyor`)
        : (window.t ? window.t('decision.vramFit') : 'donanımında rahatça çalışıyor');
      const source = rec.fromLlmfit
        ? (window.t ? window.t('decision.source.llmfit') : 'benchcompass ağırlıklandırmasıyla')
        : (window.t ? window.t('decision.source.client') : 'client-side filtreyle');
      const tier = window.tierT ? window.tierT(rec.tier) : rec.tier;
      if (window.t) {
        return window.t('decision.reason', {
          name: rec.model.name, ucLabel: window.t(ucLabel), source,
          score, vramPay, tier,
        });
      }
      return `${rec.model.name}, ${ucLabel} için ${source} en yüksek skora (${score}) sahip ve ${vramPay}. Tier: ${rec.tier}.`;
    },

    // --- Preset'ler (Bölüm 4) ---
    applyPreset(name) {
      if (name === 'coding') {
        this.useFilter = 'coding';
        this.onlyCompatible = true;
        this.sortBy = 'fit';
        this.search = '';
      } else if (name === 'chat') {
        this.useFilter = 'chat';
        this.onlyCompatible = true;
        this.sortBy = 'fit';
        this.search = '';
      } else if (name === 'lightest') {
        this.useFilter = 'all';
        this.onlyCompatible = true;
        this.sortBy = 'vram';
        this.search = '';
      }
      this._saveFilterState();
      this._addActivity('Preset uygulandi: ' + name);
    },

    get presetResults() {
      // "X için en iyi 5" preset'leri için kullanılır (her preset 5'e kadar)
      // Aslında filtre uygulanır, gösterim filteredModels ile aynı; bu getter
      // sayaç amacıyla kullanılabilir.
      return this.filteredModels.slice(0, 5);
    },

    // --- Snapshot ---
    async saveSnapshot() {
      const name = (this.snapshotName || '').trim() || (this._autoSnapshotName());
      try {
        const r = await fetch(this.apiBase + '/api/dashboard/snapshot', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name }),
        });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const data = await r.json();
        this.snapshotMsg = `Snapshot yazıldı: run_id=${data.run_id}, ${data.copied_models} model kopyalandı.`;
        this.log('apiLog', 'Snapshot yazıldı: ' + JSON.stringify(data));
        this._addActivity('Snapshot: ' + name);
        this.toast('Snapshot Kaydedildi', `${name} (${data.copied_models} model) kalıcı DB'ye yazıldı.`, 'success', 4000);
        this.snapshotName = '';
        await this.refreshFromDb();
      } catch (err) {
        this.snapshotMsg = 'Snapshot hatası: ' + err.message;
        this.log('apiLog', 'Snapshot hatası: ' + err.message);
        this.toast('Snapshot Hatası', err.message, 'error', 5000);
      }
    },

    _autoSnapshotName() {
      const d = new Date();
      const p = n => String(n).padStart(2, '0');
      return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}-${p(d.getHours())}:${p(d.getMinutes())}`;
    },

    // --- History karşılaştırma ---
    runCompare() {
      const a = this.history[this.compareA];
      const b = this.history[this.compareB];
      if (!a || !b) { this.compareResult = []; return; }
      // Sprint 5: model kayıtlarını fit ile birlikte yapısal alanlarıyla sakla
      // (tier-diff hesabı için computeTier gerekli)
      const ma = Object.fromEntries((a.models || []).map(m => [m.name, m]));
      const mb = Object.fromEntries((b.models || []).map(m => [m.name, m]));
      const names = [...new Set([...Object.keys(ma), ...Object.keys(mb)])].sort();
      this.compareResult = names.map(n => {
        const am = ma[n];
        const bm = mb[n];
        const av = am?.fitScore ?? null;
        const bv = bm?.fitScore ?? null;
        const diff = (av != null && bv != null) ? bv - av : null;
        // Sprint 5: tier-diff hesabı (Kriter #9). Donanim profili ayniysa
        // tier farki, model ozelliklerinin farkindan gelir (ornegin backfill
        // sonrasi required_vram_gb guncellenmisse).
        let tierA = null, tierB = null, tierDiff = null, tierDiffDir = 'same';
        if (am) tierA = computeTier(am, this.hardware, this.thresholds).tier;
        if (bm) tierB = computeTier(bm, this.hardware, this.thresholds).tier;
        if (tierA && tierB) {
          const order = { 'Tam Uyumlu': 0, 'Uyumlu (Sınırda)': 1, 'Dikkatli Kullan': 2, 'Uygun Değil': 3 };
          const oa = order[tierA] ?? 9;
          const ob = order[tierB] ?? 9;
          if (ob < oa) { tierDiffDir = 'up'; tierDiff = `${tierA} → ${tierB}`; }
          else if (ob > oa) { tierDiffDir = 'down'; tierDiff = `${tierA} → ${tierB}`; }
          else { tierDiffDir = 'same'; tierDiff = '—'; }
        }
        return { name: n, a: av, b: bv, diff, tierA, tierB, tierDiff, tierDiffDir };
      });
    },

    loadRun(idx) {
      const run = this.history[idx];
      if (!run) return;
      this.latest = (run.models || []).map(m => ({
        name: m.name,
        provider: run.source || 'db',
        useCase: run.use_case || 'unknown',
        fitScore: m.fitScore || 0,
        contextWindow: m.contextWindow || 0,
        notes: 'DB run yüklemesi',
        // yapısal alanlar (varsa)
        required_vram_gb: m.required_vram_gb,
        required_ram_gb: m.required_ram_gb,
        quantization: m.quantization,
        param_count_b: m.param_count_b,
        context_length_supported: m.context_length_supported,
        context_length_estimated_at: m.context_length_estimated_at,
        estimated_speed_tok_s: m.estimated_speed_tok_s,
      }));
      this.source = 'db-run: ' + (run.name || run.id);
      this.toast('Geçmiş Run Yüklendi', `${run.name || ('run-' + run.id)} tablolara aktarıldı.`, 'info', 3000);
    },

    // --- Sprint 17: History toplu/seçerek silme ---
    get allHistorySelected() {
      return this.history.length > 0 && this.selectedHistoryIds.length === this.history.length;
    },

    toggleHistorySelect(id) {
      const idx = this.selectedHistoryIds.indexOf(id);
      if (idx >= 0) this.selectedHistoryIds.splice(idx, 1);
      else this.selectedHistoryIds.push(id);
      this.historyDeleteMsg = '';
    },

    toggleSelectAllHistory() {
      this.selectedHistoryIds = this.allHistorySelected ? [] : this.history.map(r => r.id).filter(Boolean);
      this.historyDeleteMsg = '';
    },

    async deleteSelectedHistory() {
      const ids = this.selectedHistoryIds.filter(Boolean);
      if (!ids.length) return;
      const names = this.history.filter(r => ids.includes(r.id)).map(r => r.name || ('run-' + r.id)).slice(0, 3).join(', ');
      const more = ids.length > 3 ? (window.t ? window.t('dialog.andMoreRuns', { count: ids.length - 3 }) : ` ve ${ids.length - 3} run daha`) : '';
      if (!confirm(window.t ? window.t('dialog.deleteSelected', { count: ids.length, names, more }) : `Seçilen ${ids.length} run silinsin mi?\n${names}${more}`)) return;
      try {
        const r = await fetch(this.apiBase + '/api/dashboard/history', {
          method: 'DELETE',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ run_ids: ids }),
        });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const data = await r.json();
        this.selectedHistoryIds = [];
        this.historyDeleteMsg = `${data.deleted} run silindi.`;
        this._addActivity(`${data.deleted} run silindi (seçerek)`);
        await this.refreshFromDb();
      } catch (e) {
        this.historyDeleteMsg = (window.t ? window.t('toast.deleteError') : 'Silme Hatası') + ': ' + e.message;
        this.toast(window.t ? window.t('toast.deleteError') : 'Silme Hatası', e.message, 'error', 5000);
      }
    },

    async deleteAllHistory() {
      if (!this.history.length) return;
      if (!confirm(window.t ? window.t('confirm.deleteAllHistory', { count: this.history.length }) : `TÜM history (${this.history.length} run) silinsin mi? Bu işlem geri alınamaz!`)) return;
      try {
        const r = await fetch(this.apiBase + '/api/dashboard/history', {
          method: 'DELETE',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ all: true }),
        });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const data = await r.json();
        this.selectedHistoryIds = [];
        this.historyDeleteMsg = `${data.deleted} run silindi (tümü).`;
        this._addActivity(`${data.deleted} run silindi (tümü)`);
        await this.refreshFromDb();
      } catch (e) {
        this.historyDeleteMsg = (window.t ? window.t('toast.deleteError') : 'Silme Hatası') + ': ' + e.message;
        this.toast(window.t ? window.t('toast.deleteError') : 'Silme Hatası', e.message, 'error', 5000);
      }
    },

    // --- Collector kontrolü ---
    async collectorStatus() {
      try {
        const data = await this.getJson(this.collectorBase + '/health');
        this.collectorInfo = 'Collector erişilebilir.';
        this.log('collectorLog', 'Health: ' + JSON.stringify(data));
      } catch (err) {
        this.collectorInfo = 'Collector erişilemedi.';
        this.log('collectorLog', 'Health hatası: ' + err.message);
      }
    },

    async collectorRun() {
      try {
        const r = await fetch(this.collectorBase + '/api/collector/run', { method: 'POST' });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const data = await r.json();
        this.collectorInfo = 'Collector run tamamlandı.';
        this.log('collectorLog', 'Manual run: ' + JSON.stringify(data));
        await this.refreshFromDb();
      } catch (err) {
        this.collectorInfo = 'Collector run başarısız.';
        this.log('collectorLog', 'Run hatası: ' + err.message);
      }
    },

    async collectorLatest() {
      try {
        const data = await this.getJson(this.collectorBase + '/api/dashboard/history');
        this.jsonOutput = JSON.stringify(data, null, 2);
        this.log('collectorLog', 'Latest history çekildi: ' + (data.history?.length || 0) + ' run');
      } catch (err) {
        this.log('collectorLog', 'History hatası: ' + err.message);
      }
    },

    // --- Yardımcılar ---
    log(id, msg) {
      const stamp = new Date().toLocaleTimeString('tr-TR');
      const line = `\n[${stamp}] ${msg}`;
      if (id === 'apiLog') this.apiLog += line;
      else if (id === 'collectorLog') this.collectorLog += line;
      this.lastLog = `[${stamp}] ${msg}`;
    },

    esc, ctx, shortModelName, renderNotesParts,

    // --- Tema ---
    theme: 'dark',
    applyTheme() {
      document.documentElement.setAttribute('data-theme', this.theme);
    },
    toggleTheme() {
      this.theme = this.theme === 'dark' ? 'light' : 'dark';
      this.applyTheme();
      localStorage.setItem('benchcompass-theme', this.theme);
    },
    get themeIcon() { return this.theme === 'dark' ? '☀️' : '🌙'; },

    // --- Dil (i18n, ADR-0009) ---
    getLang() { void this.lang; return this.lang; },
    // Alpine reaktivitesi: this.lang'e dokunarak x-text/x-title ifadelerinin
    // dil değişiminde yeniden değerlendirilmesini sağlar (yoksa sabit kalır).
    t(key, vars = {}) {
      void this.lang;
      return window.t ? window.t(key, vars) : key;
    },
    tierT(tier) {
      void this.lang;
      return window.tierT ? window.tierT(tier) : tier;
    },
    tierShortT(tier) {
      void this.lang;
      return window.tierShortT ? window.tierShortT(tier) : tier;
    },
    toggleLangBtn() {
      const next = window.toggleLang ? window.toggleLang() : 'tr';
      this.lang = next;
      // Sayfa başlığını dil ile senkronize et
      if (document && document.title) {
        document.title = window.t ? window.t('app.title') : 'BenchCompass';
      }
      if (this.$nextTick) {
        this.$nextTick(() => { if (this.view === 'charts') this.renderCharts(); });
      } else if (this.view === 'charts') {
        this.renderCharts();
      }
    },

    // --- Sprint 6 Ekstra 1: CSV/JSON export ---
    exportData(format) {
      const rows = this.filteredModels.map(m => {
        const t = this.tierOf(m);
        return {
          name: m.name,
          provider: m.provider || '',
          useCase: m.useCase || '',
          fitScore: m.fitScore || 0,
          tier: t.tier,
          vram_margin_gb: t.vram_margin_gb,
          ram_margin_gb: t.ram_margin_gb,
          required_vram_gb: m.required_vram_gb,
          required_ram_gb: m.required_ram_gb,
          quantization: m.quantization || '',
          param_count_b: m.param_count_b,
          context_length_supported: m.context_length_supported,
          context_length_estimated_at: m.context_length_estimated_at,
          estimated_speed_tok_s: m.estimated_speed_tok_s,
          contextWindow: m.contextWindow,
        };
      });

      const hardwareInfo = {
        device: this.hardware.device_name,
        vram_gb: this.hardware.vram_gb,
        ram_gb: this.hardware.ram_gb,
        gpu: this.hardware.gpu,
        exported_at: new Date().toISOString(),
      };

      let blob, filename;
      if (format === 'csv') {
        const cols = Object.keys(rows[0] || { name: '' });
        const csv = [
          '# ' + Object.entries(hardwareInfo).map(([k, v]) => k + '=' + v).join(' '),
          cols.join(','),
          ...rows.map(r => cols.map(c => {
            const v = r[c];
            if (v == null) return '';
            const s = String(v);
            return /[,"\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
          }).join(',')),
        ].join('\n');
        blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
        filename = 'benchcompass-export-' + new Date().toISOString().slice(0, 10) + '.csv';
      } else {
        const data = { hardware: hardwareInfo, models: rows };
        blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        filename = 'benchcompass-export-' + new Date().toISOString().slice(0, 10) + '.json';
      }
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      this.toast(window.t ? window.t('toast.export') : 'Export', window.t ? window.t('toast.exportDone', { count: rows.length, format: format.toUpperCase(), filename }) : `${rows.length} model ${format.toUpperCase()} olarak dışa aktarıldı: ${filename}`, 'success');
      this._addActivity(rows.length + ' model ' + format.toUpperCase() + ' export');
    },

    // --- Sprint 6 Ekstra 2: Toast bildirimleri ---
    toasts: [],
    _toastId: 0,
    toast(title, message, kind = 'info', ttl = 4000) {
      const id = ++this._toastId;
      this.toasts.push({ id, title, message, kind });
      setTimeout(() => { this.dismissToast(id); }, ttl);
    },
    dismissToast(id) {
      this.toasts = this.toasts.filter(t => t.id !== id);
    },

    // --- Sprint 6 Ekstra 2: "Model uyumlu hale geldi" bildirimi ---
    // refreshFromDb sonrası önceki snapshot ile karşılaştır; tier yükseldiyse
    // toast göster.
    _previousTierByModel: {},
    _checkCompatibilityImprovements() {
      const improvements = [];
      for (const m of this.latest) {
        const tier = this.tierOf(m).tier;
        const prev = this._previousTierByModel[m.name];
        if (prev && prev !== tier) {
          const order = { 'Tam Uyumlu': 0, 'Uyumlu (Sınırda)': 1, 'Dikkatli Kullan': 2, 'Uygun Değil': 3 };
          if ((order[tier] ?? 9) < (order[prev] ?? 9)) {
            improvements.push({ name: m.name, from: prev, to: tier });
          }
        }
      }
      // Snapshot'ı güncelle
      const next = {};
      for (const m of this.latest) next[m.name] = this.tierOf(m).tier;
      this._previousTierByModel = next;

      // İlk yüklemede bildirim yapma (sadece _previousTierByModel zaten dolu ise)
      if (improvements.length === 0) return;
      const top = improvements.slice(0, 3);
      const title = window.t
        ? (improvements.length === 1 ? window.t('toast.compatImproved') : window.t('toast.compatImprovedN', { count: improvements.length }))
        : (improvements.length === 1 ? '✓ Model uyumluluğu iyileşti' : `✓ ${improvements.length} model uyumluluğu iyileşti`);
      const msg = top.map(i => `${shortModelName(i.name)}: ${window.tierT ? window.tierT(i.from) : i.from} → ${window.tierT ? window.tierT(i.to) : i.to}`).join('\n') +
                  (improvements.length > 3 ? (window.t ? '\n' + window.t('toast.andMoreModels', { count: improvements.length - 3 }) : `\n…ve ${improvements.length - 3} model daha`) : '');
      this.toast(title, msg, 'success', 6000);
    },

    // ========================================================================
    // Sprint 8 — llmfit proxy entegrasyonu
    // ========================================================================

    // --- Özellik A: Model Detay Modalı (llmfit info) ---
    async showModelDetail(modelName) {
      this.modelDetailOpen = true;
      this.modelDetailLoading = true;
      this.modelDetailError = '';
      this.modelDetail = null;
      try {
        const r = await fetch(this.apiBase + '/api/benchcompass/info/' + encodeURIComponent(modelName));
        const data = await r.json();
        if (!r.ok || data.error) {
          throw new Error(data.error || ('HTTP ' + r.status));
        }
        // llmfit info {models: [tek model], system: {...}}
        const m = (data.models || [])[0] || null;
        this.modelDetail = m;
        // Radar grafiğini bir sonraki tick'te çiz (DOM hazır olsun)
        this.$nextTick(() => this._renderScoreRadar(m));
      } catch (e) {
        this.modelDetailError = 'Detay alınamadı: ' + e.message;
        this.toast(window.t ? window.t('toast.modelDetailError') : 'Model Detay Hatası', e.message, 'error', 6000);
      } finally {
        this.modelDetailLoading = false;
      }
    },

    closeModelDetail() {
      this.modelDetailOpen = false;
      if (this.charts.scoreRadar) {
        try { this.charts.scoreRadar.destroy(); } catch (err) { console.debug(err); }
        this.charts.scoreRadar = null;
      }
    },

    _renderScoreRadar(model) {
      if (!model || !model.score_components) return;
      const el = document.getElementById('scoreRadarChart');
      if (!el) return;
      const sc = model.score_components;
      const css = getComputedStyle(document.documentElement);
      const C = {
        primary: css.getPropertyValue('--primary').trim() || '#4f98a3',
        success: css.getPropertyValue('--success').trim() || '#6daa45',
      };
      if (this.charts.scoreRadar) {
        try { this.charts.scoreRadar.destroy(); } catch (err) { console.debug(err); }
      }
      this.charts.scoreRadar = new Chart(el, {
        type: 'radar',
        data: {
          labels: ['Fit', 'Quality', 'Speed', 'Context'],
          datasets: [{
            label: window.t ? window.t('chart.llmfitScores') : 'benchcompass skorları',
            data: [sc.fit || 0, sc.quality || 0, sc.speed || 0, sc.context || 0],
            backgroundColor: C.primary + '4d',
            borderColor: C.primary,
            borderWidth: 2,
            pointBackgroundColor: C.success,
            pointRadius: 4,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            r: {
              beginAtZero: true,
              max: 100,
              ticks: { stepSize: 25 },
              grid: { color: css.getPropertyValue('--border').trim() },
            },
          },
        },
      });
    },

    // --- Özellik B: Upgrade Simülatörü (llmfit plan) ---
    async runSimulation() {
      this.simLoading = true;
      this.simError = '';
      this.simResults = [];
      // Top-10 modeli al
      const topModels = this.filteredModels.slice(0, 10);
      try {
        const results = [];
        // 10 modeli paralel fetch et (async.all benzeri)
        const promises = topModels.map(async m => {
          try {
            const r = await fetch(this.apiBase + '/api/benchcompass/plan', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                model: m.name,
                context: this.simContext,
                memory_gb: this.simRam,
                vram_gb: this.simVram,
              }),
            });
            const d = await r.json();
            if (!r.ok || d.error) return { model: m.name, error: d.error || ('HTTP ' + r.status) };
            // GPU run_path'ini al (genelde en iyisi)
            const gpuPath = (d.run_paths || []).find(p => p.path === 'gpu') || (d.run_paths || [])[0];
            return {
              model: m.name,
              fit_level: gpuPath?.fit_level || d.fit_level || '?',
              estimated_tps: gpuPath?.estimated_tps || d.estimated_tps,
              feasible: gpuPath?.feasible ?? true,
              minimum_vram: d.minimum?.vram_gb,
              recommended_vram: d.recommended?.vram_gb,
            };
          } catch (e) {
            return { model: m.name, error: e.message };
          }
        });
        const all = await Promise.all(promises);
        this.simResults = all;
      } catch (e) {
        this.simError = 'Simülasyon hatası: ' + e.message;
        this.toast(window.t ? window.t('toast.simulationError') : 'Simülasyon Hatası', e.message, 'error', 6000);
      } finally {
        this.simLoading = false;
      }
    },

    get simVramDelta() {
      return (this.simVram - (this.hardware.vram_gb || 0)).toFixed(1);
    },
    get simRamDelta() {
      return (this.simRam - (this.hardware.ram_gb || 0)).toFixed(1);
    },

    // --- Özellik C: Otomatik Donanım Tespiti (llmfit system) ---
    async autoDetectHardware() {
      try {
        const r = await fetch(this.apiBase + '/api/hardware/autodetect', { method: 'POST' });
        const data = await r.json();
        if (!r.ok || data.error) throw new Error(data.error || ('HTTP ' + r.status));
        // Config'i yeniden çek ve state'e uygula
        const hw = await this.getJson(this.apiBase + '/api/hardware');
        this.applyHardwareConfig(hw);
        this.settingsMsg = window.t ? window.t('dialog.settingsMsg.autoDetected', { gpu: data.detected.gpu || '', vram: data.detected.vram_gb }) : '✓ Donanım llmfit\'ten otomatik algılandı: ' + (data.detected.gpu || '') + ' (' + data.detected.vram_gb + ' GB VRAM)';
        this.toast(window.t ? window.t('toast.autoDetect') : 'Otomatik Tespit', window.t ? window.t('toast.autoDetectDone', { device: data.detected.device_name }) : 'Donanım profili güncellendi: ' + data.detected.device_name, 'success', 5000);
        setTimeout(() => { this.settingsMsg = ''; }, 5000);
      } catch (e) {
        this.settingsMsg = (window.t ? window.t('toast.autoDetectError') : 'Otomatik tespit hatası') + ': ' + e.message;
        this.toast(window.t ? window.t('toast.autoDetectError') : 'Otomatik Tespit Hatası', e.message, 'error', 6000);
      }
    },

    // --- Özellik D: Karar Asistanı (llmfit recommend) ---
    get decisionUseCases() {
      return [
        { id: 'general', label: '🎯 Genel amaçlı' },
        { id: 'coding', label: '💻 Kodlama' },
        { id: 'reasoning', label: '🧠 Akıl yürütme' },
        { id: 'chat', label: '💬 Sohbet' },
        { id: 'multimodal', label: '👁️ Multimodal (görüntü)' },
        { id: 'embedding', label: '📚 Embedding (RAG)' },
      ];
    },

    async loadRecommendFromLlmfit() {
      // llmfit recommend çağır, karar asistanına llmfit'in gerçek ağırlıklandırmasını besle
      this.recommendLoading = true;
      try {
        const r = await fetch(this.apiBase + '/api/recommend?use_case=' + this.decisionUseCase + '&limit=10&min_fit=runnable');
        const data = await r.json();
        if (!r.ok || data.error) throw new Error(data.error || ('HTTP ' + r.status));
        this.recommendData = data;
        this.toast(window.t ? window.t('toast.recommend') : 'benchcompass Tavsiyesi', window.t ? window.t('toast.recommendDone', { uc: this.decisionUseCase, count: data.models?.length || 0 }) : 'use-case \'' + this.decisionUseCase + '\' için ' + (data.models?.length || 0) + ' model geldi', 'success', 4000);
      } catch (e) {
        this.toast(window.t ? window.t('toast.recommendError') : 'benchcompass Tavsiye Hatası', e.message, 'error', 6000);
      } finally {
        this.recommendLoading = false;
      }
    },

    async loadBaseline(modelName) {
      // Sprint 21: frontier baseline karşılaştırması (/api/fit/baseline)
      this.baselineLoading = true;
      this.baselineData = null;
      this.baselineError = '';
      try {
        const r = await fetch(this.apiBase + '/api/fit/baseline?model=' + encodeURIComponent(modelName || '') + '&role=' + encodeURIComponent(this.decisionUseCase));
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const data = await r.json();
        if (data.error) throw new Error(data.error);
        this.baselineData = data;
      } catch (e) {
        this.baselineError = e.message;
      } finally {
        this.baselineLoading = false;
      }
    },

    // decisionCandidates'i llmfit recommend ile zenginleştir
    get decisionCandidatesHybrid() {
      // Önce llmfit recommend verisi varsa onu kullan (daha doğru)
      if (this.recommendData?.models?.length) {
        const tierOrder = { 'Tam Uyumlu': 0, 'Uyumlu (Sınırda)': 1, 'Dikkatli Kullan': 2, 'Uygun Değil': 3 };
        return this.recommendData.models.slice(0, 10).map(m => {
          // llmfit modelini bizim tier sistemine çevir
          const fakeModel = {
            name: m.name,
            required_vram_gb: m.memory_required_gb,
            required_ram_gb: null,
            notes: m.notes,
          };
          const t = this.tierOf(fakeModel);
          return { model: m, tier: t.tier, tone: t.tone, vram_margin: t.vram_margin_gb, fromLlmfit: true };
        }).sort((a, b) => (tierOrder[a.tier] ?? 9) - (tierOrder[b.tier] ?? 9)).slice(0, 3);
      }
      // Yoksa mevcut client-side mantık
      return this.decisionCandidates.map(c => ({ ...c, fromLlmfit: false }));
    },

    // --- Özellik E: Model Karşılaştırma (llmfit diff) ---
    toggleDiffCandidate(modelName) {
      const idx = this.diffCandidates.indexOf(modelName);
      if (idx >= 0) {
        this.diffCandidates.splice(idx, 1);
      } else {
        if (this.diffCandidates.length >= 2) this.diffCandidates.shift();
        this.diffCandidates.push(modelName);
      }
    },

    async runDiff() {
      if (this.diffCandidates.length !== 2) return;
      this.diffLoading = true;
      this.diffError = '';
      this.diffData = null;
      this.diffOpen = true;
      try {
        const r = await fetch(this.apiBase + '/api/benchcompass/diff?a=' + encodeURIComponent(this.diffCandidates[0]) + '&b=' + encodeURIComponent(this.diffCandidates[1]));
        const data = await r.json();
        if (!r.ok || data.error) throw new Error(data.error || ('HTTP ' + r.status));
        this.diffData = data;
      } catch (e) {
        this.diffError = (window.t ? window.t('diffError') : 'Karşılaştırma hatası') + ': ' + e.message;
        this.toast(window.t ? window.t('toast.diffError') : 'Diff Hatası', e.message, 'error', 6000);
      } finally {
        this.diffLoading = false;
      }
    },

    closeDiff() {
      this.diffOpen = false;
    },

    // diff tablosu için karşılaştırma satırları üretir
    get diffRows() {
      void this.lang;
      if (!this.diffData?.models || this.diffData.models.length < 2) return [];
      const a = this.diffData.models[0];
      const b = this.diffData.models[1];
      const m = (mod) => mod.model || mod;
      const ma = m(a), mb = m(b);
      const L = (k) => window.t ? window.t('diff.' + k) : null;
      const yes = window.t ? window.t('yes') : 'Evet';
      const no = window.t ? window.t('no') : 'Hayır';
      const rows = [
        { label: L('score') || 'Skor', a: ma.score, b: mb.score, higher: 'b' },
        { label: L('fitLevel') || 'Fit seviyesi', a: a.fit_level || ma.fit_level, b: b.fit_level || mb.fit_level },
        { label: L('params') || 'Parametre (B)', a: ma.params_b || ma.parameter_count, b: mb.params_b || mb.parameter_count, higher: 'b' },
        { label: L('vram') || 'Gerekli VRAM (GB)', a: ma.memory_required_gb || a.memory_required_gb, b: mb.memory_required_gb || b.memory_required_gb, higher: 'a' },
        { label: L('speed') || 'Tahmini hız (tok/s)', a: ma.estimated_tps || a.estimated_tps, b: mb.estimated_tps || b.estimated_tps, higher: 'b' },
        { label: L('context') || 'Context (tokens)', a: ma.context_length, b: mb.context_length, higher: 'b' },
        { label: L('disk') || 'Disk (GB)', a: ma.disk_size_gb, b: mb.disk_size_gb, higher: 'a' },
        { label: L('quant') || 'Quantizasyon', a: ma.best_quant || ma.quantization, b: mb.best_quant || mb.quantization },
        { label: L('moe') || 'MoE', a: ma.is_moe ? yes : no, b: mb.is_moe ? yes : no },
      ];
      return rows.filter(r => r.a != null || r.b != null);
    },

    // ========================================================================
    // Sprint 9 — Benchmark + Magaza
    // ========================================================================

    // --- Benchmark ---
    async startBenchmark() {
      this.benchmarkLoading = true;
      this.benchmarkResult = null;
      try {
        const r = await fetch(this.apiBase + '/api/benchmark', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            model: this.benchmarkModel,
            provider: this.benchmarkProvider,
            share: this.benchmarkShare,
          }),
        });
        const data = await r.json();
        if (!r.ok || data.error) throw new Error(data.error || ('HTTP ' + r.status));
        this.benchmarkTaskId = data.task_uuid;
        this.toast(window.t ? window.t('toast.benchmark') : 'Benchmark', window.t ? window.t('toast.benchmarkStarted', { model: this.benchmarkModel }) : 'Benchmark başlatıldı: ' + this.benchmarkModel, 'info', 3000);
        // Polling baslat
        this._pollBenchmark();
      } catch (e) {
        this.toast(window.t ? window.t('toast.benchmarkError') : 'Benchmark Hatası', e.message, 'error', 6000);
        this.benchmarkLoading = false;
      }
    },

    /** Adım 4: eşzamanlılık stresi — POST /api/benchmark/concurrent. */
    async startConcurrentStress() {
      this.concurrentLoading = true;
      this.concurrentResults = null;
      this.concurrentError = '';
      const backend = this.benchmarkProvider === 'auto' ? 'lmstudio' : this.benchmarkProvider;
      try {
        const r = await fetch(this.apiBase + '/api/benchmark/concurrent', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            model: this.benchmarkModel,
            backend,
            levels: [1, 2, 4, 8],
          }),
        });
        const data = await r.json();
        if (!r.ok || data.ok === false) throw new Error(data.error || ('HTTP ' + r.status));
        this.concurrentResults = data.results || [];
      } catch (e) {
        this.concurrentResults = null;
        this.concurrentError = (e && e.message) || String(e);
      } finally {
        this.concurrentLoading = false;
      }
    },

    /** Adım 5: interconnect simülasyonu — GET /api/compat/simulate. */
    async loadInterconnectSim() {
      this.interconnectLoading = true;
      this.interconnectResult = null;
      this.interconnectError = '';
      try {
        const q = new URLSearchParams({
          param_count_b: '8.0',
          quant: 'Q4_K_M',
          context_length: '4096',
          vram_gb: '12.0',
          ram_gb: '32.0',
          gpu_count: String(this.interconnectGpuCount || 1),
          interconnect: this.interconnectType || 'single',
        });
        const r = await fetch(this.apiBase + '/api/compat/simulate?' + q.toString());
        const data = await r.json();
        if (!r.ok) throw new Error(data.error || ('HTTP ' + r.status));
        this.interconnectResult = data;
      } catch (e) {
        this.interconnectError = (e && e.message) || String(e);
      } finally {
        this.interconnectLoading = false;
      }
    },

    /** Adım 6: red-team planı + grade — /api/eval/redteam-plan, /api/eval/redteam/grade. */
    async loadRedteamPlan() {
      this.redteamLoading = true;
      this.redteamError = '';
      try {
        const r = await fetch(this.apiBase + '/api/eval/redteam-plan');
        const data = await r.json();
        if (!r.ok) throw new Error(data.error || data.detail || ('HTTP ' + r.status));
        this.redteamTasks = data.tasks || [];
        if (!this.redteamTaskId && this.redteamTasks.length) this.redteamTaskId = this.redteamTasks[0].id;
      } catch (e) {
        this.redteamError = (e && e.message) || String(e);
      } finally {
        this.redteamLoading = false;
      }
    },

    async gradeRedteam() {
      this.redteamLoading = true;
      this.redteamResult = null;
      this.redteamError = '';
      try {
        const r = await fetch(this.apiBase + '/api/eval/redteam/grade', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ task_id: this.redteamTaskId, response: this.redteamResponse }),
        });
        const data = await r.json();
        if (!r.ok) throw new Error(data.error || data.detail || ('HTTP ' + r.status));
        this.redteamResult = data;
      } catch (e) {
        this.redteamError = (e && e.message) || String(e);
      } finally {
        this.redteamLoading = false;
      }
    },

    async _pollBenchmark() {
      if (!this.benchmarkTaskId) { this.benchmarkLoading = false; return; }
      try {
        const r = await fetch(this.apiBase + '/api/tasks/' + this.benchmarkTaskId);
        const data = await r.json();
        if (data.status === 'completed') {
          this.benchmarkResult = data.result;
          this.benchmarkLoading = false;
          this._refreshBenchmarkHistory();
          this.toast(window.t ? window.t('toast.benchmarkDone') : 'Benchmark Tamam', window.t ? window.t('toast.benchmarkMeasured', { tps: data.result.measured_tps }) : data.result.measured_tps + ' tok/s ölçüldü', 'success', 6000);
        } else if (data.status === 'failed') {
          this.toast(window.t ? window.t('toast.benchmarkFailed') : 'Benchmark Başarısız', data.error || (window.t ? window.t('toast.unknownError') : 'Bilinmeyen hata'), 'error', 6000);
          this.benchmarkLoading = false;
        } else {
          setTimeout(() => this._pollBenchmark(), 1500);
        }
      } catch (e) {
        this.benchmarkLoading = false;
      }
    },

    async _refreshBenchmarkHistory() {
      try {
        const r = await fetch(this.apiBase + '/api/benchmarks?limit=20');
        const data = await r.json();
        this.benchmarkHistory = data.benchmarks || [];
      } catch (err) { console.debug(err); }
    },

    // --- Magaza (yerel katalog + hf-search + download + run) ---
    async loadStoreProviders() {
      // Sprint 25: filtre select'i için provider listesi (/api/catalog).
      try {
        const r = await fetch(this.apiBase + '/api/catalog');
        const data = await r.json();
        this.storeProviders = (data.providers || []).slice(0, 50);
      } catch (e) {
        this.storeProviders = [];
      }
    },

    async searchStore() {
      if (!this.storeQuery.trim()) return;
      this.storeLoading = true;
      try {
        // Sprint 19: önce yerel katalog (ağ yok — hf_models.json)
        // Sprint 25: filtreler (provider/use_case/is_moe/min_ctx) backend'e iletilir
        const params = new URLSearchParams();
        params.set('q', this.storeQuery);
        params.set('limit', 20);
        if (this.storeProvider) params.set('provider', this.storeProvider);
        if (this.storeUseCase) params.set('use_case', this.storeUseCase);
        if (this.storeMoe) params.set('is_moe', 'true');
        if (this.storeMinCtx) params.set('min_ctx', String(this.storeMinCtx));
        const cr = await fetch(this.apiBase + '/api/catalog/search?' + params.toString());
        const cdata = await cr.json();
        const catalogModels = (cdata.models || []).map(m => ({
          repo: m.name,
          quant: m.quantization || 'Q4_K_M',
          size_gb: m.required_ram_gb || m.param_count_b ? null : null,
          compatible: true,
          source: 'local-catalog',
          name: m.name,
          required_vram_gb: m.required_vram_gb,
          context_window: m.context_window,
          is_moe: m.is_moe,
        }));
        if (catalogModels.length > 0) {
          this.storeResults = catalogModels;
          this.storeSource = 'local-catalog';
          this._addActivity('Yerel katalogdan ' + catalogModels.length + ' model bulundu');
          return;
        }
        // Yerel katalogda yoksa HF arama (ağ)
        this.storeSource = 'hf';
        const r = await fetch(this.apiBase + '/api/hf-search?query=' + encodeURIComponent(this.storeQuery) + '&limit=20');
        const data = await r.json();
        const models = data.models || [];
        if (models.length === 0) {
          this.storeResults = [];
          this.storeSource = 'none';
          this.toast(window.t ? window.t('toast.noResult') : 'Sonuç Yok', window.t ? window.t('toast.noResultMsg') : 'Yerel katalog ve HF\'de eşleşme bulunamadı.', 'info', 4000);
        } else {
          this.storeResults = models;
        }
      } catch (e) {
        this.toast(window.t ? window.t('toast.searchError') : 'Arama Hatası', e.message, 'error', 5000);
      } finally {
        this.storeLoading = false;
      }
    },

    async downloadModel(item) {
      const repo = item.repo || item.repo_id || item.model || item.name;
      item._downloading = true;
      try {
        const r = await fetch(this.apiBase + '/api/download', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ repo, quant: item.quant || 'Q4_K_M' }),
        });
        const data = await r.json();
        if (!r.ok || data.error) throw new Error(data.error || ('HTTP ' + r.status));
        this.toast(window.t ? window.t('toast.download') : 'İndirme', window.t ? window.t('toast.downloadingMsg', { model: repo.split('/')[1] }) : repo.split('/')[1] + ' indiriliyor (arka planda)', 'info', 4000);
        // Poll
        const poll = async () => {
          const t = await (await fetch(this.apiBase + '/api/tasks/' + data.task_uuid)).json();
          if (t.status === 'completed') {
            this._refreshDownloaded();
            this.toast(window.t ? window.t('toast.downloadDone') : 'İndirme Tamam', window.t ? window.t('toast.downloadedMsg', { model: repo.split('/')[1] }) : repo.split('/')[1] + ' indirildi', 'success', 5000);
          } else if (t.status === 'failed') {
            this.toast(window.t ? window.t('toast.downloadFailed') : 'İndirme Başarısız', t.error, 'error', 6000);
          } else { setTimeout(poll, 2000); }
        };
        setTimeout(poll, 1000);
      } catch (e) {
        this.toast(window.t ? window.t('toast.downloadError') : 'İndirme Hatası', e.message, 'error', 6000);
      } finally {
        item._downloading = false;
      }
    },

    async runModel(item) {
      const model = item.model || item.repo || item.name;
      try {
        const r = await fetch(this.apiBase + '/api/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model, port: 8080 }),
        });
        const data = await r.json();
        if (!r.ok || data.error) throw new Error(data.error || ('HTTP ' + r.status));
        this.toast(window.t ? window.t('toast.run') : 'Çalıştırma', window.t ? window.t('toast.runMsg', { model: model.split('/')[1] }) : model.split('/')[1] + ' başlatılıyor (mock)', 'info', 3000);
        setTimeout(() => this._refreshRunning(), 2000);
      } catch (e) {
        this.toast(window.t ? window.t('toast.runError') : 'Çalıştırma Hatası', e.message, 'error', 6000);
      }
    },

    async stopServer(pid) {
      try {
        await fetch(this.apiBase + '/api/run/stop', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pid }),
        });
        this.toast(window.t ? window.t('toast.stopped') : 'Durduruldu', window.t ? window.t('toast.stoppedMsg', { pid }) : 'Sunucu ' + pid + ' durduruldu', 'info', 3000);
        this._refreshRunning();
      } catch (e) {
        this.toast(window.t ? window.t('toast.stopError') : 'Durdurma Hatası', e.message, 'error', 5000);
      }
    },

    async _refreshDownloaded() {
      try {
        const r = await fetch(this.apiBase + '/api/downloaded');  // not implemented in mock
      } catch (err) { console.debug(err); }
    },

    async _refreshRunning() {
      try {
        const r = await fetch(this.apiBase + '/api/running-servers');
        const data = await r.json();
        this.runningServers = data.servers || [];
      } catch (err) { console.debug(err); }
    },

    // ========================================================================
    // Sprint 10 — Modellerim (Ollama yerel modeller)
    // ========================================================================

    async loadOllamaModels() {
      this.installedModelsLoading = true;
      this.installedModelsError = '';
      try {
        const [modelsRes, psRes] = await Promise.all([
          fetch(this.apiBase + '/api/ollama/models').then(r => r.json()).catch(() => ({ ok: false })),
          fetch(this.apiBase + '/api/ollama/ps').then(r => r.json()).catch(() => ({ ok: false })),
        ]);

        if (!modelsRes || !modelsRes.ok || modelsRes.error) {
          throw new Error(modelsRes?.error || 'Ollama servisine ulaşılamadı.');
        }

        const runningList = (psRes && psRes.ok && psRes.models) ? psRes.models : [];
        this.runningOllamaModels = runningList;

        const runningNames = new Set(runningList.map(r => r.name || r.model));

        this.installedModels = (modelsRes.models || []).map(m => {
          const isRunning = runningNames.has(m.name);
          const psInfo = runningList.find(r => r.name === m.name || r.model === m.name);
          return {
            ...m,
            is_running: isRunning,
            running_info: psInfo || null,
            _running_op: false,
            _stopping_op: false,
            _benchmarking: false,
          };
        });
      } catch (e) {
        this.installedModelsError = window.t ? window.t('ollama.unreachable') : 'Ollama servisine (http://localhost:11434) erişilemiyor veya model yüklenemedi. Lütfen terminalde "ollama serve" çalıştırın veya [ DEMO ] verisini kullanın.';
      } finally {
        this.installedModelsLoading = false;
      }
    },

    // Benchmark model girişinde mevcut Ollama modellerini listele (Sprint 27 sonrası)
    async ensureBenchmarkModels() {
      if (!this.installedModels.length && !this.installedModelsLoading) {
        await this.loadOllamaModels();
      }
    },

    async loadNormalizedScore(modelName, tps) {
      if (!modelName || !tps || tps <= 0) return null;
      try {
        const gpu = this.hardware?.gpu_name || '';
        const url = `${this.apiBase}/api/score/normalized?model=${encodeURIComponent(modelName)}&tps=${tps}&gpu=${encodeURIComponent(gpu)}`;
        const res = await fetch(url);
        if (res && res.ok) {
          const data = await res.json();
          return data && data.score != null ? data.score : null;
        }
      } catch (_) {
        // graceful degradation
      }
      return null;
    },

    async benchmarkOllamaModel(modelName) {
      const m = this.installedModels.find(x => x.name === modelName);
      if (!m) return;
      m._benchmarking = true;
      this.toast('Benchmark', modelName + ' için hız ölçümü başlatıldı...', 'info', 3000);
      try {
        const r = await fetch(this.apiBase + '/api/ollama/benchmark', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model: modelName, runs: 1 }),
        });
        const data = await r.json();
        if (!r.ok || data.error || data.ok === false) {
          const errMsg = data.error || ('HTTP ' + r.status);
          throw new Error(errMsg);
        }
        const tps = data.result?.measured_tps || 0;
        this.toast('Benchmark Tamamlandı', modelName + ' -> ' + tps + ' tok/s ölçüldü!', 'success', 5000);
        const classScore = await this.loadNormalizedScore(modelName, tps);
        m.benchmark = {
          measured_tps: tps,
          ttft_ms: data.result?.ttft_ms,
          ttft_method: data.result?.ttft_method || 'measured',
          source: data.result?.source || 'real',
          class_score: classScore,
        };
        await this.refreshFromDb();
      } catch (e) {
        this.toast('Benchmark Hatası', e.message, 'error', 6000);
      } finally {
        m._benchmarking = false;
      }
    },

    async benchmarkAllOllama() {
      this.benchmarkAllRunning = true;
      this.benchmarkAllProgress = 0;
      try {
        const r = await fetch(this.apiBase + '/api/ollama/benchmark-all', { method: 'POST' });
        const data = await r.json();
        if (!r.ok || data.error) throw new Error(data.error || ('HTTP ' + r.status));
        this.benchmarkAllTaskId = data.task_uuid;
        this.benchmarkAllTotal = data.total || 0;
        this.toast('Toplu Benchmark', 'Tüm yerel modeller sırayla test ediliyor...', 'info', 3000);
        this._pollBenchmarkAll();
      } catch (e) {
        this.toast('Toplu Benchmark Hatası', e.message, 'error', 6000);
        this.benchmarkAllRunning = false;
      }
    },

    async _pollBenchmarkAll() {
      if (!this.benchmarkAllTaskId) { this.benchmarkAllRunning = false; return; }
      try {
        const r = await fetch(this.apiBase + '/api/tasks/' + this.benchmarkAllTaskId);
        const data = await r.json();
        if (data.status === 'completed') {
          this.benchmarkAllRunning = false;
          this.benchmarkAllProgress = data.result?.success || 0;
          this.toast('Toplu Benchmark Bitti', data.result?.success + '/' + data.result?.total + ' model başarıyla ölçüldü.', 'success', 6000);
          await this.loadOllamaModels();
          await this.refreshFromDb();
        } else if (data.status === 'failed') {
          this.benchmarkAllRunning = false;
          this.toast('Toplu Benchmark Başarısız', data.error || '', 'error', 6000);
        } else {
          this.benchmarkAllProgress = data.progress || 0;
          setTimeout(() => this._pollBenchmarkAll(), 2000);
        }
      } catch {
        setTimeout(() => this._pollBenchmarkAll(), 2000);
      }
    },

    async ollamaRunModel(modelName) {
      const m = this.installedModels.find(x => x.name === modelName);
      if (m) m._running_op = true;
      this.toast('Model Başlatılıyor', modelName + ' VRAM belleğe yükleniyor...', 'info', 3000);
      try {
        const r = await fetch(this.apiBase + '/api/ollama/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model: modelName }),
        });
        const data = await r.json();
        if (!r.ok || data.error || data.ok === false) {
          throw new Error(data.error || ('HTTP ' + r.status));
        }
        this.toast('Model Aktif!', modelName + ' VRAM belleğe yüklendi ve kullanıma hazır.', 'success', 4000);
        await this.loadOllamaModels();
      } catch (e) {
        this.toast('Çalıştırma Hatası', e.message, 'error', 6000);
      } finally {
        if (m) m._running_op = false;
      }
    },

    async ollamaStopModel(modelName) {
      const m = this.installedModels.find(x => x.name === modelName);
      if (m) m._stopping_op = true;
      this.toast('Model Durduruluyor', modelName + ' bellekten boşaltılıyor...', 'info', 3000);
      try {
        const r = await fetch(this.apiBase + '/api/ollama/stop', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model: modelName }),
        });
        const data = await r.json();
        if (!r.ok || data.error || data.ok === false) {
          throw new Error(data.error || ('HTTP ' + r.status));
        }
        this.toast('Model Durduruldu', modelName + ' VRAM/RAM belleğinden boşaltıldı.', 'info', 3000);
        await this.loadOllamaModels();
      } catch (e) {
        this.toast('Durdurma Hatası', e.message, 'error', 6000);
      } finally {
        if (m) m._stopping_op = false;
      }
    },

    // --- Model Test & Chat Inference Modalı ---
    openTestChatModal(modelName) {
      this.chatModelName = modelName;
      this.chatResponse = null;
      this.chatError = '';
      this.chatModalOpen = true;
    },

    async sendTestChat() {
      if (!this.chatModelName) return;
      this.chatLoading = true;
      this.chatError = '';
      this.chatResponse = null;
      try {
        const r = await fetch(this.apiBase + '/api/ollama/test-chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            model: this.chatModelName,
            prompt: this.chatPrompt || 'Merhaba!',
          }),
        });
        const data = await r.json();
        if (!r.ok || data.ok === false || data.error) {
          throw new Error(data.error || ('HTTP ' + r.status));
        }
        this.chatResponse = data;
        this.toast('Yanıt Alındı', this.chatModelName + ' başarıyla yanıt üretti.', 'success', 3000);
        await this.loadOllamaModels(); // ps durumunu tazele
      } catch (e) {
        this.chatError = e.message;
        this.toast('İstem Hatası', e.message, 'error', 5000);
      } finally {
        this.chatLoading = false;
      }
    },

    // --- Ek Ozellik Metodlari ---

    // --- Ozellik 3: Favori Modeller ---
    toggleFavorite(modelName) {
      const idx = this.favorites.indexOf(modelName);
      if (idx >= 0) {
        this.favorites.splice(idx, 1);
      } else {
        this.favorites.push(modelName);
      }
      localStorage.setItem('benchcompass-favorites', JSON.stringify(this.favorites));
    },

    isFavorite(modelName) {
      return this.favorites.includes(modelName);
    },

    get favCount() {
      return this.favorites.length;
    },

    clearAllFavorites() {
      if (this.favorites.length === 0) return;
      this.favorites = [];
      localStorage.setItem('benchcompass-favorites', '[]');
      this.toast(window.t ? window.t('toast.favorites') : 'Favoriler', window.t ? window.t('toast.favoritesCleared') : 'Tum favoriler temizlendi.', 'info', 3000);
    },

    // --- Ozellik 7: Tier filtre etiketi ---
    toggleTierFilter(tier) {
      this.tierQuickFilter = this.tierQuickFilter === tier ? null : tier;
    },

    // --- Ozellik 9: Kalici filtre state ---
    _saveFilterState() {
      try {
        localStorage.setItem('benchcompass-filters', JSON.stringify({
          search: this.search,
          useFilter: this.useFilter,
          sortBy: this.sortBy,
          onlyCompatible: this.onlyCompatible,
          onlyFavorites: this.onlyFavorites,
          compactCards: this.compactCards,
          minContext: this.minContext,
          notesSearch: this.notesSearch,
        }));
      } catch (err) { console.debug(err); }
    },

    _loadFilterState() {
      try {
        const saved = localStorage.getItem('benchcompass-filters');
        if (saved) {
          const f = JSON.parse(saved);
          if (f.search !== undefined) this.search = f.search;
          if (f.useFilter) this.useFilter = f.useFilter;
          if (f.sortBy) this.sortBy = f.sortBy;
          if (f.onlyCompatible !== undefined) this.onlyCompatible = f.onlyCompatible;
          if (f.onlyFavorites !== undefined) this.onlyFavorites = f.onlyFavorites;
          if (f.compactCards !== undefined) this.compactCards = f.compactCards;
          if (f.minContext !== undefined) this.minContext = f.minContext;
          if (f.notesSearch !== undefined) this.notesSearch = f.notesSearch;
        }
      } catch (err) { console.debug(err); }
    },

    // --- Ozellik 16: Model adi kopyala ---
    copyModelName(name) {
      navigator.clipboard.writeText(name).then(() => {
        this.toast(window.t ? window.t('toast.copied') : 'Kopyalandi', window.t ? window.t('toast.copiedMsg', { name }) : name + ' panoya kopyalandi.', 'success', 2000);
      }).catch(() => {});
    },

    // --- Ozellik 19: Aktivite logu ---
    _addActivity(action) {
      this.activityLog.unshift({
        time: new Date().toLocaleTimeString('tr-TR'),
        action: action,
      });
      if (this.activityLog.length > 20) this.activityLog = this.activityLog.slice(0, 20);
    },

    // --- Ozellik 15: Sparkline data ---
    getSparklineData(modelName) {
      const scores = [];
      this.history.forEach(r => {
        const m = (r.models || []).find(x => x.name === modelName);
        if (m && m.fitScore != null) scores.push(m.fitScore);
      });
      return scores.slice(-8);
    },

    // --- Ozellik 6: Animasyonlu KPI ---
    _animateKpi(el, target) {
      if (!el) return;
      const current = parseFloat(el.textContent) || 0;
      const diff = target - current;
      if (Math.abs(diff) < 1) { el.textContent = target; return; }
      const steps = 20;
      const step = diff / steps;
      let i = 0;
      const anim = () => {
        i++;
        const val = current + step * i;
        el.textContent = Math.round(val);
        if (i < steps) requestAnimationFrame(anim);
        else el.textContent = target;
      };
      requestAnimationFrame(anim);
    },

    // --- Ozellik 26: llmfit doctor endpoint ---
    async loadDoctorReport() {
      this.doctorLoading = true;
      this.showDoctor = true;
      try {
        const r = await fetch(this.apiBase + '/api/benchcompass/doctor');
        const data = await r.json();
        if (data.error) throw new Error(data.error);
        this.doctorReport = data.report;
        this._addActivity('Doctor raporu alindi');
      } catch (e) {
        this.doctorReport = (window.t ? window.t('toast.doctorError') : 'Hata') + ': ' + e.message;
        this.toast(window.t ? window.t('toast.doctorError') : 'Doctor Hatasi', e.message, 'error', 5000);
      } finally {
        this.doctorLoading = false;
      }
    },

    // --- Ozellik 27: llmfit fit import ---
    async loadBenchcompassFit(refresh) {
      this.benchcompassFitLoading = true;
      this.showBenchcompassFit = true;
      try {
        const r = await fetch(this.apiBase + '/api/benchcompass/fit?refresh=' + (refresh ? 'true' : 'false'));
        const data = await r.json();
        if (data.error) throw new Error(data.error);
        this.benchcompassFitData = data;
        this._addActivity('llmfit fit verisi alindi (' + ((data.models||[]).length || '?') + ' model)');
      } catch (e) {
        this.toast(window.t ? window.t('toast.fitError') : 'benchcompass Fit Hatasi', e.message, 'error', 5000);
      } finally {
        this.benchcompassFitLoading = false;
      }
    },

    // --- Ozellik 28: Provider yapilandirmasi ---
    async loadProviderConfig() {
      try {
        const r = await fetch(this.apiBase + '/api/provider');
        this.providerConfig = await r.json();
      } catch (err) { console.debug(err); }
    },

    async saveProviderConfig() {
      if (!this.providerConfig) return;
      try {
        const r = await fetch(this.apiBase + '/api/provider', {
          method: 'PUT',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(this.providerConfig),
        });
        const data = await r.json();
        if (data.ok) this.toast(window.t ? window.t('toast.provider') : 'Provider', window.t ? window.t('toast.providerSaved', { provider: this.providerConfig.active_provider || 'auto' }) : 'Çalışma zamanı sağlayıcısı kaydedildi: ' + (this.providerConfig.active_provider || 'auto'), 'success', 3000);
      } catch (e) {
        this.toast(window.t ? window.t('toast.providerError') : 'Provider Hatasi', e.message, 'error', 5000);
      }
    },

    async changeProvider(runtimeId) {
      if (!this.providerConfig) this.providerConfig = {};
      this.providerConfig.active_provider = runtimeId;
      await this.saveProviderConfig();
    },

    // --- Ozellik 29: Cache yonetimi ---
    async loadCacheStatus() {
      try {
        const r = await fetch(this.apiBase + '/api/benchcompass/cache/status');
        this.cacheStatus = await r.json();
      } catch (err) { console.debug(err); }
    },

    async clearLlmfitCache() {
      try {
        const r = await fetch(this.apiBase + '/api/benchcompass/cache/clear', {method: 'POST'});
        await r.json();
        this.cacheStatus = null;
        this.toast(window.t ? window.t('toast.cache') : 'Cache', window.t ? window.t('toast.cacheCleared') : 'llmfit proxy cache temizlendi.', 'success', 2000);
        this._addActivity('Cache temizlendi');
      } catch (e) {
        this.toast(window.t ? window.t('toast.cacheError') : 'Cache Hatasi', e.message, 'error', 5000);
      }
    },

    // --- Ozellik 30: Rapor export ---
    async downloadReport() {
      this.reportLoading = true;
      try {
        const r = await fetch(this.apiBase + '/api/export/report');
        const text = await r.text();
        const blob = new Blob([text], {type: 'text/markdown'});
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'benchcompass-benchmark-report.md';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        this.toast(window.t ? window.t('toast.report') : 'Rapor', window.t ? window.t('toast.reportDownloaded') : 'Benchmark raporu indirildi.', 'success', 3000);
        this._addActivity('Rapor indirildi');
      } catch (e) {
        this.toast(window.t ? window.t('toast.reportError') : 'Rapor Hatasi', e.message, 'error', 5000);
      } finally {
        this.reportLoading = false;
      }
    },

    // --- Sprint 27: Eval rapor durumu kontrolü (C1) ---
    async checkEvalReport() {
      try {
        const r = await fetch(this.apiBase + '/api/eval/report-status');
        const d = await r.json();
        this.evalReportExists = !!d.exists;
        this.evalReportUpdatedAt = d.updated_at || null;
      } catch (e) {
        this.evalReportExists = false;
        this.evalReportUpdatedAt = null;
      } finally {
        this.evalReportChecked = true;
      }
      this.loadEvalHistory();
    },

    // Sprint 34: Geçmiş koşu listesini yükle (P2)
    async loadEvalHistory() {
      this.evalHistoryLoading = true;
      try {
        const r = await fetch(this.apiBase + '/api/eval/history?limit=100');
        const d = await r.json();
        this.evalHistory = (d && d.runs) || [];
      } catch (e) {
        this.evalHistory = [];
      } finally {
        this.evalHistoryLoading = false;
      }
    },

    // Sprint 54: Kodlama değerlendirmesi (Pass@1/Pass@N kalite kayıtları).
    // Artefakt satırları bilerek DIŞLANMAZ — panelde işaretlenerek gösterilir.
    async loadEvalQuality() {
      this.evalQualityLoading = true;
      this.evalQualityError = '';
      try {
        const r = await fetch(this.apiBase + '/api/eval/quality?limit=500');
        const d = await r.json();
        this.evalQuality = {
          total: d.total || 0,
          ozet: d.ozet || [],
          kayitlar: d.kayitlar || [],
        };
      } catch (e) {
        // Sessiz yutma yok (Y3): hata durumu arayüzde gösterilir.
        this.evalQuality = null;
        this.evalQualityError = (e && e.message) || String(e);
      } finally {
        this.evalQualityLoading = false;
      }
    },

    /** Özet tablo satırları (model bazlı: Pass@1/Pass@N/artefakt). */
    get evalQualityOzet() {
      return (this.evalQuality && this.evalQuality.ozet) || [];
    },

    /** Ham kayıt satırları (artefaktlar dahil — rozetle işaretlenir). */
    get evalQualityKayitlar() {
      return (this.evalQuality && this.evalQuality.kayitlar) || [];
    },

    /** Özetten hariç tutulan geçersiz ölçüm sayısı (panelde not olarak basılır). */
    get evalQualityArtefaktSayisi() {
      return this.evalQualityKayitlar.filter((k) => !evalGecerliMi(k)).length;
    },

    /** Adım 3: iki modelin McNemar eşli karşılaştırmasını yükler. */
    async loadEvalCompare() {
      const a = this.compareModelA;
      const b = this.compareModelB;
      if (!a || !b) {
        this.evalCompare = null;
        this.evalCompareError = window.t
          ? window.t('quality.compareNoData')
          : 'İki model seçilmeli';
        return;
      }
      this.evalCompareLoading = true;
      this.evalCompareError = '';
      try {
        const url =
          this.apiBase +
          '/api/eval/compare?model_a=' +
          encodeURIComponent(a) +
          '&model_b=' +
          encodeURIComponent(b);
        const r = await fetch(url);
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const d = await r.json();
        if (d.ok === false) throw new Error(d.error || 'compare hatası');
        this.evalCompare = d;
      } catch (e) {
        this.evalCompare = null;
        this.evalCompareError = (e && e.message) || String(e);
      } finally {
        this.evalCompareLoading = false;
      }
    },

    // --- Ozellik 4: Tier Dagilim Minibar ---
    get tierDistribution() {
      void this.lang;
      const counts = { 'Tam Uyumlu': 0, 'Uyumlu (Sinirda)': 0, 'Dikkatli Kullan': 0, 'Uygun Degil': 0 };
      this.latest.forEach(m => {
        const t = this.tierOf(m).tier;
        if (counts[t] !== undefined) counts[t]++;
      });
      const total = this.latest.length || 1;
      const short = (canonical) => typeof window.tierShortT === 'function' ? window.tierShortT(canonical) : null;
      return {
        labels: ['TAM', 'SINIR', 'DIKKAT', 'UYGUN'].map((l, i) => {
          const canon = ['Tam Uyumlu', 'Uyumlu (Sinirda)', 'Dikkatli Kullan', 'Uygun Degil'][i];
          return short(canon) || l;
        }),
        values: [counts['Tam Uyumlu'], counts['Uyumlu (Sinirda)'], counts['Dikkatli Kullan'], counts['Uygun Degil']],
        colors: ['var(--success)', 'var(--warn)', 'var(--orange)', 'var(--error)'],
        pcts: [counts['Tam Uyumlu'], counts['Uyumlu (Sinirda)'], counts['Dikkatli Kullan'], counts['Uygun Degil']]
          .map(v => ((v / total) * 100).toFixed(0)),
        total: this.latest.length,
      };
    },

    // --- Ozellik 1: Son Guncelleme ---
    get friendlyLastUpdated() {
      return this.lastUpdated
        ? (window.t ? window.t('footer.lastUpdated', { time: this.lastUpdated }) : 'SON: ' + this.lastUpdated)
        : '—';
    },

  };
  // Getter'lar spread ile kopyalanamaz (değer olarak değerlendirilir);
  // descriptor'larla birleştir ki `this` çalışma anında bileşene bağlansın.
  for (const mixin of DASHBOARD_MIXINS) {
    Object.defineProperties(component, Object.getOwnPropertyDescriptors(mixin));
  }
  return component;
}

// Gerçek ESM export'ları (Vitest doğrudan import eder — Y10)
export {
  esc,
  ctx,
  shortModelName,
  renderNotesParts,
  parseNotesFlags,
  prepareExtraChartData,
  fmtMb,
  fmtW,
  fmtPct,
  evalGecerliMi,
  evalTgGuvenilirMi,
  computeTier,
  computeContextFlag,
  buildTooltip,
  dashboard,
};


// Global scope'a koy (index.html Alpine.data'dan erişir)
window.dashboard = dashboard;
window.computeTier = computeTier;
window.esc = esc;
window.ctx = ctx;
window.shortModelName = shortModelName;
window.renderNotesParts = renderNotesParts;
window.prepareExtraChartData = prepareExtraChartData;
window.fmtMb = fmtMb;
window.fmtW = fmtW;
window.fmtPct = fmtPct;
window.evalGecerliMi = evalGecerliMi;
window.evalTgGuvenilirMi = evalTgGuvenilirMi;
