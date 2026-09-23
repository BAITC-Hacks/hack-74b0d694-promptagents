import type { ApiError } from './api-client';
import { fieldLabels } from './presentation';

export function ErrorPanel({ error, retry }: { error: ApiError; retry?: () => void }) {
  const title = error.code === 'invalid_response' ? 'Не удалось прочитать ответ'
    : error.status === 422 ? 'Проверьте параметры запроса'
    : error.status === 503 ? 'Каталог временно недоступен'
    : error.status === 501 ? 'Подбор ещё не подключён'
    : error.status ? 'Ошибка сервиса'
    : error.code === 'timeout' ? 'Время ожидания истекло' : 'Нет соединения с сервером';
  return <div className="error" role="alert"><h3>{title}</h3><p>{error.message}</p>
    {error.issues.length > 0 && <ul>{error.issues.map((item, index) => <li key={index}>
      {item.field && `${fieldLabels[item.field.replace(/^body\./, '')] ?? item.field}: `}
      {item.line != null && `Строка ${item.line}. `}{item.id && `${item.id}. `}{item.message}
    </li>)}</ul>}
    {error.status && <p className="hint">HTTP {error.status}</p>}
    {retry && <button type="button" className="secondary" onClick={retry}>Повторить запрос</button>}
  </div>;
}
