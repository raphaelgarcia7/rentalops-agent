import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

test('catalog loading, error, empty, validation and keyboard remain usable', async ({
  page,
}, info) => {
  await page.route('**/api/auth/**', (route) =>
    route.fulfill({
      json: {
        user_id: 'synthetic',
        session_id: 'synthetic',
        expires_at: new Date(Date.now() + 12 * 3600_000).toISOString(),
        idle_expires_at: new Date(Date.now() + 3600_000).toISOString(),
      },
    }),
  );
  let state: 'loading' | 'error' | 'empty' = 'loading';
  let ready: () => void = () => {};
  const pending = new Promise<void>((resolve) => {
    ready = resolve;
  });
  await page.route('**/api/products?**', async (route) => {
    if (state === 'loading') await pending;
    await route.fulfill(
      state === 'error'
        ? { status: 503, json: { detail: 'Serviço indisponível.' } }
        : { json: { items: [], total: 0, page: 1, page_size: 25 } },
    );
  });
  await page.goto('/catalogo');
  await expect(
    page.getByRole('heading', { name: 'Carregando catálogo…' }),
  ).toBeVisible();
  await page.screenshot({
    path: `test-results/evidence/${info.project.name}-catalog-loading.png`,
    fullPage: true,
  });
  state = 'error';
  ready();
  await expect(page.getByRole('alert')).toContainText('Serviço indisponível');
  await page.screenshot({
    path: `test-results/evidence/${info.project.name}-catalog-error.png`,
    fullPage: true,
  });
  state = 'empty';
  await page.getByRole('button', { name: 'Tentar novamente' }).click();
  await expect(
    page.getByRole('heading', { name: 'Seu acervo começa aqui' }),
  ).toBeVisible();
  await expect(
    page.getByRole('link', { name: 'Voltar à visão geral' }),
  ).toHaveCount(1);
  await page.screenshot({
    path: `test-results/evidence/${info.project.name}-catalog-empty.png`,
    fullPage: true,
  });
  await page.getByRole('button', { name: 'Novo produto' }).focus();
  await page.keyboard.press('Enter');
  await expect(
    page.getByRole('heading', { name: 'Novo produto' }),
  ).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(
    page.getByRole('button', { name: 'Cancelar', exact: true }),
  ).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByLabel('Nome', { exact: true })).toBeFocused();
  await page.keyboard.type('Produto sintético');
  await page.keyboard.press('Tab');
  await expect(
    page.getByLabel('Preço por locação (R$)', { exact: true }),
  ).toBeFocused();
  await page.keyboard.type('10,01');
  await page.keyboard.press('Tab');
  await expect(page.getByLabel('Quantidade inicial')).toBeFocused();
  await page.getByLabel('Quantidade inicial').fill('-1');
  expect(
    await page
      .getByLabel('Quantidade inicial')
      .evaluate((element) => (element as HTMLInputElement).validity.valid),
  ).toBe(false);
  await page.getByLabel('Quantidade inicial').fill('0');
  await page.keyboard.press('Tab');
  await expect(
    page.getByText('Mais detalhes (opcionais)', { exact: true }),
  ).toBeFocused();
  await page.keyboard.press('Enter');
  await page.keyboard.press('Tab');
  await expect(page.getByLabel('Descrição', { exact: true })).toBeFocused();
  expect(
    await page
      .getByLabel('Descrição', { exact: true })
      .evaluate((element) => getComputedStyle(element).outlineWidth),
  ).toBe('3px');
  await page.emulateMedia({ reducedMotion: 'reduce' });
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
    path: `test-results/evidence/${info.project.name}-catalog-keyboard-form.png`,
    fullPage: true,
  });
});
