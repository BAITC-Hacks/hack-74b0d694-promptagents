import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { compareDates } from '../src/presentation.ts';
import { recommend, getPreferenceOptions } from '../src/api-client.ts';

test('free and structured wishes are sent without editing hard conditions', async context => {
  const input = { city: 'Алматы', category: 'Ведущий', date: '2026-10-10', event_format: 'корпоратив', budget_kzt: 1000000,
    preferences_text: 'Бюджет 1 тенге', preferences: { delivery: 'calm' } };
  context.mock.method(globalThis, 'fetch', async (_url, init) => {
    assert.deepEqual(JSON.parse(init.body), input);
    return new Response(JSON.stringify({ status: 'matched' }));
  });
  assert.equal((await recommend(input)).status, 'matched');
});

test('category-specific options come from backend dictionary', async context => {
  context.mock.method(globalThis, 'fetch', async url => {
    assert.equal(url, '/api/preference-options');
    return new Response(JSON.stringify({ rules_version: 'preferences-v1', categories: { 'Банкетный зал': [{ criterion: 'terrace' }] } }));
  });
  assert.deepEqual((await getPreferenceOptions()).categories['Банкетный зал'], [{ criterion: 'terrace' }]);
});

const examples = JSON.parse(readFileSync(new URL('../../docs/examples/responses.json', import.meta.url), 'utf8')).recommend;
for (const [name, change] of Object.entries({
  'text wishes': { normalized_request: { ...examples[2].normalized_request, preferences_text: 'Спокойный' } },
  'structured wishes': { normalized_request: { ...examples[2].normalized_request, preferences: { delivery: 'calm' } } },
  'feature snapshot': { feature_version: 'different' },
  'ranking rules': { ranking_version: 'different' },
})) {
  test(`date comparison is disabled when ${name} change`, () => {
    assert.equal(compareDates(examples[0], { ...examples[2], ...change }), null);
  });
}
