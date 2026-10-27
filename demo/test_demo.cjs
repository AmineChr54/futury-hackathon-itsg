// Regression checks for the single-file app in both modes. Run: node demo/test_demo.cjs
// The page script runs in a vm without its last two lines (APP.init / TOUR.init), on stubbed browser globals.
const { readFileSync } = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const { test } = require('node:test');

const html = readFileSync(__dirname + '/index.html', 'utf8');
const script = html.slice(html.lastIndexOf('<script>') + 8, html.lastIndexOf('APP.init();'));

function load(mode, hash = '') {
  const el = () => new Proxy({ style: {}, classList: { add() {}, remove() {}, toggle() {}, contains: () => false }, dataset: {} },
    { get: (t, k) => (k in t ? t[k] : typeof k === 'string' && /^(query|add|remove|append|set|focus|click|scroll|insert|get)/.test(k) ? () => el() : '') });
  const mem = () => { const m = new Map(); return { getItem: k => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: k => m.delete(k) }; };
  const window = { SPECS_MODE: mode, addEventListener() {}, matchMedia: () => ({ matches: false }) };
  const ctx = vm.createContext({ window, location: { hash, protocol: 'http:', href: '' }, document: { addEventListener() {}, querySelector: el, querySelectorAll: () => [], getElementById: el, createElement: el, body: el(), documentElement: el() },
    localStorage: mem(), sessionStorage: mem(), navigator: {}, matchMedia: () => ({ matches: false }), setTimeout, clearTimeout, setInterval, clearInterval,
    innerWidth: 1400, innerHeight: 900, performance, requestAnimationFrame: f => setTimeout(f, 0), addEventListener() {}, MutationObserver: class { observe() {} }, BroadcastChannel: class { postMessage() {} }, TextDecoder, TextEncoder, URL, Blob, fetch: async () => ({ ok: false, json: async () => ({}) }), console });
  ctx.self = ctx.top = ctx;
  vm.runInContext(script + '\nthis.APP = APP; this.TOUR = TOUR;', ctx);
  return ctx;
}

test('without the server flag the page is recorded: GitHub Pages, a file, /demo', () => {
  for (const mode of [undefined, 'demo']) assert.equal(load(mode).APP.LIVE, false);
  assert.equal(load('live', '#demo=3').APP.LIVE, false); // the guided demo always runs recorded
  assert.equal(load('live').APP.LIVE, true);
});

test('the recorded story the guided demo drives is intact', () => {
  const { APP, TOUR } = load(undefined);
  for (const k of ['reset', 'simDrop', 'chatAsk', 'generateCases', 'sendPackage', 'uploadResult', 'itsgAnswer', 'issueCert', 'toVendor', 'autoDecide', 'tickAll',
    'ensureDrop', 'ensureEdited', 'ensureSent', 'ensureUpload', 'ensureAsked', 'ensureFixed', 'certIssued', 'caseEdited']) assert.equal(typeof APP.story[k], 'function', k);
  assert.equal(TOUR.SEQ.length, 23);
  APP.story.ensureSent();
  assert.equal(APP.S.story.sent, true);
  assert.ok(APP.story.caseIds().length >= 5);
});

test('live mode projects the server data onto the screens', () => {
  const { APP } = load('live');
  const { LV, hydrate, liveChanges } = APP.live;
  LV.session = { user: 'istg', role: 'itsg', token: 't' };
  LV.run = { id: 'r1', seq: 5, status: 'done', live: {}, plan: { mode: 'single', new: { name: 'v13.4.pdf', version: '13.4' }, old: null }, items: [
    { sec: '3.12', title: 'DBVO', page: 135, status: 'done', source: 'change log v13.4', log: ['redaktionelle Anpassung'], decision: 'approved', change_edited: true, phase: 'cases', cases: ['TC-1'],
      spec_change: { change_type: 'condition', summary: 's', quotes_new: ['nicht mehr als 6 Monate'], parameters: [], quote_checks: [] } },
    { sec: '3.7', title: 'DBEE', page: 91, status: 'candidate', source: 'log+diff', log: [] }] };
  LV.cases = [{ id: 'TC-1', section: '3.12', section_title: 'DBVO', title: 'Boundary', status: 'sent', formula: { expression: 'a', variables: [] }, expected_value: '4' }];
  LV.exchange = { threads: [{ id: 'T-cert-sap', vendor: 'sap', kind: 'cert', subject: 'x', msgs: [], read: { itsg: 0, vendor: 0 } }], files: {}, certs: {}, publishedTo: ['sap'] };
  hydrate();
  const ST = APP.S.story;
  assert.equal(ST.decided['3.12'], 'approved');
  assert.ok(ST.edits['3.12']);
  assert.equal(ST.sent, true);
  assert.deepEqual(APP.S.publishedTo, ['sap']);
  assert.equal(APP.S.mail.threads[0].id, 'T-cert-sap');
  assert.deepEqual(liveChanges().map(c => [c.sec, c.source, !!c.entry]), [['3.12', 'log', true], ['3.7', 'confirmed', false]]);
});

test('a vendor sees its package rounds from the verdicts in its thread', () => {
  const { APP } = load('live');
  const { LV, hydrate } = APP.live;
  LV.session = { user: 'sap', role: 'vendor', vendor: 'sap', token: 't' };
  APP.S.vendorUser = 'sap';
  LV.checklists = [{ id: 'PKG-1', note: 'n', covered: { 'TC-1': '2026-10-27T10:00:00' }, rows: [{ id: 'TC-1', section: '3.12', title: 'Boundary', result_name: 'n_au' }], recap: { status: 'pending' } }];
  const verdict = { package: 'PKG-1', round: 1, ok: false, passed: 0, total: 1, file: 'checklist', rows: [{ id: 'TC-1', ok: false, words: [{ en: 'x', de: 'x' }] }] };
  LV.exchange = { threads: [{ id: 'T', vendor: 'sap', kind: 'cert', subject: 'x', read: { itsg: 0, vendor: 0 }, msgs: [{ from: 'system', at: 1, body: '', attach: [{ type: 'pkgverdict', ref: verdict }] }] }], files: {}, certs: {} };
  hydrate();
  const ST = APP.S.story;
  assert.equal(ST.sent, true);
  assert.equal(ST.covered['TC-1'], '2026-10-27 10:00');
  assert.equal(ST.uploads.length, 1);
  assert.equal(ST.uploads[0].round, 1);
  assert.equal(ST.notify, true); // a new package: the notification shows once
});
