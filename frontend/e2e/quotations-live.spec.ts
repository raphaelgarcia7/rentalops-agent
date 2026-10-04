import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import type { Page, TestInfo } from '@playwright/test';
import { randomInt, randomUUID } from 'node:crypto';

const origin = 'http://127.0.0.1:4173';
async function login(page: Page) {
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
          password: 'synthetic quotation browser phrase',
        },
      })
    ).status(),
  ).toBe(204);
  await page.goto('/locacoes');
  await page
    .getByRole('textbox', { name: 'E-mail', exact: true })
    .fill(account.email);
  await page
    .getByLabel('Senha', { exact: true })
    .fill('synthetic quotation browser phrase');
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Novo orçamento' }),
  ).toBeVisible();
  return account;
}
async function post(page: Page, path: string, data: object, status = 201) {
  const response = await page.request.post(`/api/${path}`, {
    headers: { Origin: origin },
    data,
  });
  expect(response.status(), path).toBe(status);
  return (await response.json()) as Record<string, unknown>;
}
async function seed(page: Page) {
  const suffix = randomUUID().slice(0, 8);
  const name = `Synthetic quote ${suffix}`;
  const customer = await post(page, 'customers', {
    name,
    phone: `+55119${randomInt(10000000, 99999999)}`,
  });
  const arch = await post(page, 'products', {
    name: `Synthetic arch ${suffix}`,
    price: '40.00',
    initial_quantity: 3,
  });
  const vase = await post(page, 'products', {
    name: `Synthetic vase ${suffix}`,
    price: '10.00',
    initial_quantity: 5,
  });
  await post(
    page,
    `products/${vase.id}/maintenance`,
    { expected_version: 1, quantity: 1, reason: 'Synthetic maintenance' },
    200,
  );
  const kit = await post(page, 'kits', {
    name: `Synthetic kit ${suffix}`,
    price: '195.00',
    items: [
      { product_id: arch.id, quantity: 1 },
      { product_id: vase.id, quantity: 2 },
    ],
  });
  return { customer, arch, vase, kit, name, suffix };
}
async function visual(page: Page, info: TestInfo, phase: string) {
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
    path: `test-results/evidence/${info.project.name}-quotations-${phase}.png`,
    fullPage: true,
    mask: [
      page.locator('.customer-contact:visible'),
      page.locator('.catalog-attributes dd:visible'),
    ],
    maskColor: '#dce5d7',
  });
}
async function fillBase(page: Page, seeded: Awaited<ReturnType<typeof seed>>) {
  await page.getByRole('button', { name: 'Novo orçamento' }).click();
  await expect(
    page.getByRole('heading', { name: 'Novo orçamento' }),
  ).toBeFocused();
  await page
    .getByLabel('Buscar cliente por nome', { exact: true })
    .fill(seeded.name);
  await page
    .getByLabel('Cliente', { exact: true })
    .selectOption(String(seeded.customer.id));
  await page
    .getByLabel('Retirada prevista', { exact: true })
    .fill('2026-10-10');
  await page.getByLabel('Data do evento', { exact: true }).fill('2026-10-11');
  await page
    .getByLabel('Devolução prevista', { exact: true })
    .fill('2026-10-13');
  await page
    .getByLabel('Validade comercial', { exact: true })
    .fill('2026-10-09');
  await page.getByLabel('Horário da retirada (opcional)').fill('10:00');
  await page
    .getByLabel('Buscar no catálogo', { exact: true })
    .fill(seeded.suffix);
  await page
    .getByLabel('Item do catálogo', { exact: true })
    .selectOption(String(seeded.kit.id));
  await page
    .getByRole('button', { name: 'Adicionar item', exact: true })
    .click();
  await page
    .getByRole('region', { name: 'Linha 1', exact: true })
    .getByLabel('Quantidade', { exact: true })
    .fill('2');
  await page
    .getByLabel('Tipo de item', { exact: true })
    .selectOption('product');
  await page
    .getByLabel('Item do catálogo', { exact: true })
    .selectOption(String(seeded.vase.id));
  await page
    .getByRole('button', { name: 'Adicionar item', exact: true })
    .click();
}

test('real quotation agreement, custom composition, revisions, expiration, conflicts and replay', async ({
  page,
}, info) => {
  test.setTimeout(120000);
  const account = await login(page);
  const seeded = await seed(page);
  await fillBase(page, seeded);
  await page
    .getByLabel('Tipo de desconto', { exact: true })
    .selectOption('percent');
  await page.getByLabel('Valor do desconto', { exact: true }).fill('10');
  await page
    .getByLabel('Motivo do desconto', { exact: true })
    .fill('Synthetic discount agreement');
  await page
    .getByRole('button', { name: 'Calcular prévia', exact: true })
    .click();
  await expect(page.getByText('Demanda 5 · Apto 4')).toBeVisible();
  await expect(page.getByText('Faltam 1 · pendência comercial')).toBeVisible();
  await expect(
    page
      .getByRole('region', { name: 'Prévia comercial do servidor' })
      .getByText('R$ 360,00', { exact: true }),
  ).toBeVisible();
  await visual(page, info, 'preview-shortage');
  // Changing a catalog source after preview must be a useful 409, never a silent price refresh.
  const changed = await page.request.patch(`/api/products/${seeded.vase.id}`, {
    headers: { Origin: origin },
    data: { name: seeded.vase.name, price: '12.00', expected_version: 2 },
  });
  expect(changed.status()).toBe(200);
  await page
    .getByRole('button', { name: 'Salvar orçamento', exact: true })
    .click();
  await expect(page.getByRole('alert')).toContainText('Os dados mudaram');
  await expect(page.getByRole('alert')).toBeFocused();
  await expect(
    page.getByLabel('Motivo do desconto', { exact: true }),
  ).toHaveValue('Synthetic discount agreement');
  await visual(page, info, 'catalog-conflict');
  const first = page.getByRole('region', { name: 'Linha 1', exact: true });
  await first.getByLabel('Negociar preço / composição').check();
  await first.getByLabel('Preço unitário acordado (R$)').fill('180.01');
  await first
    .getByLabel('Motivo do preço / composição')
    .fill('Synthetic custom kit agreement');
  await first.getByLabel('Quantidade do componente 2').fill('3');
  await page
    .getByRole('button', { name: 'Calcular prévia', exact: true })
    .click();
  await expect(page.getByText('Demanda 7 · Apto 4')).toBeVisible();
  await visual(page, info, 'customized');
  // Commit succeeded but the response was lost: replay must reconcile the same request ID.
  let requestId = '';
  await page.route(
    '**/api/quotations',
    async (route) => {
      const body = route.request().postDataJSON() as { request_id: string };
      requestId = body.request_id;
      const actual = await route.fetch();
      expect(actual.status()).toBe(201);
      await route.abort('failed');
    },
    { times: 1 },
  );
  await page
    .getByRole('button', { name: 'Salvar orçamento', exact: true })
    .click();
  await expect(
    page.getByRole('button', { name: 'Reconciliar mesma gravação' }),
  ).toBeVisible();
  await expect(
    page.getByLabel('Motivo do desconto', { exact: true }),
  ).toBeDisabled();
  await page.route(
    '**/api/quotations',
    async (route) => {
      expect(
        (route.request().postDataJSON() as { request_id: string }).request_id,
      ).toBe(requestId);
      await route.continue();
    },
    { times: 1 },
  );
  await page
    .getByRole('button', { name: 'Reconciliar mesma gravação' })
    .click();
  await expect(
    page.getByText(
      'Orçamento salvo com sucesso. Nenhum estoque foi reservado.',
    ),
  ).toBeVisible();
  const id = new URL(page.url()).searchParams.get('orcamento')!;
  const saved = (await (
    await page.request.get(`/api/quotations/${id}`)
  ).json()) as {
    version: number;
    lines: { unit_price: string }[];
    total: string;
  };
  expect(saved.version).toBe(1);
  expect(saved.lines[0].unit_price).toBe('180.01');
  expect(
    (
      (await (await page.request.get(`/api/kits/${seeded.kit.id}`)).json()) as {
        price: string;
      }
    ).price,
  ).toBe('195.00');
  await visual(page, info, 'saved');
  const vaseDetail = (await (
    await page.request.get(`/api/products/${seeded.vase.id}`)
  ).json()) as { version: number; maintenance: { id: string }[] };
  await post(
    page,
    `products/${seeded.vase.id}/maintenance/${vaseDetail.maintenance[0].id}/release`,
    {
      expected_version: vaseDetail.version,
      quantity: 1,
      reason: 'Synthetic maintenance release',
    },
    200,
  );
  await page
    .getByRole('button', { name: 'Reconsultar estoque cadastral' })
    .click();
  await expect(
    page.getByText(
      'O estoque cadastral mudou desde a última consulta. Os valores e a composição acordados foram preservados.',
    ),
  ).toBeVisible();
  await page.getByRole('link', { name: 'Abrir cliente vinculado' }).click();
  await expect(
    page.getByRole('heading', { name: 'Orçamentos deste cliente' }),
  ).toBeVisible();
  await page
    .getByRole('link', { name: new RegExp(`Orçamento ${id.slice(0, 8)}`) })
    .click();
  await page.getByRole('button', { name: 'Criar nova revisão' }).click();
  await page
    .getByLabel('Motivo da nova revisão', { exact: true })
    .fill('Synthetic preserved negotiation');
  await page
    .getByRole('button', { name: 'Calcular prévia', exact: true })
    .click();
  await page.getByRole('button', { name: 'Salvar nova revisão' }).click();
  await expect(
    page.getByText('ORÇAMENTO · REVISÃO 2', { exact: true }),
  ).toBeVisible();
  expect(
    (
      (await (
        await page.request.get(`/api/quotations/${id}/versions/1`)
      ).json()) as { total: string }
    ).total,
  ).toBe(saved.total);
  await page.getByRole('button', { name: 'Criar nova revisão' }).click();
  await page
    .getByLabel('Motivo da nova revisão', { exact: true })
    .fill('Synthetic retained local draft');
  const current = (await (
    await page.request.get(`/api/quotations/${id}`)
  ).json()) as {
    customer_id: string;
    version: number;
    lines: { id: string; kind: string; source_id: string; quantity: number }[];
  };
  const concurrent = {
    customer_id: current.customer_id,
    quotation_id: id,
    expected_version: current.version,
    pickup_date: '2026-10-10',
    event_date: '2026-10-11',
    return_date: '2026-10-13',
    valid_until: '2026-10-09',
    lines: current.lines.map((line) => ({
      kind: line.kind,
      source_id: line.source_id,
      quantity: line.quantity,
      retained_line_id: line.id,
    })),
  };
  const preview = await post(page, 'quotations/preview', concurrent, 200);
  await post(page, `quotations/${id}/versions`, {
    ...concurrent,
    request_id: randomUUID(),
    catalog_versions: preview.catalog_versions,
    reason: 'Synthetic other attendant',
  });
  await page
    .getByRole('button', { name: 'Calcular prévia', exact: true })
    .click();
  await expect(page.getByRole('alert')).toContainText('Os dados mudaram');
  // A conflict at preview also offers current-version comparison; save-path conflict below is deterministic.
  await expect(
    page.getByLabel('Motivo da nova revisão', { exact: true }),
  ).toHaveValue('Synthetic retained local draft');
  await visual(page, info, 'revision-conflict');
  await expect(
    page.getByRole('heading', { name: 'Versão atual 3' }),
  ).toBeVisible();
  await page
    .getByRole('button', { name: 'Manter rascunho após comparar' })
    .click();
  await page
    .getByRole('region', { name: 'Linha 2', exact: true })
    .getByLabel('Motivo do preço / composição')
    .fill('Synthetic price preserved after comparing current revision');
  await page
    .getByLabel('Validade comercial', { exact: true })
    .fill('2026-10-01');
  await page
    .getByLabel('Motivo da nova revisão', { exact: true })
    .fill('Synthetic historical expired agreement');
  await page
    .getByRole('button', { name: 'Calcular prévia', exact: true })
    .click();
  await expect(
    page.getByText('Vencido · requer nova revisão antes de fechar'),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Salvar nova revisão' }).click();
  await expect(
    page.getByText('ORÇAMENTO · REVISÃO 4', { exact: true }),
  ).toBeVisible();
  await visual(page, info, 'expired');
  await page.getByRole('button', { name: 'Criar nova revisão' }).click();
  await page
    .getByLabel('Validade comercial', { exact: true })
    .fill('2026-10-09');
  await page
    .getByLabel('Motivo da nova revisão', { exact: true })
    .fill('Synthetic renewal after human review');
  // Real session loss keeps the negotiated draft in memory through login.
  expect(
    (
      await page.request.post('/api/auth/logout', {
        headers: { Origin: origin },
        data: {},
      })
    ).status(),
  ).toBe(204);
  await page
    .getByRole('button', { name: 'Calcular prévia', exact: true })
    .click();
  await expect(
    page.getByRole('button', { name: 'Entrar', exact: true }),
  ).toBeVisible();
  await page
    .getByRole('textbox', { name: 'E-mail', exact: true })
    .fill(account.email);
  await page
    .getByLabel('Senha', { exact: true })
    .fill('synthetic quotation browser phrase');
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await expect(
    page.getByLabel('Motivo da nova revisão', { exact: true }),
  ).toHaveValue('Synthetic renewal after human review');
  await page
    .getByRole('button', { name: 'Calcular prévia', exact: true })
    .click();
  await page.getByRole('button', { name: 'Salvar nova revisão' }).click();
  await expect(
    page.getByText('ORÇAMENTO · REVISÃO 5', { exact: true }),
  ).toBeVisible();
  await visual(page, info, 'renewed');
  const catalogKit = (await (
    await page.request.get(`/api/kits/${seeded.kit.id}`)
  ).json()) as {
    version: number;
    name: string;
    items: { product_id: string; quantity: number }[];
  };
  expect(
    (
      await page.request.patch(`/api/kits/${seeded.kit.id}`, {
        headers: { Origin: origin },
        data: {
          name: catalogKit.name,
          price: '210.00',
          expected_version: catalogKit.version,
          items: catalogKit.items.map((item) => ({
            product_id: item.product_id,
            quantity: item.quantity,
          })),
        },
      })
    ).status(),
  ).toBe(200);
  await page.getByRole('button', { name: 'Criar nova revisão' }).click();
  await page
    .getByRole('region', { name: 'Linha 1', exact: true })
    .getByRole('button', { name: 'Usar valores atuais do catálogo' })
    .click();
  await page
    .getByLabel('Motivo da nova revisão', { exact: true })
    .fill('Synthetic explicit source update');
  await page
    .getByRole('button', { name: 'Calcular prévia', exact: true })
    .click();
  await expect(
    page
      .getByRole('region', { name: 'Prévia comercial do servidor' })
      .getByText('R$ 432,00', { exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Salvar nova revisão' }).click();
  await expect(
    page.getByText('ORÇAMENTO · REVISÃO 6', { exact: true }),
  ).toBeVisible();
  expect(
    (
      (await (await page.request.get(`/api/quotations/${id}`)).json()) as {
        lines: { unit_price: string }[];
      }
    ).lines[0].unit_price,
  ).toBe('210.00');
  expect(
    (
      (await (
        await page.request.get(`/api/quotations/${id}/versions/1`)
      ).json()) as { total: string }
    ).total,
  ).toBe(saved.total);
  await visual(page, info, 'explicit-catalog-update');
});

test('quotation loading, empty, error retry, keyboard and reduced motion', async ({
  page,
}, info) => {
  test.setTimeout(90000);
  await login(page);
  await page.route(
    '**/api/quotations/search',
    async (route) => {
      await route.fulfill({
        status: 503,
        json: { detail: 'Serviço indisponível.' },
      });
    },
    { times: 1 },
  );
  await page.getByRole('button', { name: 'Buscar orçamentos' }).click();
  await expect(page.getByRole('alert')).toContainText('Serviço indisponível');
  await visual(page, info, 'error');
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(
    '**/api/quotations/search',
    async (route) => {
      await gate;
      await route.fulfill({
        json: { items: [], total: 0, page: 1, page_size: 25 },
      });
    },
    { times: 1 },
  );
  await page
    .getByRole('button', { name: 'Tentar novamente', exact: true })
    .click();
  await expect(page.getByText('Carregando orçamentos…')).toBeVisible();
  await visual(page, info, 'loading');
  release();
  await expect(
    page.getByRole('heading', { name: 'Seu primeiro orçamento começa aqui' }),
  ).toBeVisible();
  await visual(page, info, 'empty');
  await page.getByRole('button', { name: 'Novo orçamento' }).focus();
  await page.keyboard.press('Enter');
  await expect(
    page.getByRole('heading', { name: 'Novo orçamento' }),
  ).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(
    page.getByLabel('Buscar cliente por nome', { exact: true }),
  ).toBeFocused();
  expect(
    await page
      .getByLabel('Buscar cliente por nome', { exact: true })
      .evaluate((element) => getComputedStyle(element).outlineStyle),
  ).not.toBe('none');
  expect(
    await page.evaluate(
      () => matchMedia('(prefers-reduced-motion: reduce)').matches,
    ),
  ).toBe(true);
  await visual(page, info, 'keyboard');
  await page.getByRole('button', { name: 'Cancelar edição' }).click();
  await expect(
    page.getByRole('button', { name: 'Novo orçamento' }),
  ).toBeFocused();
});
