/* BenchCompass — değerlendirme (kalite) yardımcıları ve grafik veri adaptörü
 *
 * web/app.js'ten ayrıldı (2026-11-05, Faz 2 modülerleştirme).
 */

/**
 * Kalite kaydı geçerli mi? (`gecerlilik='artefakt-g7'` = harness artefaktı.)
 *
 * 6 Ekim 2026: G7 test modülü iki isim import ederken prompt tek fonksiyon
 * istiyordu → collection `ImportError` → doğru cevap "başarısız" sayıldı.
 * Bu satırlar SİLİNMEZ, panelde işaretlenir (bkz. lessons-learned-2026-10-07).
 * NULL değer backend ile aynı şekilde 'gecerli' kabul edilir.
 */
export function evalGecerliMi(kayit) {
  if (!kayit) return false;
  return (kayit.gecerlilik || 'gecerli') !== 'artefakt-g7';
}

/**
 * Kaydın tok/s değeri GÜVENİLİR mi?
 *
 * `char_tahmin` kaynaklı kayıtlar (bonsai2/freetoken: fork/usage dönmediği için
 * karakter sayımıyla tahmin) 433/340 tok/s gibi sahte hız üretir. Panel hızı
 * yalnız SUNUCUNUN ölçtüğü decode süresine dayanan kaynaklarda gösterir:
 * `eval_duration` (Ollama) / `usage` (OpenAI uyumlu) / `timings`
 * (llama.cpp /completion `timings.predicted_per_second`); diğerlerinde '—' basar.
 */
export function evalTgGuvenilirMi(kayit) {
  if (!kayit) return false;
  return (
    kayit.tg_kaynagi === 'eval_duration' ||
    kayit.tg_kaynagi === 'usage' ||
    kayit.tg_kaynagi === 'timings'
  );
}

/**
 * `/api/grafiks/ekstra` ham yanıtını chart-ready veri yapısına çevirir.
 * 5 grafiği (radar/scatter/fit_level/moe/caps) besler. Boş/eksik bölümler
 * güvenli şekilde sıfırlanır; `hasData=false` olduğunda UI boş-state gösterir.
 */
export function prepareExtraChartData(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const radar = (raw.score_components_radar || []).slice(0, 5).map(m => ({
    name: m.name || '-',
    fit: m.fit ?? 0,
    quality: m.quality ?? 0,
    speed: m.speed ?? 0,
    context: m.context ?? 0,
  }));
  const scatter = (raw.param_speed_scatter || []).map(p => ({
    x: p.p,
    y: p.s,
    name: p.n || '',
  }));
  const fitLevel = raw.fit_level_distribution || {};
  const moeTrend = (raw.moe_trend || []).map(r => ({
    run: r.run || '',
    total: r.total || 0,
    moe: r.moe || 0,
    pct: r.pct ?? 0,
  }));
  const caps = raw.capabilities_pie || {};
  const hasData =
    radar.length > 0 ||
    scatter.length > 0 ||
    Object.keys(fitLevel).length > 0 ||
    moeTrend.length > 0 ||
    Object.keys(caps).length > 0;
  return { radar, scatter, fitLevel, moeTrend, caps, hasData };
}
