import { lazy, Suspense, useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError, asApiError, getHealth, getOptions, recommend } from './api-client';
import type { HealthResponse, OptionsResponse, RecommendRequest, RecommendResponse } from './contracts';
import { demoPresets } from './demo-presets';
import { ErrorPanel } from './ErrorPanel';
import { ResultPanel } from './ResultPanel';

const ExampleGallery = lazy(() => import('./ExampleGallery'));
const examplesMode = new URLSearchParams(window.location.search).get('examples') === '1';

export function App() {
  return <>
    <a className="skip-link" href="#content">Перейти к содержимому</a>
    <header className="site-header"><a className="brand" href={window.location.pathname}><span className="brand-mark" aria-hidden="true">P</span>PromptAgents</a>
      <span className="header-note">События начинаются с людей</span></header>
    <main id="content">
      <div className="intro"><p className="eyebrow">Подбор подрядчиков · Казахстан</p>
        <h1>Ваше событие.<br /><span>Подходящие люди.</span></h1>
        <p className="lead">Задайте условия — получите до трёх рекомендаций с понятным объяснением каждого выбора.</p></div>
      {examplesMode ? <Suspense fallback={<p role="status">Загружаем учебные примеры…</p>}><ExampleGallery /></Suspense> : <LiveSearch />}
    </main>
    <footer className="site-footer"><span>PromptAgents · Хакатон</span>{!examplesMode && <a href="?examples=1">Открыть учебные примеры интерфейса</a>}</footer>
  </>;
}

function LiveSearch() {
  const [options, setOptions] = useState<OptionsResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthUnavailable, setHealthUnavailable] = useState(false);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [optionsError, setOptionsError] = useState<ApiError | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [result, setResult] = useState<RecommendResponse | null>(null);
  const [previous, setPrevious] = useState<RecommendResponse | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [cancelled, setCancelled] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  const outputRef = useRef<HTMLElement>(null);
  const pending = useRef<AbortController | null>(null);
  const sequence = useRef(0);
  const lastSuccessful = useRef<RecommendResponse | null>(null);
  const lastRequest = useRef<RecommendRequest | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setOptionsError(null);
    setHealthUnavailable(false);
    getOptions(controller.signal).then(value => {
      if (!controller.signal.aborted) setOptions(value);
    }).catch(err => {
      if (!controller.signal.aborted) { setOptions(null); setOptionsError(asApiError(err)); }
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    getHealth(controller.signal).then(value => {
      if (!controller.signal.aborted) setHealth(value);
    }).catch(() => { if (!controller.signal.aborted) { setHealth(null); setHealthUnavailable(true); } });
    return () => controller.abort();
  }, [attempt]);

  useEffect(() => () => { sequence.current++; pending.current?.abort(); }, []);
  useEffect(() => { if (result || error) outputRef.current?.focus(); }, [result, error]);

  function cancel() {
    sequence.current++;
    pending.current?.abort();
    pending.current = null;
    setSending(false);
  }

  function edit() {
    cancel();
    setResult(null);
    setError(null);
    setCancelled(false);
    lastRequest.current = null;
  }

  async function send(input: RecommendRequest) {
    cancel();
    const requestNumber = sequence.current;
    const controller = new AbortController();
    pending.current = controller;
    lastRequest.current = input;
    setSending(true);
    setCancelled(false);
    setError(null);
    setResult(null);
    try {
      const response = await recommend(input, controller.signal);
      if (sequence.current !== requestNumber || controller.signal.aborted) return;
      setPrevious(lastSuccessful.current);
      lastSuccessful.current = response;
      setResult(response);
      // Снимок health обновляем отдельно; успешный ответ сам по себе не подменяет health.
      getHealth(controller.signal).then(value => {
        if (sequence.current === requestNumber && !controller.signal.aborted) setHealth(value);
      }).catch(() => {});
    } catch (err) {
      if (sequence.current === requestNumber && !controller.signal.aborted) setError(asApiError(err));
    } finally {
      if (sequence.current === requestNumber) setSending(false);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const budget = Number(fields.get('budget_kzt'));
    const duration = fields.get('duration_hours') ? Number(fields.get('duration_hours')) : null;
    if (!Number.isFinite(budget) || budget <= 0 || (duration !== null && (!Number.isFinite(duration) || duration <= 0))) {
      cancel();
      setResult(null);
      lastRequest.current = null;
      setError(new ApiError('Бюджет и заданная длительность должны быть положительными числами.', 422, 'validation_error'));
      return;
    }
    void send({
      city: String(fields.get('city')), date: String(fields.get('date')),
      category: String(fields.get('category')), event_format: String(fields.get('event_format')),
      budget_kzt: budget, duration_hours: duration,
      language: fields.get('language') ? String(fields.get('language')) : null,
    });
  }

  function runDemo(input: RecommendRequest) {
    const form = formRef.current;
    if (!form) return;
    form.reset();
    for (const [key, value] of Object.entries(input)) {
      const element = form.elements.namedItem(key);
      if (element instanceof HTMLInputElement || element instanceof HTMLSelectElement) element.value = value == null ? '' : String(value);
    }
    // Native validation тоже действует для демо; ответ всегда приходит из API.
    form.requestSubmit();
  }

  return <>
    {health?.recommendation_implemented === false && <div className="notice service-notice"><strong>Подбор в разработке</strong>
      <p>Каталог и форма доступны. Сервис пока не формирует рекомендации; при отправке он сообщит об этом.</p></div>}
    {healthUnavailable && <p className="hint">Не удалось проверить готовность сервиса. <button className="text-button" onClick={() => setAttempt(value => value + 1)}>Проверить ещё раз</button></p>}
    {optionsError && <ErrorPanel error={optionsError} retry={() => setAttempt(value => value + 1)} />}
    <div className="search-layout">
      <section className="form-panel" aria-label="Параметры мероприятия">
        <div className="section-top"><span className="step-number">01</span><h2>Расскажите о событии</h2></div>
        {loading && <p role="status">Загружаем параметры каталога…</p>}
        <form onSubmit={submit} ref={formRef} onChange={edit}>
          <fieldset disabled={!options || loading}><legend className="sr-only">Условия заказа</legend>
            <div className="fields">
              <label>Город<select name="city" required defaultValue=""><option value="" disabled>Выберите город</option>
                {options?.cities.map(value => <option key={value}>{value}</option>)}</select></label>
              <label>Дата мероприятия<input name="date" type="date" required min={options?.date_range.min ?? '2026-09-23'} max={options?.date_range.max ?? '2026-12-31'} aria-describedby="calendar-help" /></label>
              <label>Тип мероприятия<select name="event_format" required defaultValue=""><option value="" disabled>Выберите формат</option>
                {options?.event_formats.map(value => <option key={value}>{value}</option>)}</select></label>
              <label>Категория подрядчика<select name="category" required defaultValue=""><option value="" disabled>Выберите категорию</option>
                {options?.categories.map(value => <option key={value}>{value}</option>)}</select></label>
              <label>Бюджет, ₸<input name="budget_kzt" type="number" min="0" step="any" required placeholder="Например, 300 000" /></label>
              <label>Длительность, ч <span className="optional">необязательно</span><input name="duration_hours" type="number" min="0" step="any" placeholder="Например, 6" /></label>
              <label>Язык <span className="optional">необязательно</span><select name="language" defaultValue=""><option value="">Без предпочтений</option>
                {options?.languages.map(value => <option key={value}>{value}</option>)}</select></label>
            </div>
            <p id="calendar-help" className="hint">Календарь: 23 сентября — 31 декабря 2026. Цена в каталоге стартовая; итоговую стоимость нужно уточнить.</p>
            <div className="form-actions"><button className="primary" type="submit">{sending ? 'Отправить заново' : 'Подобрать подрядчиков'} <span aria-hidden="true">→</span></button>
              {sending && <button type="button" className="secondary" onClick={() => { cancel(); setCancelled(true); }}>Отменить</button>}</div>
          </fieldset>
        </form>
      </section>
      <aside className="demo-panel"><p className="eyebrow">Попробуйте на примерах</p><h2>Шесть реальных сценариев</h2>
        <p className="hint">Каждая кнопка заполнит форму и отправит запрос с выбранными условиями.</p>
        <div className="demos">{demoPresets.map(preset => <button type="button" key={preset.label} disabled={!options || loading}
          onClick={() => runDemo(preset.request)}>{preset.label}<span aria-hidden="true">↗</span></button>)}</div>
        <p className="demo-footnote">Все категории доступны для любого города — в том числе когда такой категории в нём нет.</p>
      </aside>
    </div>
    <section className="output" ref={outputRef} tabIndex={-1} aria-label="Результат запроса" aria-busy={sending}>
      {sending && <p className="loading-status" role="status"><span className="spinner" aria-hidden="true" />Проверяем условия. Можно изменить параметры или отменить запрос.</p>}
      {cancelled && <p role="status">Запрос отменён. Можно начать новый подбор.</p>}
      {error && <ErrorPanel error={error} retry={lastRequest.current ? () => { if (lastRequest.current) void send(lastRequest.current); } : undefined} />}
      {result && <><p className="sr-only" role="status">Подбор завершён. Подходящих: {result.eligible_count}.</p><ResultPanel result={result} previous={previous} /></>}
      {!sending && !error && !result && !cancelled && <div className="initial-state"><span className="step-number">02</span><h2>Здесь появятся рекомендации</h2><p>Заполните условия или выберите один из сценариев. Мы покажем результат и основания выбора.</p></div>}
    </section>
  </>;
}
