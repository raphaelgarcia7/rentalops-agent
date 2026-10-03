import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

test('customers loading, empty, errors, keyboard, validation and reduced motion', async ({
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
  await page.route('**/api/customers/search', async (route) => {
    if (state === 'loading') await pending;
    await route.fulfill(
      state === 'error'
        ? { status: 503, json: { detail: 'Serviço indisponível.' } }
        : { json: { items: [], total: 0, page: 1, page_size: 25 } },
    );
  });
  await page.route('**/api/customers', (route) =>
    route.fulfill({
      status: 422,
      json: { detail: 'Entrada inválida.', fields: ['phone'] },
    }),
  );
  async function visual(phase: string) {
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
    });
  }
  await page.goto('/clientes');
  await expect(
    page.getByRole('heading', { name: 'Carregando clientes…' }),
  ).toBeVisible();
  await visual('loading');
  state = 'error';
  ready();
  await expect(page.getByRole('alert')).toContainText('Serviço indisponível');
  await visual('error');
  state = 'empty';
  await page.getByRole('button', { name: 'Tentar novamente' }).click();
  await expect(
    page.getByRole('heading', { name: 'Seu primeiro contato começa aqui' }),
  ).toBeVisible();
  await visual('empty');
  await page.getByRole('button', { name: 'Novo cliente' }).focus();
  await page.keyboard.press('Enter');
  await expect(
    page.getByRole('heading', { name: 'Novo cliente' }),
  ).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(
    page.getByRole('button', { name: 'Cancelar', exact: true }),
  ).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByLabel('Nome *')).toBeFocused();
  await page.keyboard.type('Pessoa sintética');
  await page.keyboard.press('Tab');
  await expect(page.getByLabel('Telefone / WhatsApp *')).toBeFocused();
  await page.keyboard.type('123');
  await page.getByRole('button', { name: 'Salvar cliente' }).click();
  await expect(page.getByRole('alert')).toContainText(
    'Confira: Telefone / WhatsApp',
  );
  await expect(page.getByRole('alert')).toBeFocused();
  await page.getByLabel('Telefone / WhatsApp *').clear();
  await page
    .getByText('Documentos e endereço (opcionais)', { exact: true })
    .focus();
  await page.keyboard.press('Enter');
  await page.keyboard.press('Tab');
  await expect(page.getByLabel('CPF', { exact: true })).toBeFocused();
  expect(
    await page
      .getByLabel('CPF', { exact: true })
      .evaluate((element) => getComputedStyle(element).outlineWidth),
  ).toBe('3px');
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await visual('keyboard-validation');
  await page.getByRole('button', { name: 'Cancelar', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Novo cliente' }),
  ).toBeFocused();
});
