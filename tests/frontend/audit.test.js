// Denetim Paneli (ADR-0002 / G12) — web/modules/audit.js davranış testleri.
// Gerçek import zorunlu (Y10); localStorage jsdom'un gerçek bileşenidir.

import { describe, it, expect, beforeEach, vi } from 'vitest';
import '../../web/app.js';
import '../../web/i18n.js';
import {
  KARAR_SIRASI,
  DENETIM_KATALOGU,
  kararlariOku,
  mergeKararlar,
  buildAiPrompt,
  buildAiActionJson,
  buildAiReportMd,
} from '../../web/modules/audit.js';

const KALICILIK_ANAHTARI = 'denetim_kararlari_v1';

describe('audit: karar enumu sözleşmesi', () => {
  it('karar enumu yalnızca 4 değer içerir (rehber bölüm 3)', () => {
    expect(KARAR_SIRASI).toEqual(['KALSIN', 'DUZELT', 'SILINSIN', 'NOT_SET']);
  });
});

describe('audit: katalog şeması', () => {
  it('her öğe DenetimOgesi şemasına uyar ve id benzersizdir', () => {
    const ids = new Set();
    for (const oge of DENETIM_KATALOGU) {
      expect(typeof oge.id).toBe('string');
      expect(oge.id.length).toBeGreaterThan(0);
      expect(ids.has(oge.id)).toBe(false);
      ids.add(oge.id);
      for (const alan of ['sayfaId', 'sayfaAdi', 'bolumAdi', 'etiket', 'kodKonumu', 'aciklama']) {
        expect(typeof oge[alan]).toBe('string');
      }
    }
    expect(ids.size).toBe(DENETIM_KATALOGU.length);
  });

  it('katalog tüm nav görünümlerini ve kritik kartları kapsar', () => {
    const sayfalar = new Set(DENETIM_KATALOGU.map((o) => o.sayfaId));
    const beklenen = [
      'control-center', 'overview', 'mediakit', 'modellerim', 'local-models',
      'arena', 'history', 'charts', 'matris', 'telemetri', 'collector',
      'benchmark', 'magaza', 'rapor', 'kodlama', 'api', 'settings', 'guide',
      'denetim',
    ];
    for (const s of beklenen) expect(sayfalar.has(s)).toBe(true);
    const idler = DENETIM_KATALOGU.map((o) => o.id);
    for (const kart of ['ui-km-asr', 'ui-km-paylasim', 'ui-modellerim-kuyruk', 'ui-magaza-kuyruk', 'ui-telemetri-uyari']) {
      expect(idler).toContain(kart);
    }
  });
});

describe('audit: kalıcılık (localStorage, rehber bölüm 6)', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('kararlariOku: boş depoda boş küme döner', () => {
    expect(kararlariOku()).toEqual({});
  });

  it('kararlariOku: bozuk JSON çökmez, boş küme döner', () => {
    localStorage.setItem(KALICILIK_ANAHTARI, '{bozuk-json');
    const spy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    expect(kararlariOku()).toEqual({});
    expect(spy).toHaveBeenCalled();
  });

  it('kararlariOku: geçersiz karar değeri reddedilir', () => {
    localStorage.setItem(
      KALICILIK_ANAHTARI,
      JSON.stringify({ 'ui-arena': { karar: 'YANLIS_KARAR', duzeltNotu: '' } })
    );
    expect(kararlariOku()).toEqual({});
  });

  it('mergeKararlar: yeni öğe eklense bile eski karar korunur', () => {
    const katalog = [
      { id: 'a', sayfaId: 's', sayfaAdi: 'S', bolumAdi: 'B', etiket: 'e', kodKonumu: 'k', aciklama: 'x' },
      { id: 'b', sayfaId: 's', sayfaAdi: 'S', bolumAdi: 'B2', etiket: 'e', kodKonumu: 'k', aciklama: 'x' },
    ];
    const kayitli = { a: { karar: 'DUZELT', duzeltNotu: 'baslik kucuk' } };
    const merged = mergeKararlar(katalog, kayitli);
    expect(merged[0].karar).toBe('DUZELT');
    expect(merged[0].duzeltNotu).toBe('baslik kucuk');
    expect(merged[1].karar).toBe('NOT_SET');
  });

  it('mergeKararlar: bozuk not alanı güvenli boşalır', () => {
    const katalog = [
      { id: 'a', sayfaId: 's', sayfaAdi: 'S', bolumAdi: 'B', etiket: 'e', kodKonumu: 'k', aciklama: 'x' },
    ];
    const merged = mergeKararlar(katalog, { a: { karar: 'KALSIN', duzeltNotu: 42 } });
    expect(merged[0].karar).toBe('KALSIN');
    expect(merged[0].duzeltNotu).toBe('');
  });
});

describe('audit: karar akışı (mixin metotları)', () => {
  let app;

  beforeEach(() => {
    localStorage.clear();
    app = globalThis.dashboard();
    globalThis.setLang('tr');
    app.auditAc();
  });

  it('kararVer: geçersiz karar reddedilir, durum değişmez', () => {
    const onceki = app.auditItems.find((o) => o.id === 'ui-arena').karar;
    expect(app.kararVer('ui-arena', 'YANLIS')).toBe(false);
    expect(app.auditItems.find((o) => o.id === 'ui-arena').karar).toBe(onceki);
  });

  it('kararVer: geçerli karar uygulanır ve kalıcıya yazılır', () => {
    expect(app.kararVer('ui-arena', 'DUZELT')).toBe(true);
    expect(app.auditItems.find((o) => o.id === 'ui-arena').karar).toBe('DUZELT');
    const kayitli = JSON.parse(localStorage.getItem(KALICILIK_ANAHTARI));
    expect(kayitli['ui-arena'].karar).toBe('DUZELT');
  });

  it('kararVer: olmayan id reddedilir', () => {
    expect(app.kararVer('yok-boyle-id', 'KALSIN')).toBe(false);
  });

  it('duzeltNotuKaydet: not kaydedilir ve kalıcıya yazılır', () => {
    expect(app.duzeltNotuKaydet('ui-arena', 'etiket hizasi bozuk')).toBe(true);
    expect(app.auditItems.find((o) => o.id === 'ui-arena').duzeltNotu).toBe('etiket hizasi bozuk');
    const kayitli = JSON.parse(localStorage.getItem(KALICILIK_ANAHTARI));
    expect(kayitli['ui-arena'].duzeltNotu).toBe('etiket hizasi bozuk');
  });

  it('auditSummary: sayaçlar ve tamamlanma yüzdesi doğru', () => {
    app.kararVer('ui-arena', 'DUZELT');
    app.kararVer('ui-km-asr', 'KALSIN');
    app.kararVer('ui-magaza', 'SILINSIN');
    const s = app.auditSummary;
    expect(s.toplam).toBe(DENETIM_KATALOGU.length);
    expect(s.KALSIN).toBe(1);
    expect(s.DUZELT).toBe(1);
    expect(s.SILINSIN).toBe(1);
    expect(s.NOT_SET).toBe(DENETIM_KATALOGU.length - 3);
    expect(s.tamamlanmaYuzdesi).toBe(Math.round((3 / DENETIM_KATALOGU.length) * 100));
  });

  it('filteredAuditItems: karar filtresi + metin arama', () => {
    app.kararVer('ui-arena', 'DUZELT');
    app.kararVer('ui-km-asr', 'KALSIN');
    app.auditKararFiltre = 'DUZELT';
    expect(app.filteredAuditItems.map((o) => o.id)).toEqual(['ui-arena']);
    app.auditKararFiltre = '';
    app.auditArama = 'asr';
    expect(app.filteredAuditItems.map((o) => o.id)).toEqual(['ui-km-asr']);
  });

  it('copyAiPrompt: önizleme metnini doldurur ve prompt döndürür', () => {
    app.kararVer('ui-arena', 'DUZELT');
    const metin = app.copyAiPrompt();
    expect(app.auditPromptMetni).toBe(metin);
    expect(metin).toContain('G1-G3 kalite kapılarını çalıştır');
  });
});

describe('audit: AI talimat üretimi (rehber bölüm 5)', () => {
  let app;

  beforeEach(() => {
    localStorage.clear();
    app = globalThis.dashboard();
    globalThis.setLang('tr');
    app.auditAc();
  });

  it('buildAiPrompt: DUZELT/SILINSIN listelenir, KALSIN girmez', () => {
    app.kararVer('ui-arena', 'DUZELT');
    app.duzeltNotuKaydet('ui-arena', 'etiket hizasi bozuk');
    app.kararVer('ui-km-asr', 'KALSIN');
    const prompt = buildAiPrompt(app.auditItems);
    expect(prompt).toContain('[DUZELT] Model Arenası > Düello + oylama paneli');
    expect(prompt).toContain('etiket hizasi bozuk');
    expect(prompt).toContain('G1-G3 kalite kapılarını çalıştır.');
    expect(prompt).not.toContain('Teşhis Kartı');
  });

  it('buildAiPrompt: kararlı öğe yokken bilgilendirme + kapanış', () => {
    const prompt = buildAiPrompt(app.auditItems);
    expect(prompt).toContain('kararlı öğe yok');
    expect(prompt).toContain('G1-G3 kalite kapılarını çalıştır.');
  });

  it('buildAiActionJson: yalnız DUZELT/SILINSIN, alanlar doğru', () => {
    app.kararVer('ui-arena', 'SILINSIN');
    app.kararVer('ui-km-asr', 'KALSIN');
    const payload = JSON.parse(buildAiActionJson(app.auditItems));
    expect(payload).toHaveLength(1);
    expect(payload[0]).toEqual({
      id: 'ui-arena',
      karar: 'SILINSIN',
      duzeltNotu: '',
      kodKonumu: 'web/index.html §ARENA',
    });
  });

  it('buildAiReportMd: sayfa bazında gruplu tablo + kararlar', () => {
    app.kararVer('ui-arena', 'DUZELT');
    app.kararVer('ui-km-asr', 'KALSIN');
    const md = buildAiReportMd(app.auditItems);
    expect(md).toContain('## Model Arenası');
    expect(md).toContain('## Kontrol Merkezi');
    expect(md).toContain('| Bölüm | Etiket | Karar | Kod Konumu | Düzeltme Notu |');
    expect(md).toContain('DUZELT');
  });
});
