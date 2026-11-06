/* BenchCompass — Alpine metod grubu (ES modülü)
 * web/app.js'ten ayrıldı (2026-11-05, Faz 2 modülerleştirme).
 * `this` Alpine bileşenine bağlıdır; dashboard() içine spread edilir.
 */

export const guideMethods = {
    // --- Kilavuz Metodlari ---
    toggleGuideSection(id) {
      this.guideOpenSections[id] = !this.guideOpenSections[id];
    },

    goToView(v) {
      this.view = v;
      if (v === 'modellerim') this.loadOllamaModels();
      if (v === 'charts') {
        this.$nextTick(() => {
          // Charts sayfasinin DOM'a eklenmesini bekle
          setTimeout(() => this.renderCharts(), 50);
        });
      }
      // Scroll to top
      this.$nextTick(() => {
        const main = document.querySelector('.main');
        if (main) main.scrollTop = 0;
      });
    },

    setView(v) {
      this.goToView(v);
    },

    // --- İnteraktif Kılavuz Araçları (Sprint 10 / Interactive Guide) ---
    guideCategoryFilter: 'all',
    guideInteractiveVram: 12,
    guideInteractiveRam: 32,
    guideInteractiveModelVram: 8,
    guideInteractiveModelRam: 16,
    guideInteractiveMoeActive: 13,
    guideInteractiveMoeTotal: 47,
    guideInteractiveCliCmd: 'fit',
    guideSelectedRuntime: 'ollama',

    guideRuntimeCards: [
      { id: 'ollama', name: 'Ollama', port: 11434, platform: 'Windows / macOS / Linux', pros: ['Otomatik GPU offload', 'REST API', 'Kolay kurulum'], cons: ['Model yönetimi kendi ekosisteminde'], tip: 'Windows + NVIDIA kartlar için en pratik seçim.' },
      { id: 'lmstudio', name: 'LM Studio', port: 1234, platform: 'Windows / macOS / Linux', pros: ['Görsel arayüz', 'OpenAI-uyumlu API', 'Tek tık indirme'], cons: ['GUI ağırlıklı, script dostu az'], tip: 'Arayüzden sürükleyip bırakarak başlamak isteyenler için.' },
      { id: 'llamacpp', name: 'llama.cpp', port: 8080, platform: 'Windows / macOS / Linux', pros: ['En yüksek performans (C++)', 'Çok hafif', 'Script dostu'], cons: ['Kurulumu manuel'], tip: 'Maksimum hız ve terminal komutlarını sevenler için.' },
      { id: 'mlx', name: 'MLX', port: 8080, platform: 'Apple Silicon (M1+)', pros: ['Metal hızlandırma', 'Apple için en iyi'], cons: ['Sadece Apple M serisi'], tip: 'MacBook / Apple Silicon kullananlar için.' },
    ],

    toggleAllGuideSections(open) {
      Object.keys(this.guideOpenSections).forEach(k => {
        this.guideOpenSections[k] = Boolean(open);
      });
    },

    get guideCalcTier() {
      const th = this.thresholds || { vram_full_margin: 2.0, ram_full_margin: 4.0, vram_caution_margin: -1.5 };
      const vramMargin = (this.guideInteractiveVram || 0) - (this.guideInteractiveModelVram || 0);
      const ramMargin = (this.guideInteractiveRam || 0) - (this.guideInteractiveModelRam || 0);
      let tier = 'Uygun Değil', tone = 'bad', emoji = '🔴';

      if (vramMargin >= th.vram_full_margin && ramMargin >= th.ram_full_margin) {
        tier = 'Tam Uyumlu'; tone = 'good'; emoji = '🟢';
      } else if (vramMargin >= 0.0 && ramMargin >= 0.0) {
        tier = 'Uyumlu (Sınırda)'; tone = 'warn'; emoji = '🟡';
      } else if (vramMargin >= th.vram_caution_margin) {
        tier = 'Dikkatli Kullan'; tone = 'orange'; emoji = '🟠';
      }
      return { tier, tone, emoji, vramMargin, ramMargin };
    },

    get guideCalcMoe() {
      const active = this.guideInteractiveMoeActive || 13;
      const total = this.guideInteractiveMoeTotal || 47;
      const savingsPct = Math.round((1 - (active / total)) * 100);
      const approxVramDenseGb = (total * 0.7).toFixed(1);
      const approxVramMoeGb = (active * 0.7).toFixed(1);
      return { active, total, savingsPct, approxVramDenseGb, approxVramMoeGb };
    },

    get guideGeneratedCliCommand() {
      const sub = this.guideInteractiveCliCmd || 'fit';
      const cmdMap = {
        'fit': 'llmfit fit --json --good',
        'recommend': 'llmfit recommend --use-case coding --limit 5 --json',
        'system': 'llmfit system --json',
        'bench': 'llmfit bench mixtral:8x7b --share',
        'hf-search': 'llmfit hf-search qwen-gguf --limit 10 --json',
        'plan': 'llmfit plan mixtral:8x7b --vram 16 --ram 64 --json',
        'doctor': 'llmfit doctor',
      };
      return cmdMap[sub] || ('llmfit ' + sub);
    },

    get filteredGuideSections() {
      const q = this.guideSearch.trim().toLowerCase();
      const cat = this.guideCategoryFilter;

      const categoryMap = {
        baslangic: ['welcome', 'quickstart', 'tier', 'hardware', 'decision', 'faq', 'shortcuts', 'dictionary'],
        ileri: ['moe', 'runtime', 'benchmark', 'rapor', 'charts', 'collector', 'store', 'compare', 'upgrade', 'ollama', 'testing'],
        sss: ['faq', 'shortcuts', 'dictionary'],
      };

      return Object.keys(this.guideOpenSections).filter(k => {
        if (cat !== 'all') {
          const allowed = categoryMap[cat] || [];
          if (!allowed.includes(k)) return false;
        }
        if (!q) return true;
        const labels = {
          welcome: 'hos geldiniz baslangic mimari',
          quickstart: 'hizli baslangic kurulum port adim calistirma',
          tier: 'tier uyumluluk hesaplama formul margin vram ram uygun degil dikkatli tam uyumlu sinirda',
          hardware: 'donanim profil yonetim ayar cihaz otomatik tespit esik',
          moe: 'moe mixture of experts aktif toplam parametre vram tasarruf',
          runtime: 'multi runtime provider lmstudio llamacpp mlx ollama',
          benchmark: 'benchmark test olcum tok/s ttft itl streaming eszamanlilik concurrency interconnect coklu-gpu simülasyon bant pcie nvlink ethernet ollama gecmis',
          decision: 'karar asistani use-case oneri model tavsiye llmfit',
          charts: 'grafik chart trend dagilim radar scatter pie',
          collector: 'collector periyodik toplama scheduler kurulum powershell',
          store: 'magaza model indirme calistirma huggingface gguf arama',
          compare: 'karsilastirma diff model kiyaslama',
          upgrade: 'upgrade simulator yukseltme plan senaryo',
          ollama: 'ollama yerel model benchmark calistir durdur',
          rapor: 'rapor benchmark eval plugin pipeline quant context turkce vision retrieval community gecmis mcnemar karsilastirma drill-down red-team yaml jailbreak',
          faq: 'sss sik sorulan soru hata cozum port',
          shortcuts: 'klavye kisayol kisa yol tus',
          testing: 'test piramidi unit integration e2e playwright vitest dogrulama kapilari',
          dictionary: 'sozluk terim llm token vram ram moe gguf quantizasyon offload inference',
        };
        const txt = labels[k] || k;
        return txt.includes(q);
      });
    },
};
