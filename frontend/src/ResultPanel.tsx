import type { Evidence, RecommendResponse } from './contracts';
import { compareDates, dateLabel, evidenceValue, fieldLabels, money, originLabels, reasonLabels } from './presentation';

function EvidenceList({ items }: { items: Evidence[] }) {
  return <ul className="evidence-list">{items.map((item, index) => <li key={`${item.field}-${index}`}>
    <strong>{fieldLabels[item.field] ?? item.field}</strong>
    <span className="source-label">{item.source === 'profile' ? 'Поле каталога' : item.source === 'prepared' ? 'Подготовленный признак с цитатой' : 'Описание профиля'}</span>
    {item.quote && <blockquote>{item.quote}</blockquote>}
    <p className="source-value">{evidenceValue(item)}</p>
  </li>)}</ul>;
}

export function ResultPanel({ result, previous = null }: { result: RecommendResponse; previous?: RecommendResponse | null }) {
  const comparison = compareDates(previous, result);
  const input = result.normalized_request;
  const headings = { matched: 'Подрядчики под ваши условия', category_absent: 'В этом городе нет такой категории', no_match: 'Никто не прошёл все условия' };
  return <div className={`result-panel ${result.status}`}>
    <div className="result-heading"><div><p className="eyebrow">Результат подбора</p><h2>{headings[result.status]}</h2></div>
      <span className="count-badge">Подходящих: {result.eligible_count}</span></div>
    <p className="request-summary">{input.city} · {input.category} · {dateLabel(input.date)} · {input.event_format} · бюджет {money(input.budget_kzt)}
      {input.language && ` · ${input.language}`}{input.duration_hours != null && ` · ${input.duration_hours} ч`}</p>
    <p className="server-message">{result.message}</p>
    {result.preference_interpretation && <section className="preference-summary" aria-label="Как поняты пожелания">
      <h3>Как поняты пожелания</h3>
      {result.preference_interpretation.clarification_needed.map(message => <p className="notice" role="alert" key={message}>{message}</p>)}
      {Object.keys(result.preference_interpretation.labels).length
        ? <ul>{Object.values(result.preference_interpretation.labels).map(label => <li key={label}>{label}</li>)}</ul>
        : <p className="hint">Пожелания не заданы или не распознаны. Дополнительные предпочтения не предполагаются.</p>}
      {result.preference_interpretation.notes.map(note => <p className="hint" key={note}>{note}</p>)}
    </section>}
    <p className="hint">Кандидатов в категории и городе: {result.total_candidates}. Показано: {Math.min(result.cards.length, 3)} из {result.eligible_count} подходящих.</p>
    <div className="cards">{result.cards.slice(0, 3).map((card, index) => <article className="contractor-card" key={card.id} aria-label={card.name}>
      <div className="card-top"><span className="rank">{String(index + 1).padStart(2, '0')}</span><span className="hint">{card.category} · {card.city}</span></div>
      <h3>{card.name}</h3><p className="price">от {money(card.price_from_kzt)}</p>
      <div className="tags"><span>{originLabels[card.origin]}</span>
        {card.synthetic && <span>Синтетический профиль</span>}
        {card.city_imputed && <span>Город указан при подготовке данных</span>}
        {card.price_imputed && <span>Цена указана при подготовке данных</span>}
      </div>
      <div className="explanation"><h4>Почему подходит</h4><p>{card.explanation}</p></div>
      {!!card.score_breakdown?.criteria.length && <div className="preference-assessments">
        {[
          ['Совпадает', card.matched_preferences ?? []],
          ['Расходится с пожеланием', card.conflicting_preferences ?? []],
          ['Недостаточно данных', card.unknown_preferences ?? []],
        ].map(([title, rows]) => Array.isArray(rows) && rows.length > 0 && <div key={String(title)}><h4>{String(title)}</h4>
          <ul>{rows.map(item => <li key={item.criterion}>{item.label}: {item.requested_label}
            {item.status === 'conflicting' && `; в описании — ${item.observed_label}`}</li>)}</ul></div>)}
      </div>}
      <details><summary>На чём основано объяснение</summary><EvidenceList items={card.evidence} /></details>
      {card.score_breakdown && <details><summary>Как определён порядок</summary>
        <p className="hint">Эвристика соответствия пожеланиям, не оценка качества человека и не вероятность успеха.</p>
        <p>Соответствие пожеланиям: {card.score_breakdown.preference_score}; специализация: {card.score_breakdown.specialization}.</p>
        <ul>{card.score_breakdown.criteria.map(item => <li key={item.criterion}>{item.label}: {item.points > 0 ? '+' : ''}{item.points}
          <EvidenceList items={item.evidence} /></li>)}</ul>
        <p className="hint">Затем — стартовая цена и ID: {card.score_breakdown.tie_break_id}.</p>
      </details>}
    </article>)}</div>
    {result.cards.length > 0 && <p className="hint">Указана стартовая цена. Итоговую стоимость и детали заказа уточняйте у подрядчика.</p>}
    {comparison && <section className="date-comparison" aria-label="Сравнение дат"><h3>Что изменилось при смене даты</h3>
      <p>{dateLabel(previous!.normalized_request.date)} → {dateLabel(input.date)}. Остальные условия и версия каталога совпадают.</p>
      <ul>{comparison.map(message => <li key={message}>{message}</li>)}</ul></section>}
    <section className="diagnostics" aria-label="Причины исключения"><h3>Как применялись условия</h3>
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
      : 'Базовые объяснения по данным каталога. Без вызова AI-модели.'}</p>
      {result.preference_mode && <p>{result.preference_mode === 'rules' ? 'Пожелания сопоставлены по точным цитатам и фиксированным правилам, без AI.'
        : result.preference_mode === 'prepared' ? 'Для пожеланий использованы заранее проверенные AI-признаки.'
        : 'Для пожеланий использованы проверенные AI-признаки и локальные правила.'} Неизвестные сведения не считаются недостатком.</p>}
      {result.diagnostics.warnings.length > 0 && <div className="notice"><strong>Примечания к данным</strong><ul>{result.diagnostics.warnings.map((message, i) => <li key={i}>{message}</li>)}</ul></div>}
      <details><summary>Версии данных и правил</summary><code>{result.data_version}</code><code>{result.feature_version}</code><code>{result.ranking_version}</code></details>
    </footer>
  </div>;
}
