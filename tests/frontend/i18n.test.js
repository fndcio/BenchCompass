import { describe, expect, it, beforeEach } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import '../../web/i18n.js';
import '../../web/app.js';

describe('i18n çeviri katmanı (web/i18n.js, ADR-0009)', () => {
  beforeEach(() => {
    setLang('tr');
  });

  describe('t()', () => {
    it('TR anahtarları Türkçe döndürür', () => {
      expect(t('nav.overview')).toBe('[ GENEL ]');
      expect(t('tier.full')).toBe('Tam Uyumlu');
    });

    it('EN anahtarları İngilizce döndürür', () => {
      setLang('en');
      expect(t('nav.overview')).toBe('[ OVERVIEW ]');
      expect(t('tier.full')).toBe('Fully Compatible');
    });

    it('bilinmeyen anahtarda fallback TR, o da yoksa anahtarın kendisini döner', () => {
      setLang('en');
      // EN'de eksik olan bir anahtar yoksa TR'ye düşer; burada ikisinde de
      // olmayan bir anahtar denenir:
      expect(t('__missing_key__')).toBe('__missing_key__');
    });

    it('parametre yer tutucularını doldurur', () => {
      expect(t('tooltip.vram', { req: 8, yours: 12, sign: '+', margin: '4.0' }))
        .toContain('Gerekli VRAM: 8 GB | Senin: 12 GB | Boşluk: +4.0 GB');
    });
  });

  describe('setLang() / getLang() / toggleLang()', () => {
    it('dili değiştirip döndürür', () => {
      expect(setLang('en')).toBe('en');
      expect(getLang()).toBe('en');
    });

    it('geçersiz dilde mevcut dili korur', () => {
      const before = getLang();
      expect(setLang('fr')).toBe(before);
    });

    it('toggleLang TR↔EN arasında geçer', () => {
      setLang('tr');
      expect(toggleLang()).toBe('en');
      expect(toggleLang()).toBe('tr');
    });
  });

  describe('sözlük tutarlılığı (Y18)', () => {
    it('EN sözlüğündeki her anahtar TR sözlüğünde de vardır', () => {
      const trKeys = Object.keys(__translations.tr);
      const enKeys = Object.keys(__translations.en);
      const missing = enKeys.filter((k) => !trKeys.includes(k));
      expect(missing).toEqual([]);
    });
  });

  describe('tierT() / tierShortT()', () => {
    it('canonical TR tier değerini görüntü dilinde döndürür', () => {
      expect(tierT('Tam Uyumlu')).toBe('Tam Uyumlu');
      setLang('en');
      expect(tierT('Tam Uyumlu')).toBe('Fully Compatible');
      expect(tierT('Uygun Değil')).toBe('Not Compatible');
    });

    it('backend ASCII varyantlarını da eşler', () => {
      setLang('en');
      expect(tierT('Uyumlu (Sinirda)')).toBe('Compatible (Borderline)');
      expect(tierT('Uygun Degil')).toBe('Not Compatible');
    });

    it('kısa etiketleri döndürür', () => {
      expect(tierShortT('Tam Uyumlu')).toBe('TAM');
      setLang('en');
      expect(tierShortT('Tam Uyumlu')).toBe('FULL');
    });
  });

  describe('dashboard() bileşen reaktivitesi (EN tuşu)', () => {
    it('toggleLangBtn sonrası d.t() ve d.tierT() EN döndürür', () => {
      const d = dashboard();
      setLang('tr');
      d.lang = 'tr';
      expect(d.t('nav.overview')).toBe('[ GENEL ]');
      d.toggleLangBtn();
      expect(d.lang).toBe('en');
      expect(d.t('nav.overview')).toBe('[ OVERVIEW ]');
      expect(d.tierT('Tam Uyumlu')).toBe('Fully Compatible');
      expect(d.getLang()).toBe('en');
    });

    it('app.title çeviri anahtarı iki dilde tanımlı', () => {
      expect(t('app.title')).toBe('BenchCompass');
      setLang('en');
      expect(t('app.title')).toBe('BenchCompass');
    });

    it('d.getLang() reaktif d.lang değerini döndürür', () => {
      const d = dashboard();
      setLang('tr');
      d.lang = 'en';
      expect(d.getLang()).toBe('en');
    });

    it('d.t() parametreli çeviriyi destekler', () => {
      const d = dashboard();
      setLang('tr');
      d.lang = 'tr';
      expect(d.t('tooltip.vram', { req: 8, yours: 12, sign: '+', margin: '4.0' }))
        .toContain('Gerekli VRAM: 8 GB | Senin: 12 GB | Boşluk: +4.0 GB');
    });
  });

  describe('kılavuz gövde içerikleri (guide.bodyNN)', () => {
    const bodyKeys = ['body01', 'body02', 'body03', 'body04', 'body05', 'body06', 'body07',
      'body08', 'body08b', 'body09', 'body10', 'body11', 'body12', 'body13', 'body14',
      'body15', 'body16', 'body17'];

    it('her kılavuz gövde anahtarı TR ve EN\'de tanımlı ve boş değil', () => {
      bodyKeys.forEach((k) => {
        const key = 'guide.' + k;
        expect(__translations.tr[key], `${key} TR eksik`).toBeTruthy();
        expect(__translations.en[key], `${key} EN eksik`).toBeTruthy();
        expect(__translations.tr[key].length, `${key} TR boş`).toBeGreaterThan(10);
        expect(__translations.en[key].length, `${key} EN boş`).toBeGreaterThan(10);
      });
    });

    it('EN gövde İngilizce içerir (TR kopyası değil)', () => {
      expect(t('guide.body01')).toContain('BenchCompass');
      setLang('en');
      expect(t('guide.body01')).toContain('is a dashboard that measures');
      expect(t('guide.body16')).toContain('Q:');
    });
  });

  describe('katalog paritesi (TR ↔ EN)', () => {
    const trKeys = Object.keys(__translations.tr);
    const enKeys = Object.keys(__translations.en);

    it('TR ve EN aynı anahtar kümesine sahip', () => {
      expect(enKeys.sort()).toEqual(trKeys.sort());
    });

    it('yer tutucular ({var}) her iki dilde aynı', () => {
      const placeholders = (value) =>
        [...String(value).matchAll(/\{(\w+)\}/g)].map((match) => match[1]).sort();
      const mismatched = trKeys.filter((key) => {
        const tr = placeholders(__translations.tr[key]);
        const en = placeholders(__translations.en[key]);
        return JSON.stringify(tr) !== JSON.stringify(en);
      });
      expect(mismatched).toEqual([]);
    });

    it('şablonlarda kullanılan statik anahtarların hepsi katalogda tanımlı', () => {
      const modules = readdirSync(resolve(process.cwd(), 'web/modules'))
        .filter((name) => name.endsWith('.js'))
        .map((name) => `web/modules/${name}`);
      const files = ['web/index.html', 'web/app.js', ...modules];
      // Dinamik anahtarlar (`t('gpu.level.' + level)`) bilinçli olarak atlanır;
      // burada yalnız literal anahtarlar denetlenir.
      const literalKey = /(?:[^A-Za-z0-9_$]|^)t\(\s*['"]([^'"`]+)['"]/g;

      const missing = [];
      for (const file of files) {
        const source = readFileSync(resolve(process.cwd(), file), 'utf8');
        for (const match of source.matchAll(literalKey)) {
          const key = match[1];
          if (key.includes('${') || key.endsWith('.') || key.endsWith('_')) continue;
          if (!(key in __translations.tr) || !(key in __translations.en)) {
            missing.push(`${file}: ${key}`);
          }
        }
      }
      expect(missing).toEqual([]);
    });
  });
});
