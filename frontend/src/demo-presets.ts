import type { RecommendRequest } from './contracts';

// Только входные параметры. Никаких заранее сохранённых ответов или ID.
const host = { city: 'Алматы', category: 'Ведущий', event_format: 'корпоратив',
  budget_kzt: 1000000, language: 'русский', duration_hours: 6 };
export const demoPresets: { label: string; request: RecommendRequest }[] = [
  { label: '1. Ведущие · 10 октября', request: { ...host, date: '2026-10-10' } },
  { label: '2. Ведущие · 11 октября', request: { ...host, date: '2026-10-11' } },
  { label: '3. Флористы · 11 октября', request: { city: 'Алматы', category: 'Флорист',
    date: '2026-10-11', event_format: 'свадьба', budget_kzt: 300000, language: 'русский', duration_hours: 8 } },
  { label: '4. Нет категории в городе', request: { city: 'Астана', category: 'Декоратор',
    date: '2026-10-10', event_format: 'свадьба', budget_kzt: 500000 } },
  { label: '5. Нет подходящих · декабрь', request: { ...host, date: '2026-12-12' } },
  { label: '6. Банкетный зал · 14 ноября', request: { city: 'Алматы', category: 'Банкетный зал',
    date: '2026-11-14', event_format: 'свадьба', budget_kzt: 3000000 } },
];
