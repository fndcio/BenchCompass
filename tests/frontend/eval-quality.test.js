/**
 * tests/frontend/eval-quality.test.js
 *
 * Sprint 54: "Kodlama Değerlendirmesi" sekmesi — `/api/eval/quality` tüketimi.
 *
 * Gerçek import kullanılır (Y10): web/app.js + web/i18n.js. `document.body.
 * innerHTML` factory stub YASAK. Render sözleşmesi, bileşenin ürettiği türetilmiş
 * durum (ozet/kayitlar/artefakt sayacı) + index.html bağlayıcı denetimiyle
 * doğrulanır.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import '../../web/i18n.js';
import '../../web/app.js';

// Render sözleşmesi denetimi: sekme gövdesi gerçek index.html'den okunur
// (vitest kök dizini = proje kökü, bkz. vitest.config.js).
const INDEX_HTML = readFileSync(resolve(process.cwd(), 'web/index.html'), 'utf8');

/** API sözleşmesine birebir uyan örnek yanıt (geçerli + artefakt + char_tahmin). */
const ORNEK_YANIT = {
  ok: true,
  total: 3,
  ozet: [
    {
      model: 'rc-gemma4-udq4kxl:latest',
      gorev_sayisi: 4,
      kodlama_gorev: 4,
      pass1: 1,
      passN: 2,
      ort_deneme: 1.5,
      ort_tg: 56.0,
      alt_senaryo: 4,
      needle_senaryo: 2,
      needle_passN: 2,
      varyans_kosu: 0,
      varyans_passN: 0,
      artefakt: 1,
    },
    {
      model: 'bonsai2-27b-mtp-procreations',
      gorev_sayisi: 2,
      kodlama_gorev: 2,
      pass1: 1,
      passN: 1,
      ort_deneme: 1.0,
      ort_tg: 433.0,
      alt_senaryo: 2,
      needle_senaryo: 0,
      needle_passN: 0,
      varyans_kosu: 0,
      varyans_passN: 0,
      artefakt: 0,
    },
  ],
  kayitlar: [
    {
      id: 48,
      model: 'rc-gemma4-udq4kxl:latest',
      gorev: 'G7',
      dil: 'en',
      deneme: 1,
      visible: 1,
      hidden: 1,
      pass1: 1,
      passN: 1,
      attempts: 1,
      tg: 58.9,
      tg_kaynagi: 'eval_duration',
      tokens: 84,
      finish: 'stop',
      thinking: 'kapali',
      harness_sha: '6a7e7d06393d',
      seed: null,
      source: 'rc_gemma4_deep_hedefli',
      gecerlilik: 'gecerli',
      notlar: null,
      created_at: '2026-10-07 13:44:04',
    },
    {
      id: 47,
      model: 'rc-gemma4-udq4kxl:latest',
      gorev: 'G7',
      dil: 'en',
      deneme: 2,
      visible: 0,
      hidden: 0,
      pass1: 0,
      passN: 0,
      attempts: 2,
      tg: 340.0,
      tg_kaynagi: 'char_tahmin',
      tokens: 84,
      finish: 'stop',
      thinking: 'kapali',
      harness_sha: '6a7e7d06393d',
      seed: null,
      source: 'rc_gemma4_deep_hedefli',
      gecerlilik: 'artefakt-g7',
      notlar: null,
      created_at: '2026-10-06 09:00:00',
    },
    {
      id: 46,
      model: 'bonsai2-27b-mtp-procreations',
      gorev: 'B2',
      dil: 'tr',
      deneme: 1,
      visible: 1,
      hidden: 1,
      pass1: 1,
      passN: 1,
      attempts: 1,
      tg: 433.0,
      tg_kaynagi: 'char_tahmin',
      tokens: 20,
      finish: 'stop',
      thinking: null,
      harness_sha: null,
      seed: null,
      source: 'bonsai_deep',
      gecerlilik: 'gecerli',
      notlar: null,
      created_at: '2026-10-06 08:00:00',
    },
  ],
};

describe('Kodlama Değerlendirmesi sekmesi (Sprint 54)', () => {
  let d;

  beforeEach(() => {
    d = dashboard();
    d.apiBase = 'http://localhost:8788';
    setLang('tr');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('loadEvalQuality', () => {
    it('özet ve kayıtları API sözleşmesine göre yükler', async () => {
      const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => ORNEK_YANIT,
      });

      await d.loadEvalQuality();

      expect(String(fetchSpy.mock.calls[0][0])).toContain('/api/eval/quality');
      expect(d.evalQualityLoading).toBe(false);
      expect(d.evalQualityError).toBe('');
      expect(d.evalQuality.total).toBe(3);
      expect(d.evalQualityOzet).toEqual(ORNEK_YANIT.ozet);
      expect(d.evalQualityKayitlar).toHaveLength(3);
      // Geçerli ölçümler özet metriklerini taşır (Pass@1/Pass@N).
      expect(d.evalQualityOzet[0].pass1).toBe(1);
      expect(d.evalQualityOzet[0].passN).toBe(2);
      expect(d.evalQualityOzet[0].ort_deneme).toBe(1.5);
    });

    it('özet render sözleşmesi: satırlar model/görev/Pass@1/Pass@N/artefakt bağlar', () => {
      // Sekme gövdesi + özet tablo döngüsü index.html'de tanımlı olmalı.
      expect(INDEX_HTML).toContain("x-show=\"view==='kodlama'\"");
      expect(INDEX_HTML).toContain("t('nav.evalQuality')");
      expect(INDEX_HTML).toContain('x-for="o in evalQualityOzet"');
      // Pass@1/Pass@N paydası KODLAMA görevidir (iğne/varyans ayrı sütunda —
      // metodoloji karışımı yasak). Bu yüzden `kodlama_gorev` bağlanmalı.
      for (const alan of [
        'o.kodlama_gorev',
        'o.pass1',
        'o.passN',
        'o.ort_deneme',
        'o.artefakt',
        'o.needle_senaryo',
        'o.varyans_kosu',
      ]) {
        expect(INDEX_HTML).toContain(alan);
      }
      expect(INDEX_HTML).toContain('Pass@1');
      expect(INDEX_HTML).toContain('Pass@N');
    });
  });

  describe('artefakt (gecersiz ölçüm) işaretleme', () => {
    beforeEach(async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => ORNEK_YANIT,
      });
      await d.loadEvalQuality();
    });

    it('artefakt-g7 satırı geçersiz sayılır, geçerli satır geçerli', () => {
      expect(evalGecerliMi(ORNEK_YANIT.kayitlar[0])).toBe(true);
      expect(evalGecerliMi(ORNEK_YANIT.kayitlar[1])).toBe(false);
      // NULL gecerlilik backend ile aynı şekilde geçerli kabul edilir.
      expect(evalGecerliMi({ gecerlilik: null })).toBe(true);
      expect(evalGecerliMi(null)).toBe(false);
    });

    it('artefakt sayacı özetten hariç tutulan satırları sayar', () => {
      expect(d.evalQualityArtefaktSayisi).toBe(1);
      expect(d.evalQuality.ozet[0].artefakt).toBe(1);
    });

    it('artefakt satırı görsel olarak ayrılır (rozet + satır sınıfı)', () => {
      expect(INDEX_HTML).toContain('quality-artifact-row');
      expect(INDEX_HTML).toContain('!evalGecerliMi(k)');
      expect(INDEX_HTML).toContain("t('quality.badgeArtifact')");
      // Açıklama notu kullanıcıya artefaktın ne olduğunu anlatmalı.
      expect(t('quality.badgeArtifact')).toContain('artefakt');
      setLang('en');
      expect(t('quality.badgeArtifact')).toContain('artifact');
      expect(t('quality.artifactExplain')).toContain('G7');
    });
  });

  describe('hız alanı güven sınırı (char_tahmin sahte tok/s)', () => {
    it('yalnız sunucu-beyanlı decode kaynakları güvenilir sayılır', () => {
      expect(evalTgGuvenilirMi({ tg_kaynagi: 'eval_duration' })).toBe(true);
      expect(evalTgGuvenilirMi({ tg_kaynagi: 'usage' })).toBe(true);
      expect(evalTgGuvenilirMi({ tg_kaynagi: 'timings' })).toBe(true);
      expect(evalTgGuvenilirMi({ tg_kaynagi: 'char_tahmin', tg: 433 })).toBe(false);
      expect(evalTgGuvenilirMi({ tg_kaynagi: null })).toBe(false);
      expect(evalTgGuvenilirMi(null)).toBe(false);
    });

    it('panel güvenilmez kaynakta "—" basar ve sınırı not düşer', () => {
      expect(INDEX_HTML).toContain('evalTgGuvenilirMi(k)');
      expect(INDEX_HTML).toContain("t('quality.speedNote')");
      expect(t('quality.speedNote')).toContain('char_tahmin');
      expect(t('quality.speedNote')).toContain('eval_duration');
    });
  });

  describe('boş durum', () => {
    it('yükleme öncesi türetilmiş listeler boş döner (çökmez)', () => {
      expect(d.evalQuality).toBeNull();
      expect(d.evalQualityOzet).toEqual([]);
      expect(d.evalQualityKayitlar).toEqual([]);
      expect(d.evalQualityArtefaktSayisi).toBe(0);
    });

    it('boş veri geldiğinde özet ve kayıtlar boş kalır, hata üretmez', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => ({ ok: true, total: 0, ozet: [], kayitlar: [] }),
      });

      await d.loadEvalQuality();

      expect(d.evalQualityError).toBe('');
      expect(d.evalQuality.total).toBe(0);
      expect(d.evalQualityOzet).toEqual([]);
      expect(d.evalQualityKayitlar).toEqual([]);
      // Boş durum mesajı index.html'de tanımlı olmalı (sessiz boş ekran yok).
      expect(INDEX_HTML).toContain("t('quality.emptyHint')");
      expect(INDEX_HTML).toContain("t('quality.noRecords')");
      expect(INDEX_HTML).toContain('empty-state');
    });

    it('eksik ozet/kayitlar alanları da boş listeye düşer', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => ({ ok: true }),
      });

      await d.loadEvalQuality();

      expect(d.evalQuality.total).toBe(0);
      expect(d.evalQualityOzet).toEqual([]);
      expect(d.evalQualityKayitlar).toEqual([]);
    });
  });

  describe('fetch hatası', () => {
    it('ağ hatasında evalQuality=null, hata mesajı saklanır (Y3: yutma yok)', async () => {
      vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('network down'));

      await d.loadEvalQuality();

      expect(d.evalQualityLoading).toBe(false);
      expect(d.evalQuality).toBeNull();
      expect(d.evalQualityError).toBe('network down');
      expect(d.evalQualityOzet).toEqual([]);
      expect(d.evalQualityKayitlar).toEqual([]);
      expect(INDEX_HTML).toContain("t('quality.error')");
    });

    it('yeniden yükleme hatadan sonra durumu temizler', async () => {
      const fetchSpy = vi.spyOn(globalThis, 'fetch');
      fetchSpy.mockRejectedValueOnce(new Error('boom'));
      await d.loadEvalQuality();
      expect(d.evalQualityError).toBe('boom');

      fetchSpy.mockResolvedValueOnce({
        ok: true,
        json: async () => ORNEK_YANIT,
      });
      await d.loadEvalQuality();

      expect(d.evalQualityError).toBe('');
      expect(d.evalQuality.total).toBe(3);
    });
  });
});
