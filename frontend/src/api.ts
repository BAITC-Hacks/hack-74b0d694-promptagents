import type { ErrorResponse, OptionsResponse, RecommendRequest, RecommendResponse } from './contracts';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { ...init, signal: AbortSignal.timeout(15000) });
  } catch {
    throw new Error('Сервер недоступен или не ответил за 15 секунд. Проверьте запуск backend.');
  }
  if (!response.ok) {
    const body: ErrorResponse | null = await response.json().catch(() => null);
    const details = body?.error?.issues?.map(issue =>
      [issue.line ? `Строка ${issue.line}` : '', issue.field, issue.message].filter(Boolean).join(': '),
    ).join('; ');
    throw new Error([body?.error?.message ?? `Ошибка HTTP ${response.status}`, details].filter(Boolean).join(' '));
  }
  return response.json() as Promise<T>;
}

export const getOptions = () => request<OptionsResponse>('/api/options');
export const recommend = (input: RecommendRequest) => request<RecommendResponse>('/api/recommend', {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input),
});
