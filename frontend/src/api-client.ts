import type { DataIssue, ErrorResponse, HealthResponse, OptionsResponse, RecommendRequest, RecommendResponse } from './contracts';

export class ApiError extends Error {
  status: number | null;
  code: string;
  issues: DataIssue[];
  constructor(
    message: string,
    status: number | null = null,
    code: string = 'network_error',
    issues: DataIssue[] = [],
  ) { super(message); this.name = 'ApiError'; this.status = status; this.code = code; this.issues = issues; }
}

export function asApiError(error: unknown): ApiError {
  return error instanceof ApiError ? error : new ApiError('Не удалось получить ответ сервера. Попробуйте ещё раз.');
}

async function request<T>(path: string, init: RequestInit = {}, timeoutMs = 15000): Promise<T> {
  const timeout = new AbortController();
  const timer = setTimeout(() => timeout.abort(), timeoutMs);
  const signal = init.signal ? AbortSignal.any([init.signal, timeout.signal]) : timeout.signal;
  try {
    const response = await fetch(path, { ...init, signal });
    const body: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      const error = body && typeof body === 'object' && 'error' in body
        ? (body as ErrorResponse).error : null;
      throw new ApiError(
        typeof error?.message === 'string' ? error.message : `Сервер вернул ошибку HTTP ${response.status}.`,
        response.status,
        error?.code ?? 'http_error',
        Array.isArray(error?.issues) ? error.issues : [],
      );
    }
    if (body === null || typeof body !== 'object') {
      throw new ApiError('Сервер вернул ответ в неподдерживаемом формате.', response.status, 'invalid_response');
    }
    return body as T;
  } catch (error) {
    if (init.signal?.aborted) throw new DOMException('Запрос отменён', 'AbortError');
    if (timeout.signal.aborted) throw new ApiError('Сервер не ответил за 15 секунд. Повторите запрос.', null, 'timeout');
    throw asApiError(error);
  } finally { clearTimeout(timer); }
}

export const getHealth = (signal?: AbortSignal) => request<HealthResponse>('/api/health', { signal });
export const getOptions = (signal?: AbortSignal) => request<OptionsResponse>('/api/options', { signal });
export const recommend = (input: RecommendRequest, signal?: AbortSignal) => request<RecommendResponse>('/api/recommend', {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input), signal,
});
