import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import test from 'node:test';
import { compareDates, evidenceValue } from '../src/presentation.ts';

const examples = JSON.parse(readFileSync(new URL('../../docs/examples/responses.json', import.meta.url), 'utf8'));
const previous = examples.recommend[0];
const current = examples.recommend[2];

test('date change is explained only with matching calendar evidence', () => {
  const messages = compareDates(previous, current);
  assert.match(messages[0], /занят 11.10.2026 — дата подтверждена календарём/);
});

for (const [name, change] of Object.entries({
  'different data': { data_version: 'new-version' },
  'different budget': { normalized_request: { ...current.normalized_request, budget_kzt: 1 } },
  'same date': { normalized_request: { ...current.normalized_request, date: previous.normalized_request.date } },
  'different optional language': { normalized_request: { ...current.normalized_request, language: null } },
})) {
  test(`do not compare: ${name}`, () => assert.equal(compareDates(previous, { ...current, ...change }), null));
}

test('disappearance from top-3 is not proof of unavailability', () => {
  for (const evidence of [
    { source: 'profile', field: 'busy_dates', value: ['2026-10-12'] },
    { source: 'prepared', field: 'busy_dates', value: ['2026-10-11'] },
    { source: 'profile', field: 'description', value: ['2026-10-11'] },
  ]) {
    const unconfirmed = structuredClone(current);
    unconfirmed.diagnostics.busy_profiles[0].evidence = evidence;
    assert.match(compareDates(previous, unconfirmed)[0], /Подтверждения занятости.*нет/);
  }
});

test('newly appearing card is linked to the previous busy calendar', () => {
  const messages = compareDates(current, previous);
  assert.match(messages[0], /был занят 11.10.2026 по календарю/);
});

test('missing and null optional values represent the same constraints', () => {
  const a = structuredClone(previous);
  const b = structuredClone(current);
  delete a.normalized_request.duration_hours;
  b.normalized_request.duration_hours = null;
  assert.notEqual(compareDates(a, b), null);
});

test('null max_hours does not become unlimited hours', () => {
  assert.equal(evidenceValue({ field: 'max_hours', source: 'profile', value: null }), 'Не привязано к присутствию на площадке');
});
