import assert from 'node:assert/strict';
import test from 'node:test';
import { getOptions, recommend, ApiError } from '../src/api-client.ts';

const input = { city: 'Алматы', date: '2026-10-10', category: 'Ведущий', event_format: 'корпоратив', budget_kzt: 1000000, duration_hours: null, language: null };

test('POST sends parameters and optional null values to the real API path', async context => {
  context.mock.method(globalThis, 'fetch', async (url, init) => {
    assert.equal(url, '/api/recommend');
    assert.equal(init.method, 'POST');
    assert.deepEqual(JSON.parse(init.body), input);
    assert.equal(init.headers['Content-Type'], 'application/json');
    return new Response(JSON.stringify({ status: 'no_match' }));
  });
  assert.equal((await recommend(input)).status, 'no_match');
});

for (const status of [422, 503, 501]) {
  test(`HTTP ${status} preserves error details instead of returning an empty result`, async context => {
    const issues = [{ field: 'body.date', message: 'Проверьте дату' }];
    context.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({ error: { message: 'Ошибка', code: 'test', issues } }), { status }));
    await assert.rejects(getOptions(), error => error instanceof ApiError && error.status === status && error.issues[0].field === 'body.date');
  });
}

test('network failure is explicit and never switches to examples', async context => {
  let calls = 0;
  context.mock.method(globalThis, 'fetch', async () => { calls++; throw new TypeError('Failed to fetch'); });
  await assert.rejects(getOptions(), error => error instanceof ApiError && error.code === 'network_error');
  assert.equal(calls, 1);
});

test('non-JSON success is reported as invalid_response', async context => {
  context.mock.method(globalThis, 'fetch', async () => new Response('<html>Proxy error</html>'));
  await assert.rejects(getOptions(), error => error.code === 'invalid_response');
});

test('superseded request is cancelled without becoming a network error', async context => {
  context.mock.method(globalThis, 'fetch', async (_url, { signal }) => new Promise((_resolve, reject) => {
    signal.addEventListener('abort', () => reject(signal.reason), { once: true });
  }));
  const controller = new AbortController();
  const pending = recommend(input, controller.signal);
  controller.abort();
  await assert.rejects(pending, error => error.name === 'AbortError');
});

test('15 second timeout has its own diagnostic', async context => {
  context.mock.timers.enable({ apis: ['setTimeout'] });
  context.mock.method(globalThis, 'fetch', async (_url, { signal }) => new Promise((_resolve, reject) => {
    signal.addEventListener('abort', () => reject(signal.reason), { once: true });
  }));
  const pending = getOptions();
  context.mock.timers.tick(15000);
  await assert.rejects(pending, error => error.code === 'timeout');
});
