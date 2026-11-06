/* BenchCompass — metin/biçim ve not yardımcıları (ES modülü)
 *
 * web/app.js'ten ayrıldı (2026-11-05, Faz 2 modülerleştirme).
 * Alpine şablonları bu fonksiyonları global olarak kullanır; app.js bunları
 * `window.*` üzerine bağlar. Testler gerçek ESM import'u kullanır (Y10).
 */

export function esc(s = '') {
  return String(s).replace(/[&<>"']/g, m => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[m]));
}

export function ctx(v) {
  if (!v) return '-';
  if (v >= 1e6) return (v / 1e6).toFixed(v % 1e6 === 0 ? 0 : 1) + 'M';
  if (v >= 1e3) return Math.round(v / 1e3) + 'K';
  return String(v);
}

export function shortModelName(full) {
  if (!full) return '-';
  const max = 32;
  return full.length <= max ? full : full.slice(0, max) + '…';
}

/** notes metnini madde listesi için array'e çevirir (Bölüm 3). */
export function renderNotesParts(raw) {
  if (!raw) return [];
  let txt;
  if (Array.isArray(raw)) {
    try { txt = JSON.stringify(raw); } catch { txt = String(raw); }
  } else {
    txt = String(raw);
  }
  // Aynı ayırıcı mantığı mevcut renderNotesList ile
  return txt.split(/"?,\s*"|; |\n/).map(p => p.trim().replace(/^"|"$/g, '')).filter(Boolean);
}

/** notes'tan loaded_into_vram / insufficient boolean'larını çıkar
 *  (compute_tier'in not-bazlı ipuçları için). */
export function parseNotesFlags(raw) {
  let txt = '';
  if (Array.isArray(raw) || (raw && typeof raw === 'object')) {
    try { txt = JSON.stringify(raw).toLowerCase(); } catch { txt = ''; }
  } else if (raw) {
    txt = String(raw).toLowerCase();
  }
  return {
    loaded_into_vram: /loaded\s+into\s+vram/.test(txt),
    insufficient: /insufficient\s+vram/.test(txt),
  };
}

// --- GPU telemetri format helper'ları (Sprint 44) ---------------------------
export function fmtMb(mb) {
  if (mb == null) return '-';
  return (mb / 1024).toFixed(1) + ' GB';
}

export function fmtW(w) {
  if (w == null) return '-';
  return Math.round(w) + ' W';
}

export function fmtPct(p) {
  if (p == null) return '-';
  return (typeof p === 'number' ? p.toFixed(0) : p) + '%';
}
