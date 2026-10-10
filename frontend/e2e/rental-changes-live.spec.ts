import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import type { Page, TestInfo } from '@playwright/test';
import { randomInt, randomUUID } from 'node:crypto';

const origin = 'http://127.0.0.1:4173';
const evidence =
  process.env.RENTALOPS_EVIDENCE_DIR ?? 'test-results/rop013-evidence';
async function post(page: Page, path: string, data: object, status = 200) {
  const response = await page.request.post(`/api/${path}`, {
    headers: { Origin: origin },
    data,
  });
  expect(response.status(), path).toBe(status);
  return await response.json();
}
async function seed(page: Page) {
  const account = await (
    await page.request.post('http://127.0.0.1:8000/__test/setup')
  ).json();
  expect(
    (
      await page.request.post('http://127.0.0.1:8000/auth/password/set', {
        headers: { Origin: origin },
        data: {
          token: account.token,
          password: 'synthetic rental changes browser phrase',
        },
      })
    ).status(),
  ).toBe(204);
  await page.goto('/locacoes');
  await page.getByLabel('E-mail', { exact: true }).fill(account.email);
  await page
    .getByLabel('Senha', { exact: true })
    .fill('synthetic rental changes browser phrase');
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Novo orçamento' }),
  ).toBeVisible();
  const suffix = randomUUID().slice(0, 8);
  const customer = await post(
    page,
    'customers',
    {
      name: `Synthetic changes ${suffix}`,
      phone: `+55119${randomInt(10000000, 99999999)}`,
    },
    201,
  );
  const product = await post(
    page,
    'products',
    { name: `Synthetic decor ${suffix}`, price: '400.00', initial_quantity: 1 },
    201,
  );
  const draft = {
    customer_id: customer.id,
    pickup_date: '2026-10-11',
    event_date: '2026-10-12',
    return_date: '2026-10-13',
    valid_until: '2026-10-10',
    lines: [{ kind: 'product', source_id: product.id, quantity: 1 }],
  };
  const offer = await post(page, 'quotations/preview', draft);
  const quotation = await post(
    page,
    'quotations',
    {
      ...draft,
      catalog_versions: offer.catalog_versions,
      request_id: randomUUID(),
    },
    201,
  );
  const received = await post(
    page,
    `quotations/${quotation.id}/payments/receipts`,
    {
      request_id: randomUUID(),
      expected_quotation_version: 1,
      expected_financial_version: 0,
      amount: '200.00',
      method: 'pix',
      business_date: '2026-10-08',
    },
  );
  await post(page, `quotations/${quotation.id}/payments/reconciliations`, {
    request_id: randomUUID(),
    expected_quotation_version: 1,
    expected_financial_version: 1,
    reason: 'Synthetic explicit reconciliation',
    applications: [
      {
        receipt_id: received.receipts[0].id,
        deposit: '200.00',
        balance: '0.00',
      },
    ],
  });
  const rental = await post(
    page,
    `quotations/${quotation.id}/confirm`,
    {
      request_id: randomUUID(),
      expected_quotation_version: 1,
      expected_financial_version: 2,
    },
    201,
  );
  await page.goto(`/locacoes?orcamento=${quotation.id}`);
  await expect(
    page.getByRole('button', { name: 'Alterar locação' }),
  ).toBeVisible();
  return { quotation, product, customer, rental };
}
async function visual(page: Page, info: TestInfo, name: string) {
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth <=
        document.documentElement.clientWidth,
    ),
  ).toBe(true);
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.screenshot({
    path: `${evidence}/${info.project.name}-${name}.png`,
    fullPage: true,
  });
  await page.screenshot({
    path: `${evidence}/${info.project.name}-${name}-viewport.png`,
  });
  if (name === 'change-preview')
    await page
      .getByRole('region', { name: 'Antes e depois da alteração' })
      .screenshot({ path: `${evidence}/${info.project.name}-change-diff.png` });
}
async function price(page: Page, value: string) {
  await page.getByRole('button', { name: 'Alterar locação' }).click();
  await expect(
    page.getByRole('heading', { name: 'Alterar aluguel do cliente' }),
  ).toBeFocused();
  await page
    .getByRole('checkbox', { name: 'Negociar preço / composição' })
    .check();
  await page.getByLabel('Preço unitário acordado (R$)').fill(value);
  await page
    .getByLabel('Motivo do preço / composição', { exact: true })
    .fill('Synthetic new agreement');
  await page
    .getByLabel('Motivo da nova revisão', { exact: true })
    .fill('Synthetic revised rental');
  await page.getByRole('button', { name: 'Calcular prévia' }).click();
  await expect(
    page.getByRole('region', { name: 'Antes e depois da alteração' }),
  ).toBeVisible();
}

test('change diff, unknown replay, reduction, approved cancellation and same-rental resumption', async ({
  page,
}, info) => {
  const { quotation, rental } = await seed(page);
  await price(page, '500.00');
  await expect(
    page.getByText('Total anterior R$ 400,00 → novo R$ 500,00'),
  ).toBeVisible();
  await visual(page, info, 'change-preview');
  const keys: string[] = [];
  let lost = 2;
  await page.route('**/api/rentals/*/changes', async (route) => {
    keys.push(route.request().postData()!);
    if (lost === 2) {
      lost -= 1;
      expect((await route.fetch()).status()).toBe(201);
      await route.abort();
    } else if (lost === 1) {
      lost -= 1;
      expect((await route.fetch()).status()).toBe(200);
      await route.fulfill({
        status: 502,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: 'Synthetic lost gateway acknowledgement',
        }),
      });
    } else await route.continue();
  });
  await page
    .getByRole('button', { name: 'Confirmar alteração da locação' })
    .click();
  await expect(
    page.getByText(/Resultado da gravação desconhecido/),
  ).toBeVisible();
  await expect(page.getByLabel('Preço unitário acordado (R$)')).toBeDisabled();
  await visual(page, info, 'change-unknown');
  await page
    .getByRole('button', { name: 'Reconciliar mesma gravação' })
    .click();
  await expect(
    page.getByRole('button', { name: 'Reconciliar mesma gravação' }),
  ).toBeEnabled();
  await expect(page.getByLabel('Preço unitário acordado (R$)')).toBeDisabled();
  await visual(page, info, 'change-unknown-http-502');
  await page
    .getByRole('button', { name: 'Reconciliar mesma gravação' })
    .click();
  await expect(
    page.getByRole('button', { name: 'Alterar locação' }),
  ).toBeVisible();
  expect(keys).toHaveLength(3);
  expect(keys[0]).toBe(keys[1]);
  expect(keys[0]).toBe(keys[2]);
  let current = await (
    await page.request.get(`/api/rentals/${rental.id}`)
  ).json();
  expect(current.current_financial.remaining).toBe('300.00');
  expect(current.current_financial.estimated_deposit).toBe('200.00');
  await price(page, '150.00');
  await page
    .getByRole('button', { name: 'Confirmar alteração da locação' })
    .click();
  await expect(
    page.getByRole('button', { name: 'Alterar locação' }),
  ).toBeVisible();
  current = await (await page.request.get(`/api/rentals/${rental.id}`)).json();
  expect(current.current_financial.remaining).toBe('0.00');
  expect(current.current_financial.excess).toBe('50.00');
  await page.getByRole('button', { name: 'Registrar cancelamento' }).click();
  await page
    .getByLabel('Motivo do cancelamento')
    .fill('Synthetic request only');
  await page
    .getByRole('button', { name: 'Registrar solicitação sem liberar estoque' })
    .click();
  await expect(
    page.getByText(
      /Solicitação registrada. A reserva e o estoque continuam comprometidos/,
    ),
  ).toBeVisible();
  current = await (await page.request.get(`/api/rentals/${rental.id}`)).json();
  expect(current.allocations).toHaveLength(1);
  await page.getByRole('button', { name: 'Registrar cancelamento' }).click();
  await page.getByRole('checkbox', { name: /A equipe aprova/ }).check();
  await page
    .getByRole('button', { name: 'Confirmar cancelamento aprovado' })
    .click();
  await expect(
    page.getByRole('button', { name: 'Revisar e retomar' }),
  ).toBeVisible();
  current = await (await page.request.get(`/api/rentals/${rental.id}`)).json();
  expect(current.allocations).toEqual([]);
  expect(current.current_financial.net_received).toBe('200.00');
  expect(current.current_financial.estimated_deposit).toBe('150.00');
  expect(current.current_financial.balance_remaining).toBe('0.00');
  expect(current.current_financial.remaining).toBe('0.00');
  await expect(
    page.getByText('Sem alocação de estoque', { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(/alocação foi preservada|reserva foi preservada/),
  ).toHaveCount(0);
  await visual(page, info, 'cancelled-money-pending');
  await page.getByRole('button', { name: 'Revisar e retomar' }).click();
  await page.getByLabel('Aplicar ao sinal do recebimento 1 (R$)').fill('75.00');
  await page.getByLabel('Aplicar ao saldo do recebimento 1 (R$)').fill('75.00');
  await page
    .getByLabel('Motivo da nova revisão', { exact: true })
    .fill('Synthetic reviewed resumption');
  await page.getByRole('checkbox', { name: /Conferi os preços/ }).check();
  await page.getByRole('button', { name: 'Calcular prévia' }).click();
  await page.getByRole('button', { name: 'Retomar em revisão' }).click();
  await expect(
    page.getByText(
      'Locação em revisão, sem alocação. A nova confirmação exige sinal válido e estoque disponível.',
    ),
  ).toBeVisible();
  current = await (await page.request.get(`/api/rentals/${rental.id}`)).json();
  expect(current.allocations).toEqual([]);
  expect(current.id).toBe(rental.id);
  expect(current.financial_snapshot.estimated_deposit).toBe('75.00');
  expect(current.financial_snapshot.deposit_validated).toBe(true);
  await visual(page, info, 'resumed-review');
  const confirmation = page.getByRole('region', {
    name: 'Reserva e estoque do período',
  });
  await confirmation
    .getByRole('button', { name: 'Consultar confirmação' })
    .click();
  await confirmation.getByRole('button', { name: 'Confirmar reserva' }).click();
  await expect(
    confirmation.getByText(/Reserva confirmada · locação v7/),
  ).toBeVisible();
  current = await (await page.request.get(`/api/rentals/${rental.id}`)).json();
  expect(current.id).toBe(rental.id);
  expect(current.allocations).toHaveLength(1);
  expect(current.current_financial.receipts).toHaveLength(1);
  const history = await (
    await page.request.get(`/api/rentals/${rental.id}/history`)
  ).json();
  expect(
    history.items.map((row: { operation: string }) => row.operation),
  ).toEqual([
    'confirmed',
    'changed',
    'changed',
    'cancel_requested',
    'cancelled',
    'resumed',
    'confirmed',
  ]);
  await visual(page, info, 'reconfirmed');
  await page.getByRole('link', { name: 'Abrir cliente vinculado' }).click();
  await expect(
    page.getByRole('link', {
      name: `Orçamento ${quotation.id.slice(0, 8)} · revisão 4`,
    }),
  ).toBeVisible();
});

test('capacity failure preserves prior commitment and comparing a financial conflict preserves the draft', async ({
  page,
}, info) => {
  const { quotation, rental } = await seed(page);
  await price(page, '500.00');
  await page.getByLabel('Quantidade', { exact: true }).fill('2');
  await page.getByRole('button', { name: 'Calcular prévia' }).click();
  await page
    .getByRole('button', { name: 'Confirmar alteração da locação' })
    .click();
  await expect(page.getByRole('alert')).toContainText(
    'Capacidade insuficiente',
  );
  let current = await (
    await page.request.get(`/api/rentals/${rental.id}`)
  ).json();
  expect(current.version).toBe(1);
  expect(current.allocations[0].quantity).toBe(1);
  await visual(page, info, 'capacity-error');
  await page.getByLabel('Quantidade', { exact: true }).fill('1');
  await page.getByRole('button', { name: 'Calcular prévia' }).click();
  await post(page, `quotations/${quotation.id}/payments/receipts`, {
    request_id: randomUUID(),
    expected_quotation_version: 1,
    expected_financial_version: 2,
    amount: '1.00',
    method: 'cash',
    business_date: '2026-10-08',
  });
  await page
    .getByRole('button', { name: 'Confirmar alteração da locação' })
    .click();
  await expect(
    page.getByRole('region', { name: 'Comparação de conflito' }),
  ).toContainText('financeiro v3');
  await page
    .getByRole('button', { name: 'Manter rascunho após comparar' })
    .click();
  await expect(page.getByLabel('Preço unitário acordado (R$)')).toHaveValue(
    '500.00',
  );
  await page.getByRole('button', { name: 'Calcular prévia' }).click();
  await page
    .getByRole('button', { name: 'Confirmar alteração da locação' })
    .click();
  await expect(
    page.getByRole('button', { name: 'Alterar locação' }),
  ).toBeVisible();
  current = await (await page.request.get(`/api/rentals/${rental.id}`)).json();
  expect(current.version).toBe(2);
  expect(current.allocations[0].quantity).toBe(1);
  expect(current.current_financial.remaining).toBe('299.00');
  await page.getByRole('button', { name: 'Alterar locação' }).focus();
  await page.keyboard.press('Enter');
  await expect(
    page.getByRole('heading', { name: 'Alterar aluguel do cliente' }),
  ).toBeFocused();
  await page.emulateMedia({ reducedMotion: 'reduce' });
  expect(
    await page.evaluate(
      () => matchMedia('(prefers-reduced-motion: reduce)').matches,
    ),
  ).toBe(true);
  await page.locator('html').evaluate((element) => {
    element.style.fontSize = '200%';
  });
  await visual(page, info, 'zoom-keyboard');
});

test('rental loading and unavailable reads stay explicit; expired quote resumes with no receipts or allocation', async ({
  page,
}, info) => {
  const { quotation, customer, product } = await seed(page);
  let release: () => void = () => {};
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/rentals/by-quotation/*', async (route) => {
    await pending;
    await route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Synthetic rental read unavailable' }),
    });
  });
  await page.goto(`/locacoes?orcamento=${quotation.id}`);
  const changes = page.getByRole('region', {
    name: 'Alterações no aluguel do cliente',
  });
  await expect(
    changes.getByText('Consultando alterações da locação…'),
  ).toBeVisible();
  await changes.scrollIntoViewIfNeeded();
  await visual(page, info, 'changes-loading');
  release();
  await expect(changes.getByRole('alert')).toContainText(
    'Não foi possível consultar a locação. Tente novamente.',
  );
  await expect(
    changes.getByText(/As alterações da reserva ficam disponíveis/),
  ).toHaveCount(0);
  await visual(page, info, 'changes-read-error');
  await page.unroute('**/api/rentals/by-quotation/*');
  await changes.getByRole('button', { name: 'Reconsultar alterações' }).click();
  await expect(
    changes.getByRole('button', { name: 'Alterar locação' }),
  ).toBeVisible();
  const draft = {
    customer_id: customer.id,
    pickup_date: '2026-10-15',
    event_date: '2026-10-16',
    return_date: '2026-10-17',
    valid_until: '2026-10-09',
    lines: [{ kind: 'product', source_id: product.id, quantity: 1 }],
  };
  const preview = await post(page, 'quotations/preview', draft);
  const expired = await post(
    page,
    'quotations',
    {
      ...draft,
      catalog_versions: preview.catalog_versions,
      request_id: randomUUID(),
    },
    201,
  );
  await page.goto(`/locacoes?orcamento=${expired.id}`);
  await expect(
    page.getByRole('button', { name: 'Revisar e retomar' }),
  ).toBeVisible();
  await visual(page, info, 'expired-empty');
  await page.getByRole('button', { name: 'Revisar e retomar' }).click();
  await expect(
    page.getByText(
      'Nenhum recebimento anterior. Retomar não confirma nem aloca estoque.',
    ),
  ).toBeVisible();
  await page
    .getByLabel('Validade comercial', { exact: true })
    .fill('2026-10-10');
  await page
    .getByLabel('Motivo da nova revisão', { exact: true })
    .fill('Synthetic expiry review');
  await page.getByRole('checkbox', { name: /Conferi os preços/ }).check();
  await page.getByRole('button', { name: 'Calcular prévia' }).click();
  await page.getByRole('button', { name: 'Retomar em revisão' }).click();
  await expect(
    page.getByText(
      'Locação em revisão, sem alocação. A nova confirmação exige sinal válido e estoque disponível.',
    ),
  ).toBeVisible();
  const current = await (
    await page.request.get(`/api/rentals/by-quotation/${expired.id}`)
  ).json();
  expect(current.state).toBe('review');
  expect(current.allocations).toEqual([]);
  expect(current.current_financial.receipts).toEqual([]);
});
