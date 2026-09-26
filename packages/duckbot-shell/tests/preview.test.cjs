const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// Exercise the shipped event handlers, including async cancellation. Native startup
// and the installed resource path are checked separately by the Windows smoke job.
async function windowHarness() {
  const calls = [];
  const elements = new Map();
  class Element {
    constructor() {
      this.value = ''; this.dataset = {}; this.disabled = false; this.hidden = false;
      this.listeners = {}; this.classList = { add() {}, remove() {} };
    }
    addEventListener(event, fn) { this.listeners[event] = fn; }
    async fire(event) { await this.listeners[event]?.({ preventDefault() {} }); }
    replaceChildren() {} appendChild() {} append() {} add() {} scrollIntoView() {}
  }
  const html = fs.readFileSync(path.join(__dirname, '../ui/index.html'), 'utf8');
  for (const match of html.matchAll(/id="([^"]+)"/g)) elements.set(match[1], new Element());
  const preview = { task_id: 'task-1', state: 'ready', destination: 'offline/demo',
    destination_is_local: true, sensitivity: 'PUBLIC', policy_action: 'allow',
    policy_justification: 'local', redactions: [], estimated_cost: { currency: 'USD', amount: '0' } };
  const invoke = async (command, payload) => {
    if (command === 'health') return { protocol_version: 2 };
    calls.push(payload);
    if (payload.method === 'task_prepare') return preview;
    if (payload.method === 'connector_list') return { files: [] };
    if (payload.method === 'task_execute') return { kind: 'approval_required', preview,
      approval: { id: 'approval-1', risk_class: 'financial', action_description: 'Draft' } };
    return {};
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../ui/main.js'), 'utf8'), {
    window: { __TAURI__: { core: { invoke } } },
    document: { getElementById: id => elements.get(id),
      querySelectorAll: selector => selector === 'button, input, textarea, select' ? [...elements.values()] : [],
      createElement: () => new Element() },
    Option: Element,
  });
  await new Promise(setImmediate);
  elements.get('instruction').value = 'Draft a reply';
  await elements.get('prepare').fire('click');
  return { elements, calls };
}

for (const field of ['instruction', 'risk-class', 'action-description', 'context-file']) {
  test(`editing ${field} discards a preview and disables sending`, async () => {
    const { elements, calls } = await windowHarness();
    assert.equal(elements.get('execute').disabled, false);
    await elements.get(field).fire('input');
    await new Promise(setImmediate);
    assert.equal(elements.get('execute').disabled, true);
    assert.equal(elements.get('preview').hidden, true);
    assert.equal(calls.filter(call => call.method === 'task_cancel').length, 1);
  });
}

test('editing after an approval pause disables its old approval', async () => {
  const { elements } = await windowHarness();
  await elements.get('execute').fire('click');
  assert.equal(elements.get('approve').disabled, false);
  await elements.get('instruction').fire('input');
  assert.equal(elements.get('approve').disabled, true);
  assert.equal(elements.get('approval').hidden, true);
});

for (const [control, event] of [['settings-form', 'submit'], ['delete-key', 'click']]) {
  test(`${control} clears a preview invalidated by the host`, async () => {
    const { elements } = await windowHarness();
    await elements.get(control).fire(event);
    assert.equal(elements.get('execute').disabled, true);
    assert.equal(elements.get('preview').hidden, true);
  });
}

test('preparing again discards the old task before asking for another preview', async () => {
  const { elements, calls } = await windowHarness();
  calls.length = 0;
  await elements.get('prepare').fire('click');
  assert.deepEqual(calls.map(call => call.method), ['task_cancel', 'task_prepare']);
});
