import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import '../../web/app.js';

describe('Tema yönetimi (Sprint 18 — light mod düzeltmesi)', () => {
  let d;

  beforeEach(() => {
    localStorage.clear();
    d = dashboard();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('applyTheme', () => {
    it('documentElement data-theme attribute set eder', () => {
      d.theme = 'light';
      d.applyTheme();
      expect(document.documentElement.getAttribute('data-theme')).toBe('light');
    });

    it('dark tema attribute set eder', () => {
      d.theme = 'dark';
      d.applyTheme();
      expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    });
  });

  describe('toggleTheme', () => {
    it('dark moddan light moda gecer ve attribute guncellenir', () => {
      d.theme = 'dark';
      d.toggleTheme();
      expect(d.theme).toBe('light');
      expect(document.documentElement.getAttribute('data-theme')).toBe('light');
    });

    it('light moddan dark moda gecer', () => {
      d.theme = 'light';
      d.toggleTheme();
      expect(d.theme).toBe('dark');
      expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    });

    it('tercihi localStorage a kaydeder', () => {
      d.theme = 'dark';
      d.toggleTheme();
      expect(localStorage.getItem('benchcompass-theme')).toBe('light');
    });
  });

  describe('themeIcon', () => {
    it('dark modda gunes ikonu gosterir', () => {
      d.theme = 'dark';
      expect(d.themeIcon).toBe('☀️');
    });

    it('light modda ay ikonu gosterir', () => {
      d.theme = 'light';
      expect(d.themeIcon).toBe('🌙');
    });
  });
});
