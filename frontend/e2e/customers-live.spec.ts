import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import type { APIRequestContext, Page, TestInfo } from '@playwright/test';
import { randomInt, randomUUID } from 'node:crypto';

const origin = 'http://127.0.0.1:4173';
function syntheticPhone() {
  return `+55119${randomInt(10000000, 99999999)}`;
}
function syntheticCpf() {
  let digits = String(randomInt(100000000, 999999999));
  for (const length of [9, 10]) {
    const sum = [...digits].reduce(
      (total, digit, index) => total + Number(digit) * (length + 1 - index),
      0,
    );
    digits += String(((sum * 10) % 11) % 10);
  }
  return digits;
}
async function login(page: Page, request: APIRequestContext) {
  const setup = await request.post('http://127.0.0.1:8000/__test/setup');
  expect(setup.status()).toBe(200);
  const account = (await setup.json()) as { email: string; token: string };
  const set = await request.post('http://127.0.0.1:8000/auth/password/set', {
    headers: { Origin: origin },
    data: {
      token: account.token,
      password: 'synthetic customer browser phrase',
    },
  });
  expect(set.status()).toBe(204);
  await page.goto('/clientes');
  await page
    .getByRole('textbox', { name: 'E-mail', exact: true })
    .fill(account.email);
  await page
    .getByLabel('Senha', { exact: true })
    .fill('synthetic customer browser phrase');
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Novo cliente' }),
  ).toBeVisible();
  return account;
}
async function visual(
  page: Page,
  info: TestInfo,
  phase: string,
  maskPersonal = true,
) {
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
    path: `test-results/evidence/${info.project.name}-customers-${phase}.png`,
    fullPage: true,
    maskColor: '#dce5d7',
    mask: maskPersonal
      ? [
          page.locator('.customer-contact:visible'),
          page.locator('.catalog-attributes dd:visible'),
          page.locator(
            'input:is([name="phone"], [name="cpf"], [name="rg"], [name="postal_code"], [name="street"], [name="number"], [name="complement"], [name="neighborhood"], [name="city"], [name="state"]):visible',
          ),
        ]
      : [],
  });
}
async function newForm(page: Page, name: string, phone: string) {
  await page.getByRole('button', { name: 'Novo cliente' }).click();
  await expect(
    page.getByRole('heading', { name: 'Novo cliente' }),
  ).toBeFocused();
  await page.getByLabel('Nome *', { exact: true }).fill(name);
  await page.getByLabel('Telefone / WhatsApp *', { exact: true }).fill(phone);
}
async function save(page: Page, method = 'POST') {
  const pending = page.waitForResponse(
    (response) =>
      response.request().method() === method &&
      /\/api\/customers(?:\/[0-9a-f-]+)?$/.test(response.url()),
  );
  await page
    .getByRole('button', { name: 'Salvar cliente', exact: true })
    .click();
  return await pending;
}
async function search(page: Page, value: string, kind = 'name') {
  await page.getByLabel('Buscar por', { exact: true }).selectOption(kind);
  await page.getByLabel('Busca', { exact: true }).fill(value);
  const pending = page.waitForResponse((response) =>
    response.url().endsWith('/api/customers/search'),
  );
  await page.getByRole('button', { name: 'Buscar', exact: true }).click();
  const response = await pending;
  expect(response.request().url()).toBe(`${origin}/api/customers/search`);
  expect(response.request().method()).toBe('POST');
  expect(response.status()).toBe(200);
  return (await response.json()) as { total: number; items: { id: string }[] };
}

test('real customers: progressive contact, document, versions, stable links and pagination', async ({
  page,
  request,
}, info) => {
  test.setTimeout(180_000);
  const account = await login(page, request);
  const prefix = `Pessoa ${info.project.name} ${randomUUID().slice(0, 8)}`;
  const phone = syntheticPhone();
  const cpf = syntheticCpf();
  await newForm(page, `${prefix} A`, phone);
  expect((await save(page)).status()).toBe(201);
  await expect(
    page.getByText(/Nenhuma locação confirmada registrada/),
  ).toBeVisible();
  await visual(page, info, 'minimum-detail');
  const link = await page
    .getByRole('link', { name: 'Link deste cliente' })
    .getAttribute('href');
  expect(link).toMatch(/^\/clientes\?cliente=[0-9a-f-]+$/);
  await page.getByRole('button', { name: 'Editar cliente' }).click();
  await page
    .getByText('Documentos e endereço (opcionais)', { exact: true })
    .click();
  await page.getByLabel('CPF', { exact: true }).fill(cpf);
  await page.getByLabel('Cidade', { exact: true }).fill('Cidade sintética');
  await page.getByLabel('UF', { exact: true }).fill('SP');
  const edit = await save(page, 'PATCH');
  expect(edit.status()).toBe(200);
  const first = (await edit.json()) as { id: string; version: number };
  expect(first.version).toBe(2);
  await page.getByRole('button', { name: 'Voltar à lista' }).click();
  await newForm(page, `${prefix} B`, phone);
  expect((await save(page)).status()).toBe(409);
  await expect(page.getByRole('alert')).toContainText('Este contato já está');
  await expect(page.getByLabel('Nome *')).toHaveValue(`${prefix} B`);
  await expect(
    page.getByRole('link', { name: /Consultar cadastro 1/ }),
  ).toHaveAttribute('target', '_blank');
  await visual(page, info, 'shared-warning');
  const confirmed = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      response.url().endsWith('/api/customers'),
  );
  await page
    .getByRole('button', { name: 'Confirmar pessoa distinta e salvar' })
    .click();
  expect((await confirmed).status()).toBe(201);
  await page.getByRole('button', { name: 'Voltar à lista' }).click();
  const byPhone = await search(page, phone, 'phone');
  expect(byPhone.total).toBe(2);
  const byCpf = await search(page, cpf, 'cpf');
  expect(byCpf.total).toBe(1);
  expect(byCpf.items[0].id).toBe(first.id);
  const invalidQuery = await page.request.post(
    `/api/customers/search?cpf=${cpf}`,
    { headers: { Origin: origin }, data: {} },
  );
  expect(invalidQuery.status()).toBe(422);
  expect(await invalidQuery.text()).not.toContain(cpf);
  expect(await invalidQuery.text()).not.toContain(phone);
  // Duplicate document keeps the original form and opens consultation in another tab.
  await newForm(page, `${prefix} C`, syntheticPhone());
  await page
    .getByText('Documentos e endereço (opcionais)', { exact: true })
    .click();
  await page.getByLabel('CPF', { exact: true }).fill(cpf);
  expect((await save(page)).status()).toBe(409);
  await expect(page.getByRole('alert')).toContainText('CPF já cadastrado');
  await expect(page.getByLabel('CPF', { exact: true })).toHaveValue(cpf);
  await visual(page, info, 'cpf-conflict');
  const popupPromise = page.waitForEvent('popup');
  await page.getByRole('link', { name: /Consultar cadastro 1/ }).click();
  const popup = await popupPromise;
  await expect(
    popup.getByRole('heading', { level: 2, name: `${prefix} A` }),
  ).toBeVisible();
  await popup.close();
  await expect(page.getByLabel('Nome *')).toHaveValue(`${prefix} C`);
  await page.getByRole('button', { name: 'Cancelar', exact: true }).click();
  await page.goto(link!);
  await expect(
    page.getByRole('heading', { level: 2, name: `${prefix} A` }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Editar cliente' }).click();
  await page
    .getByLabel('Observações', { exact: true })
    .fill('Rascunho sintético');
  const concurrent = await page.request.patch(`/api/customers/${first.id}`, {
    headers: { Origin: origin },
    data: { expected_version: 2, notes: 'Outra edição sintética' },
  });
  expect(concurrent.status()).toBe(200);
  expect((await save(page, 'PATCH')).status()).toBe(409);
  await page.getByRole('button', { name: 'Consultar versão atual' }).click();
  await expect(
    page.getByRole('heading', { name: 'Versão atual 3' }),
  ).toBeVisible();
  await expect(page.getByLabel('Observações', { exact: true })).toHaveValue(
    'Rascunho sintético',
  );
  await visual(page, info, 'version-comparison');
  await page
    .getByRole('button', { name: 'Manter meu rascunho e usar versão atual' })
    .click();
  // Revoke only this synthetic session to exercise the real auth/draft boundary.
  expect(
    (
      await page.request.post('/api/auth/logout', {
        headers: { Origin: origin },
        data: {},
      })
    ).status(),
  ).toBe(204);
  expect((await save(page, 'PATCH')).status()).toBe(401);
  await expect(
    page.getByRole('heading', { name: 'Entrar no RentalOps' }),
  ).toBeVisible();
  await page
    .getByRole('textbox', { name: 'E-mail', exact: true })
    .fill(account.email);
  await page
    .getByLabel('Senha', { exact: true })
    .fill('synthetic customer browser phrase');
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: `Editar ${prefix} A` }),
  ).toBeVisible();
  await expect(page.getByLabel('Observações', { exact: true })).toHaveValue(
    'Rascunho sintético',
  );
  expect((await save(page, 'PATCH')).status()).toBe(200);
  await page.getByRole('button', { name: 'Voltar à lista' }).click();
  // A separate synthetic namespace in the name makes paging independent of other tests.
  const pagePrefix = `${prefix} Paginação`;
  for (let index = 0; index < 26; index++) {
    const created = await page.request.post('/api/customers', {
      headers: { Origin: origin },
      data: {
        name: `${pagePrefix} ${String(index).padStart(2, '0')}`,
        phone: syntheticPhone(),
      },
    });
    expect(created.status()).toBe(201);
  }
  const results = await search(page, pagePrefix);
  expect(results.total).toBe(26);
  expect(results.items).toHaveLength(25);
  await page.getByRole('button', { name: 'Próxima', exact: true }).click();
  await expect(page.getByText('Página 2 de 2')).toBeVisible();
  await expect(
    page.getByRole('button', { name: `Abrir ${pagePrefix} 25`, exact: true }),
  ).toBeVisible();
  await visual(page, info, 'list-page2');
  await page.getByRole('button', { name: 'Novo cliente' }).click();
  await page.getByLabel('Nome *').fill(`${prefix} internacional`);
  await page.getByLabel('Telefone / WhatsApp *').fill('+44 20 8366 1177');
  await page.getByLabel('Telefone / WhatsApp *').clear();
  await visual(page, info, 'form');
});
