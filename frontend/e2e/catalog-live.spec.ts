import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import type { APIRequestContext, Page, TestInfo } from '@playwright/test';
import { randomUUID } from 'node:crypto';

const origin = 'http://127.0.0.1:4173';
const syntheticPng = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
  'base64',
);

async function login(page: Page, request: APIRequestContext) {
  const setup = await request.post('http://127.0.0.1:8000/__test/setup');
  expect(setup.status()).toBe(200);
  const account = (await setup.json()) as { email: string; token: string };
  const result = await request.post('http://127.0.0.1:8000/auth/password/set', {
    headers: { Origin: origin },
    data: {
      token: account.token,
      password: 'synthetic catalog browser phrase',
    },
  });
  expect(result.status()).toBe(204);
  await page.goto('/catalogo');
  await page.getByLabel('E-mail', { exact: true }).fill(account.email);
  await page
    .getByLabel('Senha', { exact: true })
    .fill('synthetic catalog browser phrase');
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Novo produto' }),
  ).toBeVisible();
}

async function visual(page: Page, info: TestInfo, phase: string) {
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth <=
        document.documentElement.clientWidth,
    ),
  ).toBe(true);
  const result = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
    .analyze();
  expect(result.violations).toEqual([]);
  await page.screenshot({
    path: `test-results/evidence/${info.project.name}-catalog-${phase}.png`,
    fullPage: true,
  });
}

async function createProduct(
  page: Page,
  name: string,
  quantity: string,
  optional = false,
) {
  await page.getByRole('button', { name: 'Novo produto' }).click();
  await expect(
    page.getByRole('heading', { name: 'Novo produto' }),
  ).toBeFocused();
  await page.getByLabel('Nome', { exact: true }).fill(name);
  await page
    .getByLabel('Preço por locação (R$)', { exact: true })
    .fill('100,01');
  await page.getByLabel('Quantidade inicial').fill(quantity);
  if (optional) {
    await page.getByText('Mais detalhes (opcionais)', { exact: true }).click();
    await page
      .getByLabel('Observação', { exact: true })
      .fill('Observação sintética preservada');
    await page.getByLabel('Cor', { exact: true }).fill('Branca');
  }
  const saved = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      response.url().endsWith('/api/products'),
  );
  await page.getByRole('button', { name: 'Salvar cadastro' }).click();
  const response = await saved;
  expect(response.status()).toBe(201);
  const product = (await response.json()) as { id: string; version: number };
  await expect(page.getByRole('heading', { level: 2, name })).toBeVisible();
  return product;
}

async function search(page: Page, name: string) {
  await page.getByLabel('Buscar por nome').fill(name);
  await page.getByRole('button', { name: 'Buscar', exact: true }).click();
  await expect(
    page.getByRole('button', { name: `Abrir ${name}`, exact: true }),
  ).toBeVisible();
}

test('real catalog: products, kits, stock, maintenance, private photos and review', async ({
  page,
  request,
}, info) => {
  test.setTimeout(120_000);
  const suffix = `${info.project.name}-${randomUUID().slice(0, 8)}`;
  const whiteName = `Mesa branca ${suffix}`;
  const blackName = `Mesa preta ${suffix}`;
  const kitName = `Kit festa ${suffix}`;
  await login(page, request);
  const white = await createProduct(page, whiteName, '5', true);
  await expect(
    page.getByText('Observação sintética preservada', { exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/Sem foto/)).toBeVisible();
  await visual(page, info, 'product');
  await page.getByRole('button', { name: 'Registrar manutenção' }).click();
  await expect(
    page.getByRole('heading', { name: 'Registrar manutenção', exact: true }),
  ).toBeFocused();
  await page.getByLabel('Quantidade da operação').fill('1');
  await page.getByLabel('Motivo', { exact: true }).fill('Avaria sintética');
  await page
    .getByRole('button', { name: 'Registrar manutenção', exact: true })
    .last()
    .click();
  await expect(
    page.locator('.catalog-stock').getByText('4', { exact: true }),
  ).toBeVisible();
  await expect(
    page.locator('.catalog-stock').getByText('1', { exact: true }),
  ).toBeVisible();
  await visual(page, info, 'maintenance');
  await page
    .getByRole('button', { name: 'Liberar manutenção: Avaria sintética' })
    .click();
  await page
    .getByLabel('Motivo', { exact: true })
    .fill('Conferência sintética: apta');
  await page
    .getByRole('button', { name: 'Liberar unidades', exact: true })
    .click();
  await expect(
    page.locator('.catalog-stock').getByText('5', { exact: true }),
  ).toHaveCount(2);
  await page
    .getByRole('button', { name: 'Ajustar estoque', exact: true })
    .click();
  await page.getByLabel('Quantidade da operação').fill('2');
  await page.getByLabel('Motivo', { exact: true }).fill('Entrada sintética');
  await page
    .getByRole('button', { name: 'Ajustar estoque', exact: true })
    .last()
    .click();
  await expect(
    page.locator('.catalog-stock').getByText('7', { exact: true }),
  ).toHaveCount(2);
  await page.getByLabel('Adicionar foto').setInputFiles({
    name: 'synthetic.png',
    mimeType: 'image/png',
    buffer: syntheticPng,
  });
  await page.getByRole('button', { name: 'Enviar foto' }).click();
  await expect(page.getByText('Foto principal', { exact: true })).toBeVisible();
  await expect(
    page.getByRole('img', { name: `Foto de ${whiteName}` }),
  ).toBeVisible();
  await visual(page, info, 'photo');
  await page.getByRole('button', { name: 'Voltar à lista' }).click();
  const black = await createProduct(page, blackName, '2');
  await page.getByRole('button', { name: 'Voltar à lista' }).click();
  await page.getByRole('button', { name: 'Kits', exact: true }).click();
  await page.getByRole('button', { name: 'Novo kit' }).click();
  await page.getByLabel('Nome', { exact: true }).fill(kitName);
  await page
    .getByLabel('Preço por locação (R$)', { exact: true })
    .fill('50,01');
  await page.getByLabel('Buscar produto para o kit').fill(whiteName);
  await page
    .getByRole('button', { name: 'Buscar produtos', exact: true })
    .click();
  await page
    .getByRole('button', { name: `Adicionar ${whiteName}`, exact: true })
    .click();
  await page
    .getByRole('button', { name: `Adicionar ${whiteName}`, exact: true })
    .click();
  await expect(page.getByLabel(`Quantidade de ${whiteName}`)).toHaveValue('2');
  expect(
    await page.getByRole('button', { name: `Adicionar ${kitName}` }).count(),
  ).toBe(0);
  await visual(page, info, 'kit-form');
  const kitSave = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      response.url().endsWith('/api/kits'),
  );
  await page.getByRole('button', { name: 'Salvar cadastro' }).click();
  const kitResponse = await kitSave;
  expect(kitResponse.status()).toBe(201);
  const kit = (await kitResponse.json()) as { id: string; price: string };
  expect(kit.price).toBe('50.01');
  await expect(page.getByText(/Kit sem estoque próprio/)).toBeVisible();
  await visual(page, info, 'kit');
  await page.getByRole('button', { name: 'Voltar à lista' }).click();
  await page.getByRole('button', { name: 'Produtos', exact: true }).click();
  await search(page, whiteName);
  await page
    .getByRole('button', { name: `Abrir ${whiteName}`, exact: true })
    .click();
  await page.getByRole('button', { name: 'Editar cadastro' }).click();
  await page
    .getByLabel('Preço por locação (R$)', { exact: true })
    .fill('200,01');
  await page.getByRole('button', { name: 'Salvar cadastro' }).click();
  await expect(page.locator('.catalog-price')).toContainText('200,01');
  const storedKit = await page.request.get(`/api/kits/${kit.id}`);
  expect((await storedKit.json()).price).toBe('50.01');
  const storedBlack = await page.request.get(`/api/products/${black.id}`);
  expect((await storedBlack.json()).total_quantity).toBe(2);
  await page.getByRole('button', { name: 'Inativar produto' }).click();
  await page.getByLabel('Motivo', { exact: true }).fill('Inativação sintética');
  await page.getByRole('button', { name: 'Confirmar inativação' }).click();
  await expect(page.getByText('Inativo', { exact: true })).toBeVisible();
  const retiredWhite = await page.request.get(`/api/products/${white.id}`);
  expect((await retiredWhite.json()).movements.length).toBe(4);
  await page.getByRole('button', { name: 'Voltar à lista' }).click();
  await page.getByRole('button', { name: 'Kits', exact: true }).click();
  await search(page, kitName);
  await expect(
    page.getByText('Precisa de revisão', { exact: true }),
  ).toBeVisible();
  await page
    .getByRole('button', { name: `Abrir ${kitName}`, exact: true })
    .click();
  await expect(page.getByText(/Kit precisa de revisão/)).toBeVisible();
  await visual(page, info, 'kit-review');
  await page.getByRole('button', { name: 'Revisar kit' }).click();
  await page
    .getByRole('button', { name: `Remover ${whiteName}`, exact: true })
    .click();
  await page.getByLabel('Buscar produto para o kit').fill(blackName);
  await page
    .getByRole('button', { name: 'Buscar produtos', exact: true })
    .click();
  await page
    .getByRole('button', { name: `Adicionar ${blackName}`, exact: true })
    .click();
  await page.getByRole('button', { name: 'Salvar cadastro' }).click();
  await expect(
    page.getByRole('heading', { name: kitName, level: 2 }),
  ).toBeVisible();
  expect(
    (await (await page.request.get(`/api/kits/${kit.id}`)).json()).needs_review,
  ).toBe(false);
  await visual(page, info, 'kit-revised');
});

test('real catalog: stale edit retains draft; keyboard focus and photo gallery changes', async ({
  page,
  request,
}, info) => {
  test.setTimeout(90_000);
  const name = `Vaso ${info.project.name}-${randomUUID().slice(0, 8)}`;
  await login(page, request);
  const record = await createProduct(page, name, '0');
  await page.getByRole('button', { name: 'Editar cadastro' }).click();
  await page.getByLabel('Nome', { exact: true }).fill(`${name} rascunho`);
  const concurrent = await page.request.patch(`/api/products/${record.id}`, {
    headers: { Origin: origin },
    data: { expected_version: 1, name: `${name} atual`, price: '150.01' },
  });
  expect(concurrent.status()).toBe(200);
  await page.getByRole('button', { name: 'Salvar cadastro' }).click();
  await expect(page.getByRole('alert')).toContainText('Outra pessoa');
  await expect(page.getByLabel('Nome', { exact: true })).toHaveValue(
    `${name} rascunho`,
  );
  await expect(
    page.getByRole('button', { name: 'Salvar cadastro' }),
  ).toBeDisabled();
  await visual(page, info, 'conflict');
  await page.getByRole('button', { name: 'Consultar versão atual' }).click();
  await expect(page.getByText(/Versão atual 2:/)).toBeVisible();
  await page
    .getByRole('button', { name: 'Revisar e usar esta versão' })
    .click();
  await page.getByRole('button', { name: 'Salvar cadastro' }).click();
  await expect(
    page.getByRole('heading', { level: 2, name: `${name} rascunho` }),
  ).toBeFocused();
  for (const filename of ['synthetic-one.png', 'synthetic-two.png']) {
    await page.getByLabel('Adicionar foto').setInputFiles({
      name: filename,
      mimeType: 'image/png',
      buffer: syntheticPng,
    });
    await page.getByRole('button', { name: 'Enviar foto' }).click();
    await expect(
      page.getByRole('button', { name: 'Enviar foto' }),
    ).toBeEnabled();
  }
  await expect(
    page.getByRole('img', { name: `Foto de ${name} rascunho` }),
  ).toHaveCount(2);
  await page.getByRole('button', { name: 'Usar como principal' }).click();
  await expect(page.locator('.catalog-photo-card').nth(1)).toContainText(
    'Foto principal',
  );
  await page.getByLabel('Ordem da foto 2').fill('0');
  await page.getByRole('button', { name: 'Salvar ordem' }).nth(1).click();
  await expect(
    page.getByRole('button', { name: 'Salvar ordem' }).first(),
  ).toBeEnabled();
  await page.getByRole('button', { name: 'Retirar da galeria' }).last().click();
  await page
    .getByLabel('Motivo', { exact: true })
    .fill('Substituição sintética');
  await page
    .getByRole('button', { name: 'Retirar foto da galeria', exact: true })
    .click();
  await expect(
    page.getByRole('img', { name: `Foto de ${name} rascunho` }),
  ).toHaveCount(1);
  await expect(page.getByText('Foto principal', { exact: true })).toBeVisible();
  await page
    .getByRole('button', { name: 'Ajustar estoque', exact: true })
    .click();
  await page.getByRole('button', { name: 'Cancelar operação' }).click();
  await expect(
    page.getByRole('heading', { name: `${name} rascunho`, level: 2 }),
  ).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(
    page.getByRole('button', { name: 'Voltar à lista' }),
  ).toBeFocused();
  expect(
    await page
      .getByRole('button', { name: 'Voltar à lista' })
      .evaluate((element) => getComputedStyle(element).outlineWidth),
  ).toBe('3px');
  await visual(page, info, 'keyboard-gallery');
});
