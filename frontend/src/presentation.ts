import type { Diagnostics, Evidence, RecommendRequest, RecommendResponse } from './contracts';

export const money = (value: number) => `${new Intl.NumberFormat('ru-KZ', { maximumFractionDigits: 2 }).format(value)} ₸`;
export const dateLabel = (value: string) => /^\d{4}-\d{2}-\d{2}$/.test(value)
  ? value.split('-').reverse().join('.') : value;

export const fieldLabels: Record<string, string> = {
  city: 'Город', category: 'Категория', date: 'Дата', budget_kzt: 'Бюджет',
  duration_hours: 'Длительность', language: 'Язык', price_from_kzt: 'Стартовая цена',
  event_format: 'Формат', event_formats: 'Форматы', languages: 'Языки',
  max_hours: 'Время на площадке', busy_dates: 'Занятые даты', description: 'Описание',
  categories: 'Категории', anon_name: 'Имя', id: 'ID',
};
export const reasonLabels: Record<Diagnostics['filters'][number]['reason'], string> = {
  busy: 'Заняты на выбранную дату', budget: 'Стартовая цена выше бюджета',
  format: 'Не принимают этот формат', language: 'Не работают на выбранном языке',
  duration: 'Длительность превышает лимит',
};
export const originLabels = {
  source_original: 'Исходный каталог', source_synthetic: 'Синтетика организаторов', team_synthetic: 'Добавлен командой',
};

export function evidenceValue(item: Evidence): string {
  if (item.value === null) return item.field === 'max_hours' ? 'Не привязано к присутствию на площадке' : 'Не указано';
  if (item.field === 'price_from_kzt' && typeof item.value === 'number') return `от ${money(item.value)}`;
  if (Array.isArray(item.value)) return item.value.length ? item.value.map(value => typeof value === 'object' ? JSON.stringify(value) : String(value)).join(', ') : 'Пустой список';
  return typeof item.value === 'object' ? JSON.stringify(item.value) : String(item.value);
}

function sameConditions(a: RecommendRequest, b: RecommendRequest) {
  // Сравниваем нормализованные значения из ответов backend, не форму и не локальную эвристику.
  return a.city === b.city && a.category === b.category && a.event_format === b.event_format
    && a.budget_kzt === b.budget_kzt && (a.language ?? null) === (b.language ?? null)
    && (a.duration_hours ?? null) === (b.duration_hours ?? null)
    && (a.preferences_text ?? null) === (b.preferences_text ?? null)
    && JSON.stringify(Object.entries(a.preferences ?? {}).sort()) === JSON.stringify(Object.entries(b.preferences ?? {}).sort());
}

function proof(response: RecommendResponse, id: string) {
  return response.diagnostics.busy_profiles.find(item => item.id === id
    && item.date === response.normalized_request.date && item.evidence.source === 'profile'
    && item.evidence.field === 'busy_dates' && Array.isArray(item.evidence.value)
    && item.evidence.value.includes(item.date));
}

export function compareDates(previous: RecommendResponse | null, current: RecommendResponse): string[] | null {
  if (!previous || previous.data_version !== current.data_version
    || previous.feature_version !== current.feature_version || previous.ranking_version !== current.ranking_version
    || previous.normalized_request.date === current.normalized_request.date
    || !sameConditions(previous.normalized_request, current.normalized_request)) return null;
  const messages: string[] = [];
  for (const card of previous.cards) {
    if (current.cards.some(item => item.id === card.id)) continue;
    messages.push(proof(current, card.id)
      ? `${card.name}: занят ${dateLabel(current.normalized_request.date)} — дата подтверждена календарём.`
      : `${card.name} больше не отображается в первых трёх. Подтверждения занятости на новую дату в ответе нет.`);
  }
  for (const card of current.cards) {
    if (previous.cards.some(item => item.id === card.id)) continue;
    messages.push(proof(previous, card.id)
      ? `${card.name}: был занят ${dateLabel(previous.normalized_request.date)} по календарю; на новую дату включён в рекомендации.`
      : `${card.name} появился в первых трёх. Причину прежнего отсутствия нельзя установить только по карточкам.`);
  }
  if (!messages.length) messages.push('Состав отображаемых карточек не изменился. Порядок и общее число подходящих могут отличаться.');
  return messages;
}
