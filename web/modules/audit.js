/* BenchCompass — Canlı Arayüz Denetim Paneli (ADR-0002 / AGENTS.md §5 G12)
 * web/app.js dashboard() bileşenine descriptor birleşimiyle katılan mixin modülü.
 * Sözleşme: docs/process/canli_arayuz_denetim_paneli.md (§3 veri modeli, §5
 * dışa aktarım, §6 kalıcılık) + stack-configs/node-typescript/denetim-paneli-rehberi.md.
 * Katalog dashboard'un gerçek bölüm yüzeyini listeler; kararlar Local-First
 * kalır (localStorage, sunucuya gönderilmez — rehber §5).
 */

// G12 karar enumu sözleşmesi (verify_completion.py _PANEL_INDICATORS):
// değerler yalnızca bu dört olabilir; geçersiz karar çalışma anında reddedilir.
export const KARAR_SIRASI = ['KALSIN', 'DUZELT', 'SILINSIN', 'NOT_SET'];
const GECERLI_KARARLAR = new Set(KARAR_SIRASI);

// Kalıcılık anahtarı sürüm ekli (rehber §6: şema değişince sürüm yükseltilir).
const KALICILIK_ANAHTARI = 'denetim_kararlari_v1';

// --- Katalog: dashboard'un gerçek bölüm yüzeyi ------------------------------
// Her öğe DenetimOgesi şemasıdır (rehber §3). Katalog içeriği Türkçe'dir
// (proje doküman dili); panel kromu i18n'dir. kodKonumu satır numarası
// taşımaz (bayatlamasın) — dosya + bölüm işareti yeterlidir.

export const DENETIM_KATALOGU = [
  {
    id: 'ui-control-center',
    sayfaId: 'control-center',
    sayfaAdi: 'Kontrol Merkezi',
    bolumAdi: 'Kontrol Merkezi ana görünümü',
    etiket: 'karargâh',
    kodKonumu: 'web/index.html §CONTROL-CENTER',
    aciklama: 'Operasyonel karargâh: sistem durumu, başlatıcılar, tanılama.',
  },
  {
    id: 'ui-km-asr',
    sayfaId: 'control-center',
    sayfaAdi: 'Kontrol Merkezi',
    bolumAdi: 'ASR & Ses Modelleri Teşhis Kartı',
    etiket: 'asr',
    kodKonumu: 'web/index.html §CONTROL-CENTER > ASR',
    aciklama: 'ASR çalışma ortamı tespiti + model deposu taraması (0.28.0-rc.2).',
  },
  {
    id: 'ui-km-paylasim',
    sayfaId: 'control-center',
    sayfaAdi: 'Kontrol Merkezi',
    bolumAdi: 'Arena Paylaşım Kartı',
    etiket: 'paylaşım',
    kodKonumu: 'web/index.html §CONTROL-CENTER > paylaşım kartı',
    aciklama: 'Arena sonucunu tema duyarlı canvas kartına çevirir (0.28.0-rc.2).',
  },
  {
    id: 'ui-overview',
    sayfaId: 'overview',
    sayfaAdi: 'Genel',
    bolumAdi: 'Genel görünüm kartları',
    etiket: 'genel',
    kodKonumu: 'web/index.html §OVERVIEW',
    aciklama: 'Sistem durumu, karar, donanım profili ve anlık görüntü kartları.',
  },
  {
    id: 'ui-modellerim',
    sayfaId: 'modellerim',
    sayfaAdi: 'Modellerim',
    bolumAdi: 'Kurulu model tablosu',
    etiket: 'modeller',
    kodKonumu: 'web/index.html §MODELLERIM',
    aciklama: 'Ollama kurulu model tablosu + göster/detay akışı.',
  },
  {
    id: 'ui-modellerim-kuyruk',
    sayfaId: 'modellerim',
    sayfaAdi: 'Modellerim',
    bolumAdi: 'Aktif İndirme Kuyruğu',
    etiket: 'kuyruk',
    kodKonumu: 'web/index.html §MODELLERIM > kuyruk',
    aciklama: 'Ollama pull kuyruğu: canlı ilerleme, retry/kaldır (0.28.0-rc.2).',
  },
  {
    id: 'ui-local-models',
    sayfaId: 'local-models',
    sayfaAdi: 'Yerel GGUF',
    bolumAdi: 'Yerel GGUF tarayıcısı',
    etiket: 'gguf',
    kodKonumu: 'web/index.html §LOCAL-MODELS',
    aciklama: "C:\\ sürücüsünde GGUF dosya tarayıcısı (boyut bantları ile).",
  },
  {
    id: 'ui-arena',
    sayfaId: 'arena',
    sayfaAdi: 'Model Arenası',
    bolumAdi: 'Düello + oylama paneli',
    etiket: 'arena',
    kodKonumu: 'web/index.html §ARENA',
    aciklama: 'Kör düello, oylama ve Elo güncellemesi akışı.',
  },
  {
    id: 'ui-arena-liderlik',
    sayfaId: 'arena',
    sayfaAdi: 'Model Arenası',
    bolumAdi: 'Elo Liderlik Tablosu',
    etiket: 'elo',
    kodKonumu: 'web/index.html §ARENA > liderlik',
    aciklama: 'Model Elo sıralaması ve maç sayıları.',
  },
  {
    id: 'ui-history',
    sayfaId: 'history',
    sayfaAdi: 'Geçmiş',
    bolumAdi: 'Koşum geçmişi + karşılaştırma',
    etiket: 'geçmiş',
    kodKonumu: 'web/index.html §HISTORY',
    aciklama: 'Benchmark geçmişi tablosu ve model karşılaştırma görünümü.',
  },
  {
    id: 'ui-charts',
    sayfaId: 'charts',
    sayfaAdi: 'Grafikler',
    bolumAdi: 'Chart.js grafik görünümü',
    etiket: 'grafik',
    kodKonumu: 'web/index.html §CHARTS',
    aciklama: 'Trend, dağılım ve uyumluluk grafikleri (Chart.js).',
  },
  {
    id: 'ui-matris',
    sayfaId: 'matris',
    sayfaAdi: 'Matris',
    bolumAdi: 'Veri-güdümlü karar matrisi',
    etiket: 'matris',
    kodKonumu: 'web/index.html §MATRIS',
    aciklama: 'Karar matrisi + görev profili ağırlıkları önerisi (Sprint 46-47).',
  },
  {
    id: 'ui-telemetri',
    sayfaId: 'telemetri',
    sayfaAdi: 'Telemetri',
    bolumAdi: 'GPU telemetri + enerji/maliyet',
    etiket: 'telemetri',
    kodKonumu: 'web/index.html §TELEMETRI',
    aciklama: 'Canlı GPU grafiği, enerji/maliyet analizi (Sprint 44-45).',
  },
  {
    id: 'ui-telemetri-uyari',
    sayfaId: 'telemetri',
    sayfaAdi: 'Telemetri',
    bolumAdi: 'Eşik Uyarı Bandı + aktif uyarı sayacı',
    etiket: 'uyarı',
    kodKonumu: 'web/index.html §TELEMETRI > eşik uyarıları',
    aciklama: 'Eşik aşımı rozetleri + aktif uyarı sayacı (0.28.0-rc.2).',
  },
  {
    id: 'ui-telemetri-kalib',
    sayfaId: 'telemetri',
    sayfaAdi: 'Telemetri',
    bolumAdi: 'Tahmin İsabeti (Kalibrasyon) Paneli',
    etiket: 'kalibrasyon',
    kodKonumu: 'web/index.html §TELEMETRI > kalibrasyon',
    aciklama: 'Tahmin isabeti bant/n/sapma paneli (Sprint 45 / P1-2).',
  },
  {
    id: 'ui-collector',
    sayfaId: 'collector',
    sayfaAdi: 'Collector',
    bolumAdi: 'Collector görünümü',
    etiket: 'collector',
    kodKonumu: 'web/index.html §COLLECTOR',
    aciklama: 'Benchmark collector kurulum ve çalıştırma görünümü.',
  },
  {
    id: 'ui-benchmark',
    sayfaId: 'benchmark',
    sayfaAdi: 'Benchmark',
    bolumAdi: 'Benchmark görünümü',
    etiket: 'benchmark',
    kodKonumu: 'web/index.html §BENCHMARK',
    aciklama: 'Benchmark başlatma ve koşum geçmişi görünümü.',
  },
  {
    id: 'ui-magaza',
    sayfaId: 'magaza',
    sayfaAdi: 'Mağaza',
    bolumAdi: 'Mağaza kataloğu',
    etiket: 'mağaza',
    kodKonumu: 'web/index.html §MAGAZA',
    aciklama: 'İndirilebilir model kataloğu + indirilenler + sunucular.',
  },
  {
    id: 'ui-magaza-kuyruk',
    sayfaId: 'magaza',
    sayfaAdi: 'Mağaza',
    bolumAdi: 'İndirme Kuyruğu Bloğu',
    etiket: 'kuyruk',
    kodKonumu: 'web/index.html §MAGAZA > kuyruk',
    aciklama: 'Mağaza içi kuyruk görünürlüğü (0.28.0-rc.2 sapma kapanışı).',
  },
  {
    id: 'ui-rapor',
    sayfaId: 'rapor',
    sayfaAdi: 'Rapor',
    bolumAdi: 'Rapor görünümü',
    etiket: 'rapor',
    kodKonumu: 'web/index.html §RAPOR',
    aciklama: 'Değerlendirme raporu + geçmiş koşumlar görünümü.',
  },
  {
    id: 'ui-kodlama',
    sayfaId: 'kodlama',
    sayfaAdi: 'Kodlama',
    bolumAdi: 'Kodlama Değerlendirmesi',
    etiket: 'kodlama',
    kodKonumu: 'web/index.html §KODLAMA',
    aciklama: 'Kalite değerlendirmesi özet + kayıt tablosu (TAB 9 kapanışı).',
  },
  {
    id: 'ui-api',
    sayfaId: 'api',
    sayfaAdi: 'API',
    bolumAdi: 'API görünümü',
    etiket: 'api',
    kodKonumu: 'web/index.html §API',
    aciklama: 'API uç noktaları görünümü.',
  },
  {
    id: 'ui-ayarlar',
    sayfaId: 'settings',
    sayfaAdi: 'Ayarlar',
    bolumAdi: 'Ayarlar görünümü',
    etiket: 'ayarlar',
    kodKonumu: 'web/index.html §SETTINGS',
    aciklama: 'Donanım profili + tier eşikleri ayarları (Sprint 6+).',
  },
  {
    id: 'ui-kilavuz',
    sayfaId: 'guide',
    sayfaAdi: 'Kılavuz',
    bolumAdi: 'Kullanıcı kılavuzu görünümü',
    etiket: 'kılavuz',
    kodKonumu: 'web/index.html §GUIDE',
    aciklama: 'Dashboard içi kullanım kılavuzu.',
  },
  {
    id: 'ui-mediakit',
    sayfaId: 'mediakit',
    sayfaAdi: 'Medya Kit',
    bolumAdi: 'Medya Kit & Hub görünümü',
    etiket: 'medya',
    kodKonumu: 'web/index.html §MEDIAKIT',
    aciklama: 'Medya kiti & paylaşım hub görünümü.',
  },
  {
    id: 'ui-denetim',
    sayfaId: 'denetim',
    sayfaAdi: 'Denetim',
    bolumAdi: 'Denetim Paneli (bu bölüm)',
    etiket: 'denetim',
    kodKonumu: 'web/index.html §DENETIM',
    aciklama: 'Bu panel — ADR-0002 disiplininin canlı arayüzü (0.28.0-rc.2).',
  },
];

// --- Kalıcılık yardımcıları (saf fonksiyonlar) ------------------------------

// Bozuk kalıcılık senaryosu rehber §6 iskeletinden gelir: try/catch + güvenli
// boş dönüş (panel çökmez). Sessiz yutma değil — uyarı günlüğü + bilinçli
// boş karar kümesi (Y3'ün JS karşılığı bilinçli ve gerekçeli).
export function kararlariOku() {
  try {
    const raw = localStorage.getItem(KALICILIK_ANAHTARI);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
    const kararlar = {};
    for (const [id, kayit] of Object.entries(parsed)) {
      if (!kayit || typeof kayit !== 'object') continue;
      // Geçersiz karar değeri reddedilir (rehber §3: enum sözleşmesi).
      if (!GECERLI_KARARLAR.has(kayit.karar)) continue;
      kararlar[id] = {
        karar: kayit.karar,
        duzeltNotu: typeof kayit.duzeltNotu === 'string' ? kayit.duzeltNotu : '',
      };
    }
    return kararlar;
  } catch (e) {
    console.warn('Denetim kararları okunamadı (kalıcılık bozuk, boş başlanacak):', e);
    return {};
  }
}

function kararlarYaz(kararlar) {
  try {
    localStorage.setItem(KALICILIK_ANAHTARI, JSON.stringify(kararlar));
    return true;
  } catch (e) {
    console.warn('Denetim kararları yazılamadı:', e);
    return false;
  }
}

// id-bazlı merge (rehber §6): yeni öğe eklense bile eski karar korunur;
// katalogdan düşen öğenin kararı yok sayılır; kayıttaki bozuk alanlar
// güvenli şekilde varsayılana düşer (dürüst şema doğrulaması).
export function mergeKararlar(katalog, kayitli) {
  return katalog.map((oge) => {
    const k = kayitli[oge.id];
    if (!k) return { ...oge, karar: 'NOT_SET', duzeltNotu: '' };
    return {
      ...oge,
      karar: k.karar,
      duzeltNotu: typeof k.duzeltNotu === 'string' ? k.duzeltNotu : '',
    };
  });
}

// --- AI talimat üretimi (rehber §5; üçü de saf string döndürür) -------------

function mdHucre(metin) {
  // MD tablo hücresi: '|' kaçışlı, satır sonları boşluğa çevrilir.
  return String(metin ?? '').replace(/\|/g, '\\|').replace(/\r?\n/g, ' ');
}

// 5.1 AI Prompt — DUZELT/SILINSIN öğelerini doğal dile çevirir; kapanış
// "G1–G3 kalite kapılarını çalıştır" (rehber §5.1 sözleşmesi).
export function buildAiPrompt(ogeler) {
  const kararli = (ogeler || []).filter(
    (o) => o.karar === 'DUZELT' || o.karar === 'SILINSIN'
  );
  const satirlar = kararli.map(
    (o) =>
      `- [${o.karar}] ${o.sayfaAdi} > ${o.bolumAdi} (${o.kodKonumu}): ${
        o.duzeltNotu || o.aciklama
      }`
  );
  const govde = satirlar.length
    ? satirlar.join('\n')
    : '- (DUZELT/SILINSIN kararlı öğe yok — diğer öğeler KALSIN/NOT_SET)';
  return [
    'BenchCompass arayüz denetim talimatı',
    '===================================',
    'Aşağıdaki arayüz kararları insan tarafından verildi; sırayla uygula.',
    '',
    govde,
    '',
    'Uygulamadan sonra G1-G3 kalite kapılarını çalıştır.',
  ].join('\n');
}

// 5.2 AI Aksiyon JSON — otonom agent için yapısal payload.
export function buildAiActionJson(ogeler) {
  const kararli = (ogeler || []).filter(
    (o) => o.karar === 'DUZELT' || o.karar === 'SILINSIN'
  );
  return JSON.stringify(
    kararli.map((o) => ({
      id: o.id,
      karar: o.karar,
      duzeltNotu: o.duzeltNotu || '',
      kodKonumu: o.kodKonumu,
    })),
    null,
    2
  );
}

// 5.3 Markdown Rapor — sayfa bazında gruplanmış tablo (rehber §5.3).
export function buildAiReportMd(ogeler) {
  const liste = ogeler || [];
  const sayfalar = [...new Set(liste.map((o) => o.sayfaAdi))];
  const cikti = ['# Denetim Raporu', ''];
  for (const sayfa of sayfalar) {
    cikti.push(
      `## ${sayfa}`,
      '',
      '| Bölüm | Etiket | Karar | Kod Konumu | Düzeltme Notu |',
      '|---|---|---|---|---|'
    );
    for (const o of liste.filter((x) => x.sayfaAdi === sayfa)) {
      cikti.push(
        `| ${mdHucre(o.bolumAdi)} | ${mdHucre(o.etiket)} | ${o.karar} | ${mdHucre(
          o.kodKonumu
        )} | ${mdHucre(o.duzeltNotu || '-')} |`
      );
    }
    cikti.push('');
  }
  return cikti.join('\n').trimEnd() + '\n';
}

// --- Mixin: dashboard() bileşenine katılan metot/getter grubu ----------------

export const auditMethods = {
  // Denetim görünümüne girişte: katalog + kayıtlı kararları birleştir.
  auditAc() {
    this.auditItems = mergeKararlar(
      DENETIM_KATALOGU.map((o) => ({ ...o, karar: 'NOT_SET', duzeltNotu: '' })),
      kararlariOku()
    );
  },

  // Karar ver — enum doğrulamalı (rehber §3: geçersiz değer reddedilir).
  kararVer(id, karar) {
    if (!GECERLI_KARARLAR.has(karar)) {
      console.warn('Geçersiz denetim kararı reddedildi:', karar);
      return false;
    }
    const oge = (this.auditItems || []).find((o) => o.id === id);
    if (!oge) return false;
    oge.karar = karar;
    return kararlarYaz(this._kararHaritasi());
  },

  // Düzeltme notunu kaydet (DUZELT/SILINSIN'e eşlik eden AI talimat metni).
  duzeltNotuKaydet(id, metin) {
    const oge = (this.auditItems || []).find((o) => o.id === id);
    if (!oge) return false;
    oge.duzeltNotu = String(metin ?? '');
    return kararlarYaz(this._kararHaritasi());
  },

  _kararHaritasi() {
    return Object.fromEntries(
      (this.auditItems || []).map((o) => [
        o.id,
        { karar: o.karar, duzeltNotu: o.duzeltNotu || '' },
      ])
    );
  },

  // Karar özeti (rehber §7): toplam + 4 karar sayacı + tamamlanma yüzdesi.
  get auditSummary() {
    const ogeler = this.auditItems || [];
    const sayac = { KALSIN: 0, DUZELT: 0, SILINSIN: 0, NOT_SET: 0 };
    for (const o of ogeler) {
      if (sayac[o.karar] !== undefined) sayac[o.karar] += 1;
      else sayac.NOT_SET += 1;
    }
    const kararli = ogeler.length - sayac.NOT_SET;
    return {
      toplam: ogeler.length,
      ...sayac,
      tamamlanmaYuzdesi: ogeler.length
        ? Math.round((kararli / ogeler.length) * 100)
        : 0,
    };
  },

  // Arama + karar filtresi (rehber §7 Arama & Filtre modülünün mini karşılığı).
  get filteredAuditItems() {
    const filtre = this.auditKararFiltre || '';
    const arama = (this.auditArama || '').trim().toLocaleLowerCase('tr');
    return (this.auditItems || []).filter((o) => {
      if (filtre && o.karar !== filtre) return false;
      if (!arama) return true;
      return [o.bolumAdi, o.etiket, o.kodKonumu, o.sayfaAdi]
        .join(' ')
        .toLocaleLowerCase('tr')
        .includes(arama);
    });
  },

  // Dışa aktarım (rehber §5): prompt panoya, JSON/MD dosya olarak iner.
  // Yer adlandırma G12 göstergeleriyle uyumlu: copyAiPrompt / exportAiAction.
  copyAiPrompt() {
    const metin = buildAiPrompt(this.auditItems);
    this.auditPromptMetni = metin;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard
        .writeText(metin)
        .catch((e) => console.warn('Panoya kopyalama başarısız:', e));
    }
    return metin;
  },

  exportAiAction() {
    this.auditDosyaIndir(
      'ai-aksiyon.json',
      buildAiActionJson(this.auditItems),
      'application/json'
    );
  },

  exportAiReport() {
    this.auditDosyaIndir(
      'denetim-raporu.md',
      buildAiReportMd(this.auditItems),
      'text/markdown'
    );
  },

  auditDosyaIndir(dosyaAdi, icerik, mime) {
    const blob = new Blob([icerik], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = dosyaAdi;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
};
