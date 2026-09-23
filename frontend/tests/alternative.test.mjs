import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

const examples = JSON.parse(readFileSync(new URL('../../docs/examples/responses.json', import.meta.url), 'utf8'));

test('alternative date renders as a separate marked card with evidence and preference score', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' });
  try {
    const { ResultPanel } = await server.ssrLoadModule('/src/ResultPanel.tsx');
    const original = structuredClone(examples.recommend[2]);
    const card = structuredClone(examples.recommend[0].cards[0]);
    card.matched_preferences = [{ criterion: 'delivery', label: 'Подача', requested_label: 'Спокойная', status: 'matched' }];
    card.score_breakdown = { preference_score: 1, specialization: 0, tie_break_id: card.id,
      criteria: [{ criterion: 'delivery', label: 'Подача', points: 1, evidence: [] }] };
    original.alternative = { date: '2026-10-12', card, explanation_mode: 'baseline', warnings: [] };
    const html = renderToStaticMarkup(React.createElement(ResultPanel, { result: original }));
    assert.match(html, /Подходящих: 0/);
    assert.match(html, /class="alternative-date"/);
    assert.match(html, /alternative-card/);
    assert.match(html, /11\.10\.2026/);
    assert.match(html, /12\.10\.2026/);
    assert.match(html, /На чём основано объяснение/);
    assert.match(html, /Как определён порядок/);
    assert.match(html, /Соответствие пожеланиям: 1/);
    assert.doesNotMatch(renderToStaticMarkup(React.createElement(ResultPanel, { result: examples.recommend[1] })), /alternative-date/);
  } finally {
    await server.close();
  }
});
