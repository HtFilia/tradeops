// Opt-in UI integration check: install Playwright or provide NODE_PATH.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');

(async () => {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    let authenticated = false;
    const payloads = [];
    await page.route('**/auth/**', route => {
      const operation = new URL(route.request().url()).pathname.split('/').pop();
      if (operation === 'logout') authenticated = false;
      if (operation === 'login') authenticated = true;
      return route.fulfill({status: authenticated ? 200 : operation === 'logout' ? 204 : 401,
        contentType: 'application/json', body: authenticated ? JSON.stringify({user_id: 'test-user', expires_at: '2099-01-01T00:00:00Z'}) : ''});
    });
    await page.route('**/api/market/health', route => route.fulfill({json: {status: 'ok', instruments: {
      'EQ-ACME': {last_tick: {timestamp: '2024-01-02T14:30:00Z', bid: 99, ask: 101, mid: 100}},
      'FUT-ES': {last_tick: {timestamp: '2024-01-02T14:30:00Z', bid: 4999, ask: 5001, mid: 5000}}
    }}}));
    await page.route('**/api/trading/health', route => route.fulfill({json: {status: 'ok'}}));
    await page.route('**/api/trading/orders', route => {
      const payload = route.request().postDataJSON();
      payloads.push(payload);
      if (payload.quantity === 13) return route.fulfill({status: 400, json: {detail: 'Synthetic order rejected'}});
      return route.fulfill({status: 201, json: {...payload, order_id: 'test-order', filled_quantity: 2,
        status: 'PARTIALLY_FILLED', average_price: 5001}});
    });
    await page.goto(process.env.TRADEOPS_UI_URL ?? 'http://127.0.0.1:5173');
    const login = async () => {
      await page.getByLabel('Email', {exact:true}).fill('demo@example.com');
      await page.getByLabel('Password', {exact:true}).fill('demo');
      await page.getByRole('button', {name:'Sign in', exact:true}).click();
      await page.getByLabel('Quantity', {exact:true}).waitFor();
    };
    await login();
    await page.getByRole('button', {name:'Trade FUT-ES', exact:true}).focus({timeout: 3000});
    await page.keyboard.press('Enter');
    assert.equal(await page.getByLabel('Instrument', {exact:true}).inputValue(), 'FUT-ES');
    assert.equal(await page.getByLabel('User ID', {exact:true}).count(), 0);
    await page.getByLabel('Quantity', {exact:true}).fill('5');
    await page.getByRole('button', {name:'Submit order', exact:true}).click();
    const activity = page.getByRole('region', {name:'Order activity'});
    await activity.getByText('PARTIALLY_FILLED', {exact:true}).waitFor();
    assert((await activity.innerText()).includes('2 / 5'));
    assert((await activity.innerText()).includes('5001.0000'));
    assert.equal(payloads[0].instrument_id, 'FUT-ES');
    assert(!('user_id' in payloads[0]));
    await page.getByLabel('Quantity', {exact:true}).fill('13');
    await page.getByRole('button', {name:'Submit order', exact:true}).click();
    await page.getByText('Synthetic order rejected', {exact:true}).waitFor();
    assert.equal(await activity.locator('tbody tr').count(), 1, 'a rejected order must not create a receipt');
    await page.getByRole('button', {name:'Log out', exact:true}).click();
    await login();
    assert.equal(await page.getByText('test-order', {exact:true}).count(), 0);
    await page.getByText('No orders submitted in this browser session.').waitFor();
    console.log('Dashboard integration passed: keyboard selection, actual partial fill, authenticated identity, logout reset.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
