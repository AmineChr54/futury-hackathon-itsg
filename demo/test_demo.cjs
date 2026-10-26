// Regression checks for the single-file app. Run: node demo/test_demo.cjs
const { readFileSync } = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const { test } = require('node:test');
const html = readFileSync(__dirname + '/index.html', 'utf8');

function pipeline() {
  const nodes = new Map();
  const node = id => {
    if (!nodes.has(id)) nodes.set(id, { innerHTML: '', textContent: '', scrollTop: 0 });
    return nodes.get(id);
  };
  const APP = {
    S: { screen: 'pipeline', role: 'itsg', lang: 'en' }, ACT: {}, RENDER: {}, GROUPS: {},
    SCREENS: ['ingest', 'extract', 'rules', 'tests', 'publish'].map(id => ({ id })),
    store: { get: (_, fallback) => fallback, set() {} },
    L: en => en, esc: s => String(s ?? ''), pill: s => s, ic: () => '', head: () => '',
    render() {}, renderShell() {}, log() {}, toast() {}
  };
  const context = vm.createContext({ APP, location: { protocol: 'http:' }, window: {},
    document: { addEventListener() {}, getElementById: node, body: { scrollHeight: 0 } },
    ArrayBuffer, Blob, Set, URLSearchParams, setTimeout, clearTimeout,
    fetch: async path => {
      if (path.startsWith('/api/upload')) throw new Error('network unavailable');
      return { ok: true, json: async () => ({ uploads: [], law_files: [], law_dir: 'law' }) };
    } });
  vm.runInContext(html.slice(html.indexOf('const PIPE ='), html.indexOf('window.PIPE =')) + '\nthis.PIPE = PIPE;', context);
  const P = context.PIPE.P;
  P.online = true;
  P.docs = { uploads: [{ name: 'spec.pdf', kind: 'upload' }], law_files: [], law_dir: 'law' };
  return { ...context, P, node };
}

test('completed sections can be generated again from the section header', () => {
  const { PIPE, P, node } = pipeline();
  P.selItem = '3.12';
  P.run = { status: 'done', plan: { mode: 'single', new: { name: 'spec.pdf' } }, items: [
    { sec: '3.12', title: 'DBVO', page: 1, status: 'done', cases: ['TC-1'] }
  ] };
  PIPE.afterRender();
  assert.match(node('pipeItemHead').innerHTML, /data-act="pipeGen"/);
});

test('a failed document plan cannot enable generation', () => {
  const { PIPE, P } = pipeline();
  P.planErr = 'unreadable PDF';
  assert.match(PIPE.testButton(), /disabled/);
});

test('the Stop action appears when the first poll discovers a running run', () => {
  const { PIPE, P, node } = pipeline();
  P.run = { status: 'running', plan: { mode: 'single', new: { name: 'spec.pdf' } }, items: [] };
  PIPE.afterRender();
  assert.match(node('pipeStopAction').innerHTML, /data-act="pipeStop"/);
});

test('upload failure is reported to the caller and clears the busy state', async () => {
  const { PIPE, P } = pipeline();
  await assert.rejects(PIPE.upload({ name: 'spec.pdf', arrayBuffer: async () => new ArrayBuffer(1) }), /network unavailable/);
  assert.equal(P.uploading, null);
});

test('server PDF ingestion works without loading the browser PDF reader', async () => {
  const S = { ingested: [] };
  const status = { innerHTML: '' };
  const ingestSource = html.slice(html.indexOf('  async function ingestPdf('), html.indexOf('\n  function readDta('));
  let browserReads = 0;
  const result = { name: 'spec.pdf', pages: 2, sections: 3, version: '1.0', changelog_rows: 0 };
  const PIPE = { P: { online: true }, upload: async () => result };
  const context = vm.createContext({ window: { PIPE }, PIPE, S, $: () => status,
    L: en => en, esc: s => String(s), fmtN: String, log() {}, render() {},
    loadPdfJs: async () => { browserReads++; throw new Error('CDN blocked'); } });
  vm.runInContext(ingestSource + '\nthis.ingestPdf = ingestPdf;', context);
  await context.ingestPdf({ name: 'spec.pdf' });
  assert.equal(browserReads, 0);
  assert.equal(S.ingested.length, 1);
  assert.match(status.innerHTML, /spec.pdf/);
  assert.doesNotMatch(status.innerHTML, /Could not read/);
});

test('finishing a run refreshes the Generate button on the upload screen', async () => {
  const P = { online: true, runId: 'r1', after: 0, events: [], run: { status: 'running' } };
  let refreshes = 0;
  const source = html.slice(html.indexOf('  let polling = false;'), html.indexOf('\n  const KIND ='));
  const context = vm.createContext({ P, api: async () => ({ id: 'r1', status: 'done', items: [], events: [] }),
    loadCases() {}, onScreen: () => false, paintDocs: () => { refreshes++; },
    A: { renderShell() {} }, store: { set() {} } });
  vm.runInContext(source + '\nthis.pollRun = pollRun;', context);
  await context.pollRun(true);
  assert.equal(P.run.status, 'done');
  assert.equal(refreshes, 1);
});
