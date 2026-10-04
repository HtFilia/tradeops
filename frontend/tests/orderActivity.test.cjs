const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');

// Compile the pure TypeScript helper without a DOM or external services.
const source = fs.readFileSync('src/lib/orderActivity.ts', 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 }
}).outputText;
const exportsObject = {};
new Function('exports', compiled)(exportsObject);
const { appendReceipt } = exportsObject;

test('receipts preserve actual partial fills and keep newest responses first', () => {
  const previous = [{ order_id: 'first', filled_quantity: 1, status: 'FILLED' }];
  const response = { order_id: 'second', filled_quantity: 2, quantity: 5, status: 'PARTIALLY_FILLED', average_price: 99.25 };
  const receipts = appendReceipt(previous, response);
  assert.deepEqual(receipts, [response, previous[0]]);
  assert.equal(receipts[0].filled_quantity, 2);
  assert.equal(previous.length, 1);
});

test('receipts retain at most ten responses and replace duplicate IDs', () => {
  const previous = Array.from({length: 10}, (_, i) => ({order_id: String(i)}));
  assert.deepEqual(appendReceipt(previous, {order_id: 'new'}).map(r => r.order_id),
    ['new', '0', '1', '2', '3', '4', '5', '6', '7', '8']);
  assert.equal(appendReceipt(previous, {order_id: '2'}).length, 10);
  assert.equal(appendReceipt(previous, {order_id: '2'}).filter(r => r.order_id === '2').length, 1);
});
