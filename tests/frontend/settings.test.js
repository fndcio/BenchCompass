/**
 * tests/frontend/settings.test.js
 *
 * Özellik 4 (app.js modülerleştirme) — denetim kapanışı: settings.js mixin'ine
 * taşınan 10 metodun paritesi (mixin birleşimi sonrası dashboard() örneğinde
 * erişilebilirlik) ve profil/ayar davranışları (saveSettings, addProfile,
 * deleteProfile, resetThresholds) kapsanır.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import '../../web/app.js';
import '../../web/i18n.js';

describe('Settings Mixin (Özellik 4 — parite ve davranış)', () => {
  let app;

  const hwConfig = () => ({
    active_profile: 'masaustu',
    profiles: [
      { id: 'masaustu', device_name: 'RTX 5070 Ti', cpu: 'R7', gpu: '5070 Ti', vram_gb: 12, ram_gb: 32, npu_tops: null, storage_gb: null, os: 'win', cuda_version: '12' },
      { id: 'laptop', device_name: 'Laptop', cpu: 'i7', gpu: '4060', vram_gb: 8, ram_gb: 16, npu_tops: null, storage_gb: null, os: 'win', cuda_version: '' },
    ],
    tier_thresholds: { vram_full_margin: 2.0, ram_full_margin: 4.0, vram_caution_margin: -1.5 },
  });

  const mockPutHardware = (respondWith) => vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, opts) => {
    if (String(url).includes('/api/hardware') && opts && opts.method === 'PUT') {
      if (typeof respondWith === 'function') return respondWith(opts.body);
      return { ok: true, json: async () => JSON.parse(opts.body) };
    }
    return { ok: false, status: 404 };
  });

  beforeEach(() => {
    vi.useFakeTimers();
    app = globalThis.dashboard();
    globalThis.setLang('tr');
    app.applyHardwareConfig(hwConfig());
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('settings.js mixin metotları dashboard() örneğinde birleşmiş (parite)', () => {
    const methods = [
      'applyHardwareConfig',
      '_syncSettingsForm',
      'switchActiveProfile',
      '_persistHardwareConfig',
      'saveSettings',
      'addProfile',
      'deleteProfile',
      'saveThresholds',
      'resetThresholds',
      'onProfileSelectChange',
    ];
    for (const m of methods) {
      expect(typeof app[m], `app.${m}`).toBe('function');
    }
    // Getter'lar descriptor kopyasıyla korunmalı
    expect(app.activeProfileId).toBe('masaustu');
    expect(app.profiles).toHaveLength(2);
  });

  it('applyHardwareConfig aktif profili yükler, form ve eşikleri senkronlar', () => {
    expect(app.hardware.device_name).toBe('RTX 5070 Ti');
    expect(app.thresholds.vram_full_margin).toBe(2.0);
    expect(app.settingsForm.vram_gb).toBe(12);
    expect(app.settingsForm.device_name).toBe('RTX 5070 Ti');
  });

  it('saveSettings form değerlerini aktif profile yazar ve PUT gönderir', async () => {
    mockPutHardware();
    app.settingsForm = { ...app.settingsForm, vram_gb: '16', device_name: 'Yeni GPU' };

    await app.saveSettings();

    expect(app.hardwareConfig.profiles[0].vram_gb).toBe(16);
    expect(app.hardwareConfig.profiles[0].device_name).toBe('Yeni GPU');
    expect(app.settingsMsg).toContain('kaydedildi');
  });

  it('saveSettings aktif profil bulunamazsa hata mesajı yazar (PUT yok)', async () => {
    const fetchSpy = mockPutHardware();
    app.hardwareConfig.active_profile = 'yok-boyle';

    await app.saveSettings();

    expect(app.settingsMsg).toContain('bulunamadı');
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('addProfile yeni profil ekler, mükerrer ID reddedilir', async () => {
    mockPutHardware();
    vi.stubGlobal('prompt', vi.fn(() => 'LAPTOP 2'));

    await app.addProfile();

    expect(app.hardwareConfig.profiles.some((p) => p.id === 'laptop-2')).toBe(true);
    expect(app.hardwareConfig.active_profile).toBe('laptop-2');
    expect(app.settingsMsg).toContain('laptop-2');

    // Mükerrer: mevcut profil ID'si ('laptop') tekrar istenirse eklenmez
    vi.stubGlobal('prompt', vi.fn(() => 'laptop'));
    const before = app.hardwareConfig.profiles.length;
    await app.addProfile();
    expect(app.hardwareConfig.profiles.length).toBe(before);
    expect(app.settingsMsg).toContain('zaten var');
  });

  it('deleteProfile son profili silmeye izin vermez', async () => {
    const fetchSpy = mockPutHardware();
    app.hardwareConfig.profiles = [app.hardwareConfig.profiles[0]];
    vi.stubGlobal('confirm', vi.fn(() => true));

    await app.deleteProfile('masaustu');

    expect(app.hardwareConfig.profiles).toHaveLength(1);
    expect(app.settingsMsg).toContain('En az bir profil');
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('deleteProfile aktif profil silinince ilk profile geçer', async () => {
    mockPutHardware();
    vi.stubGlobal('confirm', vi.fn(() => true));

    await app.deleteProfile('masaustu');

    expect(app.hardwareConfig.profiles.some((p) => p.id === 'masaustu')).toBe(false);
    expect(app.hardwareConfig.active_profile).toBe('laptop');
    expect(app.settingsForm.device_name).toBe('Laptop');
  });

  it('resetThresholds eşikleri varsayılana döndürür', () => {
    app.thresholdsForm = { vram_full_margin: 9, ram_full_margin: 9, vram_caution_margin: 9 };

    app.resetThresholds();

    expect(app.thresholdsForm).toEqual({ vram_full_margin: 2.0, ram_full_margin: 4.0, vram_caution_margin: -1.5 });
    expect(app.settingsMsg).toBeTruthy();
  });
});
