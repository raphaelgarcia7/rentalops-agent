import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import type { Page, TestInfo } from '@playwright/test';
import { randomInt, randomUUID } from 'node:crypto';

const origin = 'http://127.0.0.1:4173';
const png = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
  'base64',
);

async function post(page: Page, path: string, body: object, status = 200) {
  const response = await page.request.post(`/api/${path}`, {
    headers: { Origin: origin },
    data: body,
  });
  expect(response.status(), path).toBe(status);
  return await response.json();
}
async function setup(page: Page) {
  const response = await page.request.post(
    'http://127.0.0.1:8000/__test/setup',
  );
  expect(response.status()).toBe(200);
  const account = (await response.json()) as { email: string; token: string };
  expect(
    (
      await page.request.post('http://127.0.0.1:8000/auth/password/set', {
        headers: { Origin: origin },
        data: {
          token: account.token,
          password: 'synthetic payment browser phrase',
        },
      })
    ).status(),
  ).toBe(204);
  await page.goto('/locacoes');
  await page.getByLabel('E-mail', { exact: true }).fill(account.email);
  await page
    .getByLabel('Senha', { exact: true })
    .fill('synthetic payment browser phrase');
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Novo orçamento' }),
  ).toBeVisible();
  const suffix = randomUUID().slice(0, 8);
  const customer = await post(
    page,
    'customers',
    {
      name: `Synthetic payments ${suffix}`,
      phone: `+55119${randomInt(10000000, 99999999)}`,
    },
    201,
  );
  const product = await post(
    page,
    'products',
    {
      name: `Synthetic rental ${suffix}`,
      price: '400.00',
      initial_quantity: 3,
    },
    201,
  );
  const draft = {
    customer_id: customer.id,
    pickup_date: '2026-10-10',
    event_date: '2026-10-11',
    return_date: '2026-10-13',
    valid_until: '2026-10-09',
    lines: [{ kind: 'product', source_id: product.id, quantity: 1 }],
  };
  const preview = await post(page, 'quotations/preview', draft);
  const quote = await post(
    page,
    'quotations',
    {
      ...draft,
      request_id: randomUUID(),
      catalog_versions: preview.catalog_versions,
    },
    201,
  );
  await page.goto(`/locacoes?orcamento=${quote.id}`);
  await expect(
    page.getByRole('heading', { name: 'Financeiro deste orçamento' }),
  ).toBeVisible();
  return { quote, customer };
}
function section(page: Page) {
  return page.getByRole('region', { name: 'Financeiro deste orçamento' });
}
async function visual(page: Page, info: TestInfo, name: string) {
  await section(page).scrollIntoViewIfNeeded();
  const overflowing = await page.evaluate(() => ({
    root: {
      client: document.documentElement.clientWidth,
      scroll: document.documentElement.scrollWidth,
      inner: innerWidth,
    },
    elements: [...document.querySelectorAll('*')]
      .filter(
        (element) =>
          element.getBoundingClientRect().right > innerWidth ||
          element.scrollWidth > element.clientWidth,
      )
      .slice(-12)
      .map((element) => ({
        tag: element.tagName,
        className: element.className,
        right: element.getBoundingClientRect().right,
        client: element.clientWidth,
        scroll: element.scrollWidth,
      })),
  }));
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth <=
        document.documentElement.clientWidth,
    ),
    JSON.stringify(overflowing),
  ).toBe(true);
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.screenshot({
    path: `test-results/evidence/${info.project.name}-payments-${name}.png`,
    fullPage: true,
  });
  await section(page)
    .getByRole('heading', { name: 'Financeiro deste orçamento' })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `test-results/evidence/${info.project.name}-payments-${name}-viewport.png`,
  });
}
async function confirm(page: Page) {
  await section(page)
    .getByRole('button', { name: 'Revisar operação financeira' })
    .click();
  const button = section(page).getByRole('button', {
    name: 'Confirmar registro financeiro',
  });
  await expect(button).toBeFocused();
  await button.press('Enter');
  await expect(
    section(page).getByText(
      'Registro financeiro salvo. Isso não confirma reserva nem aloca estoque.',
    ),
  ).toBeVisible();
}

test('manual receipt, substitute reconciliation, correction, refund and private proof', async ({
  page,
}, info) => {
  const { quote, customer } = await setup(page);
  await expect(
    section(page).getByText(
      'Nenhum recebimento registrado. Comprovante é opcional.',
    ),
  ).toBeVisible();
  await visual(page, info, 'empty');
  await section(page).getByLabel('Valor em reais').fill('250,00');
  await section(page)
    .getByLabel('Observação (opcional)')
    .fill('Synthetic manual conference');
  await confirm(page);
  await expect(page.getByText(/nenhum pagamento foi registrado/i)).toHaveCount(
    0,
  );
  await expect(
    section(page).getByText('Sinal não validado', { exact: true }),
  ).toBeVisible();
  await section(page)
    .getByRole('button', { name: 'Conciliar distribuição completa' })
    .click();
  await section(page)
    .getByLabel('Aplicar ao sinal — recebimento 1')
    .fill('200.00');
  await section(page)
    .getByLabel('Aplicar ao saldo — recebimento 1')
    .fill('50.00');
  await section(page)
    .getByLabel('Motivo obrigatório')
    .fill('Synthetic explicit 200 deposit and 50 balance');
  await visual(page, info, 'reconciliation');
  await confirm(page);
  await expect(
    section(page).getByText('Sinal validado em um único recebimento', {
      exact: true,
    }),
  ).toBeVisible();
  await visual(page, info, 'deposit-validated');
  await section(page)
    .getByRole('button', { name: 'Corrigir recebimento', exact: true })
    .click();
  await section(page).getByLabel('Valor em reais').fill('100.00');
  await section(page)
    .getByLabel('Motivo obrigatório')
    .fill('Synthetic correction preserving original');
  await confirm(page);
  await expect(
    section(page).getByText('Sinal não validado', { exact: true }),
  ).toBeVisible();
  await section(page)
    .getByRole('button', {
      name: 'Registrar devolução já realizada',
      exact: true,
    })
    .click();
  await section(page).getByLabel('Valor em reais').fill('10.00');
  await section(page).getByLabel('Forma de pagamento').selectOption('cash');
  await section(page)
    .getByLabel('Motivo obrigatório')
    .fill('Synthetic real money already returned');
  await confirm(page);
  await section(page)
    .getByRole('button', { name: 'Anexar comprovante', exact: true })
    .click();
  await section(page)
    .getByLabel('Comprovante PDF, JPEG ou PNG (até 10.000.000 bytes)')
    .setInputFiles({
      name: 'synthetic-proof.png',
      mimeType: 'image/png',
      buffer: png,
    });
  await confirm(page);
  const download = section(page).getByRole('link', {
    name: 'Baixar comprovante 1 do recebimento 1',
  });
  const response = await page.request.get(
    (await download.getAttribute('href'))!,
  );
  expect(response.status()).toBe(200);
  expect(await response.body()).toEqual(png);
  expect(response.headers()['content-disposition']).toContain('attachment');
  await section(page)
    .getByText('Consultar antes e depois', { exact: true })
    .last()
    .click();
  await visual(page, info, 'history-proof');
  const state = await (
    await page.request.get(`/api/quotations/${quote.id}/payments`)
  ).json();
  expect(state).toMatchObject({
    received: '100.00',
    refunded: '10.00',
    net_received: '90.00',
    deposit_validated: false,
  });
  await page.evaluate(() => {
    document.documentElement.style.zoom = '200%';
  });
  await visual(page, info, 'zoom-200');
  await page.evaluate(() => {
    document.documentElement.style.zoom = '';
  });
  expect(
    await page.evaluate(
      () => matchMedia('(prefers-reduced-motion: reduce)').matches,
    ),
  ).toBe(true);
  await page.goto(`/clientes?cliente=${customer.id}`);
  await page
    .getByRole('link', { name: /^Orçamento / })
    .first()
    .click();
  await expect(
    page.getByRole('heading', { name: 'Financeiro deste orçamento' }),
  ).toBeVisible();
});

test('unknown commit replays same request and stale version preserves the form', async ({
  page,
}, info) => {
  const { quote } = await setup(page);
  const base = `/api/quotations/${quote.id}/payments`;
  const bodies: string[] = [];
  await page.route(`**${base}/receipts`, async (route) => {
    bodies.push(route.request().postData()!);
    if (bodies.length === 1) {
      const result = await route.fetch();
      expect(result.status()).toBe(200);
      await route.abort('failed');
    } else await route.continue();
  });
  await section(page).getByLabel('Valor em reais').fill('200.00');
  await section(page)
    .getByRole('button', { name: 'Revisar operação financeira' })
    .click();
  await section(page)
    .getByRole('button', { name: 'Confirmar registro financeiro' })
    .click();
  await expect(section(page).getByRole('alert')).toContainText(
    'Resultado desconhecido',
  );
  await expect(section(page).getByLabel('Valor em reais')).toBeDisabled();
  await visual(page, info, 'unknown');
  const committed = await (await page.request.get(base)).json();
  await post(page, `quotations/${quote.id}/payments/reconciliations`, {
    request_id: randomUUID(),
    expected_financial_version: 1,
    expected_quotation_version: 1,
    reason: 'Synthetic reconciliation while receipt acknowledgement is unknown',
    applications: [
      {
        receipt_id: committed.receipts[0].id,
        deposit: '200.00',
        balance: '0.00',
      },
    ],
  });
  await section(page)
    .getByRole('button', { name: 'Repetir a mesma operação' })
    .click();
  await expect(
    section(page).getByText(/Registro financeiro salvo/),
  ).toBeVisible();
  expect(bodies).toHaveLength(2);
  expect(bodies[0]).toBe(bodies[1]);
  await expect(
    section(page).getByText(/Versão comercial 1 · Financeiro 2 · Conferida 1/),
  ).toBeVisible();
  await expect(
    section(page).getByText('Sinal validado em um único recebimento'),
  ).toBeVisible();
  await expect(
    section(page).getByText(/Conciliação substituída · financeiro 2/),
  ).toBeVisible();
  await visual(page, info, 'replay-current-financial');
  await page.unroute(`**${base}/receipts`);
  await section(page)
    .getByRole('button', { name: 'Novo recebimento', exact: true })
    .click();
  await section(page).getByLabel('Valor em reais').fill('25.00');
  await section(page)
    .getByRole('button', { name: 'Revisar operação financeira' })
    .click();
  await post(page, `quotations/${quote.id}/payments/receipts`, {
    request_id: randomUUID(),
    expected_financial_version: 2,
    expected_quotation_version: 1,
    amount: '10.00',
    method: 'cash',
    business_date: '2026-10-08',
  });
  await section(page)
    .getByRole('button', { name: 'Confirmar registro financeiro' })
    .click();
  await expect(section(page).getByRole('alert')).toContainText(
    'Os dados financeiros ou comerciais mudaram',
  );
  await expect(section(page).getByLabel('Valor em reais')).toHaveValue('25.00');
  await visual(page, info, 'version-conflict');
  await confirm(page);
  const result = await (await page.request.get(base)).json();
  expect(result.receipts).toHaveLength(3);
  expect(result.received).toBe('235.00');
  let release: (() => Promise<void>) | undefined;
  await page.route(`**${base}`, async (route) => {
    release = () => route.continue();
  });
  await section(page)
    .getByRole('button', { name: 'Reconsultar financeiro' })
    .click();
  await expect(
    section(page).getByText('Consultando financeiro…'),
  ).toBeVisible();
  await visual(page, info, 'loading');
  await release!();
  await page.unroute(`**${base}`);
  await expect(
    section(page).getByText('Consultando financeiro…'),
  ).not.toBeVisible();
  await page.route(`**${base}`, (route) => route.abort());
  await section(page)
    .getByRole('button', { name: 'Reconsultar financeiro' })
    .click();
  await expect(section(page).getByRole('alert')).toContainText(
    'Não foi possível consultar',
  );
  await visual(page, info, 'error');
  await page.unroute(`**${base}`);
  await section(page)
    .getByRole('button', { name: 'Reconsultar financeiro' })
    .click();
  await expect(section(page).getByRole('alert')).not.toBeVisible();
});
