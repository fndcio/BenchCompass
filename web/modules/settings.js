/* BenchCompass — Ayarlar ve donanım profili metodları (ES modülü)
 * web/app.js'ten ayrıldı (2026-11-05, Özellik 4 modülerleştirme).
 * `this` Alpine bileşenine bağlıdır; dashboard() içine DASHBOARD_MIXINS ile dahil edilir.
 */

export const settingsMethods = {
    applyHardwareConfig(hw) {
      if (!hw) return;
      this.hardwareConfig = hw;
      const active = (hw.profiles || []).find(p => p.id === hw.active_profile) || (hw.profiles || [])[0];
      if (active) {
        this.hardware = active;
        // Sprint 6: settings formunu da aktif profille doldur
        this._syncSettingsForm(active);
      }
      if (hw.tier_thresholds) {
        this.thresholds = hw.tier_thresholds;
        // Sprint 6: threshold form kopyası
        this.thresholdsForm = { ...hw.tier_thresholds };
      }
      // filteredModels cache'ini invalidate etmek için donanim referansini degistirelim
      this._filterCacheKey = null;
    },

    _syncSettingsForm(profile) {
      if (!profile) return;
      this.settingsForm = {
        device_name: profile.device_name || '',
        cpu: profile.cpu || '',
        gpu: profile.gpu || '',
        vram_gb: profile.vram_gb ?? 12,
        ram_gb: profile.ram_gb ?? 32,
        npu_tops: profile.npu_tops ?? null,
        storage_gb: profile.storage_gb ?? null,
        os: profile.os || '',
        cuda_version: profile.cuda_version || '',
      };
    },

    // --- Sprint 6: Ayarlar (Kriter #12) ---
    get activeProfileId() {
      return this.hardwareConfig?.active_profile || '';
    },

    get profiles() {
      return this.hardwareConfig?.profiles || [];
    },

    switchActiveProfile(profileId) {
      if (!this.hardwareConfig) return;
      this.hardwareConfig.active_profile = profileId;
      this._persistHardwareConfig();
    },

    async _persistHardwareConfig() {
      if (!this.hardwareConfig) return;
      try {
        const r = await fetch(this.apiBase + '/api/hardware', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.hardwareConfig),
        });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const updated = await r.json();
        this.applyHardwareConfig(updated);
      } catch (e) {
        console.error('Donanim config kaydedilemedi:', e);
      }
    },

    async saveSettings() {
      // Aktif profili formdan gelen değerlerle güncelle, sonra PUT
      if (!this.hardwareConfig) return;
      const profileId = this.hardwareConfig.active_profile || (this.profiles[0]?.id);
      const idx = this.hardwareConfig.profiles.findIndex(p => p.id === profileId);
      if (idx < 0) {
        this.settingsMsg = 'Aktif profil bulunamadı.';
        return;
      }
      this.hardwareConfig.profiles[idx] = {
        ...this.hardwareConfig.profiles[idx],
        ...this.settingsForm,
        vram_gb: Number(this.settingsForm.vram_gb),
        ram_gb: Number(this.settingsForm.ram_gb),
        npu_tops: this.settingsForm.npu_tops != null && this.settingsForm.npu_tops !== '' ? Number(this.settingsForm.npu_tops) : null,
        storage_gb: this.settingsForm.storage_gb != null && this.settingsForm.storage_gb !== '' ? Number(this.settingsForm.storage_gb) : null,
      };
      await this._persistHardwareConfig();
      this.settingsMsg = '✓ Donanım profili kaydedildi. Tüm tier\'lar güncellendi.';
      // 3 saniye sonra mesajı temizle
      setTimeout(() => { this.settingsMsg = ''; }, 3000);
    },

    async addProfile() {
      if (!this.hardwareConfig) return;
      const name = prompt(window.t ? window.t('dialog.profileId') : 'Yeni profil için kısa bir ID girin (örn: masaustu, laptop2):');
      if (!name) return;
      const id = name.trim().toLowerCase().replace(/[^a-z0-9_-]/g, '-');
      if (this.hardwareConfig.profiles.some(p => p.id === id)) {
        this.settingsMsg = (window.t ? window.t('dialog.profileIdExists', { id }) : 'Bu ID zaten var: ' + id);
        return;
      }
      this.hardwareConfig.profiles.push({
        id,
        device_name: window.t ? window.t('dialog.newDevice', { id }) : 'Yeni cihaz (' + id + ')',
        cpu: '', gpu: '',
        vram_gb: 8, ram_gb: 16,
        npu_tops: null, storage_gb: null, os: '', cuda_version: '',
      });
      this.hardwareConfig.active_profile = id;
      await this._persistHardwareConfig();
      this._syncSettingsForm(this.profiles.find(p => p.id === id));
      this.settingsMsg = window.t ? window.t('dialog.settingsMsg.profileAdded', { id }) : '✓ Yeni profil eklendi: ' + id;
      setTimeout(() => { this.settingsMsg = ''; }, 3000);
    },

    async deleteProfile(profileId) {
      if (!this.hardwareConfig) return;
      if (this.hardwareConfig.profiles.length <= 1) {
        this.settingsMsg = window.t ? window.t('dialog.settingsMsg.atLeastOne') : 'En az bir profil kalmalı.';
        return;
      }
      if (!confirm(window.t ? window.t('dialog.deleteProfile', { id: profileId }) : 'Bu profili silmek istediğinize emin misiniz? (' + profileId + ')')) return;
      const wasActive = this.hardwareConfig.active_profile === profileId;
      this.hardwareConfig.profiles = this.hardwareConfig.profiles.filter(p => p.id !== profileId);
      if (wasActive) {
        this.hardwareConfig.active_profile = this.hardwareConfig.profiles[0].id;
      }
      await this._persistHardwareConfig();
      this._syncSettingsForm(this.profiles.find(p => p.id === this.hardwareConfig.active_profile));
      this.settingsMsg = window.t ? window.t('dialog.settingsMsg.profileDeleted') : '✓ Profil silindi.';
      setTimeout(() => { this.settingsMsg = ''; }, 3000);
    },

    async saveThresholds() {
      if (!this.hardwareConfig) return;
      this.hardwareConfig.tier_thresholds = {
        vram_full_margin: Number(this.thresholdsForm.vram_full_margin),
        ram_full_margin: Number(this.thresholdsForm.ram_full_margin),
        vram_caution_margin: Number(this.thresholdsForm.vram_caution_margin),
      };
      await this._persistHardwareConfig();
      this.settingsMsg = window.t ? window.t('dialog.settingsMsg.thresholdsSaved') : '✓ Tier eşik değerleri kaydedildi.';
      setTimeout(() => { this.settingsMsg = ''; }, 3000);
    },

    resetThresholds() {
      this.thresholdsForm = { vram_full_margin: 2.0, ram_full_margin: 4.0, vram_caution_margin: -1.5 };
      this.settingsMsg = window.t ? window.t('dialog.settingsMsg.thresholdsReset') : 'Eşik değerleri varsayılana sıfırlandı (Kaydet\'e basın).';
    },

    onProfileSelectChange() {
      // select değişince hem aktif profile geç hem formu doldur
      const id = this.hardwareConfig.active_profile;
      const profile = this.profiles.find(p => p.id === id);
      this._syncSettingsForm(profile);
      // Aktif profile değişikliğini backend'e de yaz
      this._persistHardwareConfig();
    },
};
