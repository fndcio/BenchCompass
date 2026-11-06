/* BenchCompass — demo veri kümesi (dashboard fallback)
 *
 * web/app.js'ten ayrıldı (2026-11-05, Faz 2 modülerleştirme).
 * Yalnızca backend verisi yoksa kullanılır; `source: 'demo-db'` etiketi korunur.
 */

export const demoDb = {
  latest: {
    source: 'demo-db',
    models: [
      { name: 'Hy3', provider: 'OpenRouter', useCase: 'coding', fitScore: 92, contextWindow: 262000, notes: 'nightly winner' },
      { name: 'DeepSeek V4 Flash', provider: 'OpenRouter', useCase: 'coding', fitScore: 89, contextWindow: 1048576, notes: 'large context' },
      { name: 'MiMo V2.5', provider: 'OpenRouter', useCase: 'chat', fitScore: 81, contextWindow: 1000000, notes: 'chat stable' },
    ],
  },
  history: [
    { id: 1, name: 'nightly-coding-1', created_at: '2026-07-17 02:00', source: 'demo-db', use_case: 'coding', models: [{ name: 'Hy3', fitScore: 88 }, { name: 'DeepSeek V4 Flash', fitScore: 86 }] },
    { id: 2, name: 'nightly-coding-2', created_at: '2026-07-18 02:00', source: 'demo-db', use_case: 'coding', models: [{ name: 'Hy3', fitScore: 91 }, { name: 'DeepSeek V4 Flash', fitScore: 87 }] },
    { id: 3, name: 'nightly-chat-1', created_at: '2026-07-18 09:00', source: 'demo-db', use_case: 'chat', models: [{ name: 'MiMo V2.5', fitScore: 79 }, { name: 'Hy3', fitScore: 75 }] },
    { id: 4, name: 'nightly-coding-3', created_at: '2026-07-19 02:00', source: 'demo-db', use_case: 'coding', models: [{ name: 'Hy3', fitScore: 92 }, { name: 'DeepSeek V4 Flash', fitScore: 89 }, { name: 'North Mini Code', fitScore: 84 }] },
    { id: 5, name: 'nightly-chat-2', created_at: '2026-07-19 09:00', source: 'demo-db', use_case: 'chat', models: [{ name: 'MiMo V2.5', fitScore: 81 }, { name: 'Hy3', fitScore: 76 }] },
  ],
};
