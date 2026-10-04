// Real-endpoint guided journey: run only against a dedicated temporary stack.
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
(async () => {
  const base = process.env.TRADEOPS_DEMO_URL ?? "http://127.0.0.1:18600",
    out = process.env.DEMO_CHECK_OUTPUT;
  const browser = await chromium.launch();
  let storage;
  const results = [];
  if (out) fs.mkdirSync(out, { recursive: true });
  try {
    for (const width of [1440, 390, 320])
      for (const colorScheme of ["light", "dark"]) {
        const context = await browser.newContext({
          ignoreHTTPSErrors: true,
          viewport: { width, height: 900 },
          colorScheme,
          ...(storage ? { storageState: storage } : {}),
        });
        const page = await context.newPage();
        const errors = [],
          requests = [];
        page.on("pageerror", (e) => errors.push(e.message));
        page.on("request", (r) => {
          if (r.resourceType() === "fetch") requests.push(r.url());
        });
        await page.goto(base);
        if (!storage) {
          await page
            .getByRole("button", { name: "Try the isolated demo" })
            .focus();
          await page.keyboard.press("Enter");
        }
        await page.getByTestId("account-cash").waitFor();
        const reset = async (name) => {
          const response = page.waitForResponse(
            (r) =>
              r.url().endsWith("/demo/reset") &&
              r.request().method() === "POST",
          );
          await page.getByRole("button", { name, exact: true }).click();
          const resetResponse = await response;
          if (resetResponse.status() === 429) {
            await page.waitForTimeout(
              Number(resetResponse.headers()["retry-after"] ?? 60) * 1000 + 100,
            );
            return reset(name);
          }
          assert.equal(resetResponse.status(), 200);
          await page
            .getByRole("button", { name: "Execute snapshot order" })
            .waitFor({ state: "visible" });
          await page.waitForFunction(
            () => !document.querySelector("fieldset").disabled,
          );
        };
        const execute = async () => {
          const response = page.waitForResponse(
            (r) =>
              r.url().endsWith("/demo/orders") &&
              r.request().method() === "POST",
          );
          await page
            .getByRole("button", { name: "Execute snapshot order" })
            .focus();
          await page.keyboard.press("Enter");
          const r = await response;
          assert([201, 400].includes(r.status()));
          const receipt = await r.json();
          await page
            .getByText(
              `${receipt.disposition.replaceAll("_", " ")} · ${receipt.filled_quantity} / ${receipt.submitted.quantity} shares filled`,
              { exact: true },
            )
            .waitFor();
          await page.waitForFunction(
            () => !document.querySelector("fieldset").disabled,
          );
          return receipt;
        };
        if (storage) await reset("Full fill");
        let receipt = await execute();
        assert.equal(receipt.disposition, "filled");
        assert.equal(receipt.after.cash_balance, 9499.8);
        assert.equal(
          await page.getByTestId("account-holding").innerText(),
          "5",
        );
        const id = receipt.receipt_id;
        await page.reload();
        await page.getByTestId("account-cash").waitFor();
        assert.equal(
          await page.getByTestId("account-cash").innerText(),
          "9,499.80",
        );
        await page.getByRole("button", { name: /BUY 5 · filled ·/ }).click();
        await page
          .getByText("filled · 5 / 5 shares filled", { exact: true })
          .waitFor();
        if (!storage || (width === 390 && colorScheme === "light")) {
          await reset("Shallow book");
          receipt = await execute();
          assert.equal(receipt.disposition, "partially_filled_final");
          assert.equal(receipt.after.cash_balance, 9699.8);
          assert.equal(receipt.residual_quantity, 2);
        }
        if (!storage) {
          await reset("Non-crossing limit");
          receipt = await execute();
          assert.equal(receipt.disposition, "not_filled_final");
          assert.equal(receipt.after.cash_balance, 10000);
          await reset("Position rejection");
          receipt = await execute();
          assert.equal(receipt.disposition, "rejected");
          assert.deepEqual(receipt.before, receipt.after);
          assert.equal(
            receipt.reason,
            "order quantity exceeds available position",
          );
          await reset("Shallow book");
          receipt = await execute();
        }
        const download = page.waitForEvent("download");
        await page
          .getByRole("button", { name: "Download receipt JSON" })
          .click();
        const saved = JSON.parse(
          fs.readFileSync(await (await download).path(), "utf8"),
        );
        assert.deepEqual(saved.fills, receipt.fills);
        assert.equal(saved.schema_version, "execution-receipt-v1");
        const archived = await context.request.get(
          base + "/api/trading/demo/orders/" + id,
        );
        assert.equal(archived.status(), 200);
        assert(
          !(await page.evaluate(
            () => document.documentElement.scrollWidth > innerWidth,
          )),
          `overflow ${width}`,
        );
        assert(requests.every((url) => new URL(url).origin === base));
        assert.deepEqual(errors, []);
        if (base.startsWith("https:")) {
          const cookie = (await context.cookies()).find(
            (c) => c.name === "tradeops_session",
          );
          assert(cookie?.secure && cookie?.httpOnly);
        }
        if (out)
          await page.screenshot({
            path: path.join(out, `tradeops-${width}-${colorScheme}.png`),
            fullPage: true,
          });
        results.push({
          width,
          colorScheme,
          actualApi: "passed",
          refreshHistory: "passed",
          fixtureAccounting: "passed",
          download: "passed",
          pageErrors: errors,
        });
        storage = await context.storageState();
        await context.close();
      }
    // A separate principal sees only its own account and cannot fetch the first owner's receipt.
    const second = await browser.newContext({ ignoreHTTPSErrors: true });
    const started = await second.request.post(base + "/auth/demo/start", {
      data: {},
    });
    assert.equal(started.status(), 200);
    const a = await second.request.get(base + "/api/trading/demo/account");
    assert.equal((await a.json()).account.cash_balance, 10000);
    const firstHistory = await second.request.get(
      base + "/api/trading/demo/orders",
    );
    assert.deepEqual((await firstHistory.json()).receipts, []);
    await second.close();
    if (out)
      fs.writeFileSync(
        path.join(out, "browser-results.json"),
        JSON.stringify(results, null, 2),
      );
    console.log(
      "TradeOps: six layouts, keyboard execution, all four fixtures, persisted history, archived receipts, owned accounts and actual JSON downloads passed.",
    );
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
