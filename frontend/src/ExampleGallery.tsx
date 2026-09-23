// Загружается только при явном ?examples=1. Никогда не используется как fallback API.
import { useState } from 'react';
import contractExamples from '../../docs/examples/responses.json';
import type { RecommendResponse } from './contracts';
import { ApiError } from './api-client';
import { ErrorPanel } from './ErrorPanel';
import { ResultPanel } from './ResultPanel';

const examples = contractExamples.recommend as RecommendResponse[];
const base = examples[0];
const flags: RecommendResponse = {
  ...base, eligible_count: 4, total_candidates: 4,
  message: 'Учебный пример: подходят 4 профиля, показаны первые 3. Метки демонстрируют происхождение данных.',
  cards: [
    { ...base.cards[0], id: 'UI-EXAMPLE-1', name: 'Учебный профиль · исходный', origin: 'source_original', synthetic: false, city_imputed: true, price_imputed: true },
    { ...base.cards[0], id: 'UI-EXAMPLE-2', name: 'Учебный профиль · синтетика организаторов' },
    { ...base.cards[0], id: 'UI-EXAMPLE-3', name: 'Учебный профиль · добавлен командой', origin: 'team_synthetic' },
  ],
  diagnostics: { ...base.diagnostics, filters: base.diagnostics.filters.map(step => ({ ...step, remaining_count: 4 })) },
};
const quote = 'Провожу камерные корпоративы с интеллектуальными викторинами.';
const prepared: RecommendResponse = {
  ...base, explanation_mode: 'prepared',
  cards: [{ ...base.cards[0], explanation: 'Принимает корпоративы на русском языке; стартовая цена — от 100 000 ₸. В описании: «Провожу камерные корпоративы с интеллектуальными викторинами».',
    evidence: [...base.cards[0].evidence, { source: 'prepared', field: 'description', value: quote, quote }] }],
  diagnostics: { ...base.diagnostics, warnings: ['Учебный пример: подготовленная цитата вымышленного профиля, реальная модель не вызывалась.'] },
};
const kinds = [
  ['matched', 'Подобрали'], ['category_absent', 'Нет категории'], ['no_match', 'Никто не подходит'],
  ['flags', 'Три карточки и метки'], ['prepared', 'Подготовленные признаки'], ['dates', 'Смена даты'],
  ['422', 'Ошибка 422'], ['503', 'Ошибка 503'], ['501', 'Ошибка 501'],
  ['network', 'Нет соединения'], ['timeout', 'Тайм-аут'], ['loading', 'Загрузка'],
] as const;

export default function ExampleGallery() {
  const [selected, setSelected] = useState<string>('matched');
  const response = selected === 'flags' ? flags : selected === 'prepared' ? prepared
    : selected === 'dates' ? examples[2] : examples.find(item => item.status === selected);
  const errors: Record<string, ApiError> = {
    '422': new ApiError('Проверьте параметры запроса.', 422, 'validation_error', [{ field: 'body.date', message: 'Дата должна быть в диапазоне 2026-09-23 — 2026-12-31.' }]),
    '503': new ApiError('Каталог недоступен. Требуется исправить данные.', 503, 'dataset_invalid', [{ line: 2, id: 'TEST-001', message: 'Неверное значение поля synthetic.' }]),
    '501': new ApiError(contractExamples.error.error.message, 501, 'not_implemented'),
    network: new ApiError('Не удалось соединиться с сервером. Проверьте соединение и повторите запрос.'),
    timeout: new ApiError('Сервер не ответил за 15 секунд. Повторите запрос.', null, 'timeout'),
  };
  return <>
    <section className="fixture-banner" aria-label="Учебный режим"><strong>Тестовые данные</strong>
      <p>Галерея состояний интерфейса. Профили вымышлены, запросы в API не отправляются. Это не рекомендации из реального каталога.</p>
      <a href={window.location.pathname}>Вернуться к настоящему подбору →</a></section>
    <div className="example-controls" aria-label="Выбор учебного состояния">{kinds.map(([key, label]) =>
      <button className="secondary" type="button" aria-pressed={selected === key} key={key} onClick={() => setSelected(key)}>{label}</button>)}</div>
    <div aria-live="polite">
      {response && <ResultPanel result={response} previous={selected === 'dates' ? examples[0] : null} />}
      {errors[selected] && <ErrorPanel error={errors[selected]} />}
      {selected === 'loading' && <p className="loading-status" role="status"><span className="spinner" aria-hidden="true" />Учебный пример ожидания ответа. Выберите другое состояние, чтобы продолжить.</p>}
    </div>
  </>;
}
