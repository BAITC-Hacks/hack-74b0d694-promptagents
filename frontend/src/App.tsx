import { useEffect, useRef, useState, type FormEvent } from 'react';
import { getOptions, recommend } from './api';
import type { OptionsResponse, RecommendResponse } from './contracts';
import { demoPresets } from './demo-presets';

export function App() {
  const [options, setOptions] = useState<OptionsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<RecommendResponse | null>(null);
  const [attempt, setAttempt] = useState(0);
  const formRef = useRef<HTMLFormElement>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    getOptions().then(value => { if (active) setOptions(value); })
      .catch(err => { if (active) setError(err.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [attempt]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    setSending(true);
    setError('');
    setResult(null);
    try {
      setResult(await recommend({
        city: String(fields.get('city')),
        date: String(fields.get('date')),
        category: String(fields.get('category')),
        event_format: String(fields.get('event_format')),
        budget_kzt: Number(fields.get('budget_kzt')),
        duration_hours: fields.get('duration_hours') ? Number(fields.get('duration_hours')) : null,
        language: fields.get('language') ? String(fields.get('language')) : null,
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось выполнить запрос');
    } finally {
      setSending(false);
    }
  }

  return <main>
    <header><p className="eyebrow">PromptAgents · Хакатон</p>
      <h1>Подрядчики под ваше мероприятие</h1>
      <p>До трёх рекомендаций с объяснением соответствия вашим условиям.</p>
    </header>
    <p className="notice">Каркас проекта: форма и загрузка каталога готовы, подбор ещё не реализован.</p>
    {loading && <p role="status">Загружаем параметры каталога…</p>}
    {error && <div role="alert" className="error"><p>{error}</p>
      {!options && <button onClick={() => setAttempt(value => value + 1)} disabled={loading}>Повторить загрузку</button>}
    </div>}
    <section aria-label="Демосценарии">
      <p>Проверенные параметры демо. Кнопки заполняют форму и отправляют запрос в API; сейчас API явно отвечает, что подбор ещё не реализован.</p>
      <div className="demos">{demoPresets.map(preset => <button type="button" key={preset.label}
        disabled={!options || loading || sending} onClick={() => {
          const form = formRef.current;
          if (!form) return;
          form.reset();
          for (const [key, value] of Object.entries(preset.request)) {
            const input = form.elements.namedItem(key);
            if (input instanceof HTMLInputElement || input instanceof HTMLSelectElement) {
              input.value = value == null ? '' : String(value);
            }
          }
          form.requestSubmit();
        }}>{preset.label}</button>)}</div>
    </section>
    <form onSubmit={submit} ref={formRef}>
      <fieldset disabled={!options || loading || sending}>
        <legend>Условия заказа</legend>
        <div className="fields">
          <label>Город<select name="city" required defaultValue=""><option value="" disabled>Выберите город</option>
            {options?.cities.map(value => <option key={value}>{value}</option>)}</select></label>
          <label>Дата мероприятия<input name="date" type="date" required min={options?.date_range.min} max={options?.date_range.max} /></label>
          <label>Тип мероприятия<select name="event_format" required defaultValue=""><option value="" disabled>Выберите формат</option>
            {options?.event_formats.map(value => <option key={value}>{value}</option>)}</select></label>
          <label>Категория<select name="category" required defaultValue=""><option value="" disabled>Выберите категорию</option>
            {options?.categories.map(value => <option key={value}>{value}</option>)}</select></label>
          <label>Бюджет, ₸<input name="budget_kzt" type="number" min="0.01" step="0.01" required placeholder="Ваш бюджет" /></label>
          <label>Длительность, ч (необязательно)<input name="duration_hours" type="number" min="0.01" step="0.01" /></label>
          <label>Язык (необязательно)<select name="language" defaultValue=""><option value="">Без предпочтений</option>
            {options?.languages.map(value => <option key={value}>{value}</option>)}</select></label>
        </div>
        <p className="hint">Календарь: 23 сентября — 31 декабря 2026. Цена в каталоге — стартовая; итоговая стоимость требует уточнения.</p>
        <button type="submit">{sending ? 'Подбираем…' : 'Подобрать подрядчиков'}</button>
      </fieldset>
    </form>
    {result && <section aria-live="polite"><h2>Ответ сервиса</h2><p>{result.message}</p>
      <p>Найдено подходящих: {result.eligible_count}. Отображение карточек — следующий этап инженера №2.</p>
    </section>}
  </main>;
}
