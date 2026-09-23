import type { Card, Evidence, RecommendResponse } from './contracts';
import { compareDates, dateLabel, evidenceValue, fieldLabels, money, originLabels, reasonLabels } from './presentation';

function EvidenceList({ items }: { items: Evidence[] }) {
  return <ul className="evidence-list">{items.map((item, index) => <li key={`${item.field}-${index}`}>
    <strong>{fieldLabels[item.field] ?? item.field}</strong>
    <span className="source-label">{item.source === 'profile' ? 'Поле каталога' : item.source === 'prepared' ? 'Подготовленный признак с цитатой' : 'Описание профиля'}</span>
    {item.quote && <blockquote>{item.quote}</blockquote>}
    <p className="source-value">{evidenceValue(item)}</p>
  </li>)}</ul>;
}

function ContractorCard({ card, rank, alternativeDate }: { card: Card; rank?: number; alternativeDate?: string }) {
  return <article className={`contractor-card${alternativeDate ? ' alternative-card' : ''}`}
    aria-label={alternativeDate ? `${card.name} — предложение на ${dateLabel(alternativeDate)}` : card.name}>
      <div className="card-top"><span className="rank">{alternativeDate ? 'Другая дата' : String(rank).padStart(2, '0')}</span><span className="hint">{card.category} · {card.city}</span></div>
      <h3>{card.name}</h3><p className="price">от {money(card.price_from_kzt)}</p>
      <div className="tags"><span>{originLabels[card.origin]}</span>
        {card.synthetic && <span>Синтетический профиль</span>}
        {card.city_imputed && <span>Город указан при подготовке данных</span>}
        {card.price_imputed && <span>Цена указана при подготовке данных</span>}
      </div>
      <div className="explanation"><h4>{alternativeDate ? `Почему подходит на ${dateLabel(alternativeDate)}` : 'Почему подходит'}</h4><p>{card.explanation}</p></div>
      <details><summary>На чём основано объяснение</summary><EvidenceList items={card.evidence} /></details>
    </article>;
}

export function ResultPanel({ result, previous = null }: { result: RecommendResponse; previous?: RecommendResponse | null }) {
  const comparison = compareDates(previous, result);
  const input = result.normalized_request;
  const alternative = result.status === 'no_match' && result.alternative?.date !== input.date
    ? result.alternative : null;
  const headings = { matched: 'Подрядчики под ваши условия', category_absent: 'В этом городе нет такой категории', no_match: 'Никто не прошёл все условия' };
  return <div className={`result-panel ${result.status}`}>
    <div className="result-heading"><div><p className="eyebrow">Результат подбора</p><h2>{headings[result.status]}</h2></div>
      <span className="count-badge">Подходящих: {result.eligible_count}</span></div>
    <p className="request-summary">{input.city} · {input.category} · {dateLabel(input.date)} · {input.event_format} · бюджет {money(input.budget_kzt)}
      {input.language && ` · ${input.language}`}{input.duration_hours != null && ` · ${input.duration_hours} ч`}</p>
    <p className="server-message">{result.message}</p>
    <p className="hint">Кандидатов в категории и городе: {result.total_candidates}. Показано: {Math.min(result.cards.length, 3)} из {result.eligible_count} подходящих.</p>
    <div className="cards">{result.cards.slice(0, 3).map((card, index) =>
      <ContractorCard card={card} rank={index + 1} key={card.id} />)}</div>
    {alternative && <section className="alternative-date" aria-label="Предложение на другую дату">
      <h3>Ближайшая подходящая дата — <time dateTime={alternative.date}>{dateLabel(alternative.date)}</time></h3>
      <p>На {dateLabel(input.date)} подходящих подрядчиков нет. Эта карточка относится только к {dateLabel(alternative.date)}.
        {' '}Город, категория, бюджет, формат, язык и длительность сохранены.</p>
      <ContractorCard card={alternative.card} alternativeDate={alternative.date} />
      <p className="hint">{alternative.explanation_mode === 'prepared'
        ? 'Объяснение предложения использует заранее подготовленные AI-признаки с доказательствами.'
        : 'Объяснение предложения основано на данных каталога, без вызова AI-модели.'}</p>
      {alternative.warnings.length > 0 && <ul>{alternative.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>}
    </section>}
    {(result.cards.length > 0 || alternative) && <p className="hint">Указана стартовая цена. Итоговую стоимость и детали заказа уточняйте у подрядчика.</p>}
    {comparison && <section className="date-comparison" aria-label="Сравнение дат"><h3>Что изменилось при смене даты</h3>
      <p>{dateLabel(previous!.normalized_request.date)} → {dateLabel(input.date)}. Остальные условия и версия каталога совпадают.</p>
      <ul>{comparison.map(message => <li key={message}>{message}</li>)}</ul></section>}
    <section className="diagnostics" aria-label="Причины исключения"><h3>Как применялись условия на {dateLabel(input.date)}</h3>
      <p className="hint">Каждый профиль учитывается только на первом этапе, который он не прошёл.</p>
      <ol className="filter-steps">{result.diagnostics.filters.map(step => <li key={step.reason}>
        <span>{reasonLabels[step.reason]}</span><span>Исключено: <strong>{step.excluded_count}</strong> · осталось: {step.remaining_count}</span>
      </li>)}</ol>
      {result.diagnostics.busy_profiles.length > 0 && <details><summary>Проверить календарные доказательства</summary>
        {result.diagnostics.busy_profiles.map(item => <div className="busy-proof" key={item.id}>
          <strong>{item.name} · {dateLabel(item.date)}</strong><EvidenceList items={[item.evidence]} />
        </div>)}
      </details>}
    </section>
    <footer className="result-meta"><p>{result.explanation_mode === 'prepared'
      ? 'В объяснениях использованы заранее подготовленные AI-признаки с доказательствами. Модель не вызывается для этого запроса.'
      : 'Основной результат основан на данных каталога. Без вызова AI-модели.'}</p>
      {result.diagnostics.warnings.length > 0 && <div className="notice"><strong>Примечания к данным</strong><ul>{result.diagnostics.warnings.map((message, i) => <li key={i}>{message}</li>)}</ul></div>}
      <details><summary>Версия данных</summary><code>{result.data_version}</code></details>
    </footer>
  </div>;
}
