import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';

function identity() {
  return {
    user_id: 'synthetic-user',
    session_id: 'synthetic-session',
    expires_at: new Date(Date.now() + 12 * 60 * 60 * 1000).toISOString(),
    idle_expires_at: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
  };
}

async function login(page: Page) {
  await page
    .getByLabel('E-mail', { exact: true })
    .fill('person@example.invalid');
  await page.getByLabel('Senha', { exact: true }).fill('synthetic pass phrase');
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
}

test('closed login is responsive, readable, keyboard accessible and has clear errors', async ({
  page,
}, info) => {
  await page.route('**/api/auth/**', (route) =>
    route.fulfill({ status: 401, json: { detail: 'generic' } }),
  );
  await page.goto('/clientes');
  const heading = page.getByRole('heading', { name: 'Entrar no RentalOps' });
  await expect(heading).toBeFocused();
  await expect(page.getByRole('navigation')).toHaveCount(0);
  await expect(page.getByText('Google')).toHaveCount(0);
  await page.keyboard.press('Tab');
  await expect(page.getByLabel('E-mail', { exact: true })).toBeFocused();
  await page.keyboard.type('person@example.invalid');
  await page.keyboard.press('Tab');
  await page.keyboard.type('synthetic pass phrase');
  await page.keyboard.press('Tab');
  const button = page.getByRole('button', { name: 'Entrar', exact: true });
  await expect(button).toBeFocused();
  expect(
    await button.evaluate((element) => getComputedStyle(element).outlineWidth),
  ).toBe('3px');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('alert')).toContainText('Confira os dados');
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth <=
        document.documentElement.clientWidth,
    ),
  ).toBe(true);
  for (const control of await page
    .locator('.auth-card input, .auth-card button')
    .all()) {
    expect((await control.boundingBox())?.height).toBeGreaterThanOrEqual(44);
  }
  const result = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
    .analyze();
  expect(result.violations).toEqual([]);
  await page.getByLabel('Senha', { exact: true }).fill('');
  await page.screenshot({
    path: `test-results/evidence/${info.project.name}-auth-login-error.png`,
    fullPage: true,
  });
});

test('private fragment is removed and first password succeeds through body-only submission', async ({
  page,
}, info) => {
  const received: { url: string; body: Record<string, string> }[] = [];
  await page.route('**/api/auth/**', async (route) => {
    if (route.request().url().endsWith('/password/set')) {
      received.push({
        url: route.request().url(),
        body: route.request().postDataJSON() as Record<string, string>,
      });
      await route.fulfill({ status: 204 });
    } else await route.fulfill({ status: 401, json: {} });
  });
  await page.goto('/definir-senha#token=synthetic-private-token');
  await expect(
    page.getByRole('heading', { name: 'Definir sua senha' }),
  ).toBeFocused();
  await expect(page).toHaveURL('/definir-senha');
  const result = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
    .analyze();
  expect(result.violations).toEqual([]);
  await page.screenshot({
    path: `test-results/evidence/${info.project.name}-auth-set-empty.png`,
    fullPage: true,
  });
  await page
    .getByLabel('Nova senha', { exact: true })
    .fill('synthetic pass phrase');
  await page
    .getByLabel('Confirmar senha', { exact: true })
    .fill('different pass phrase');
  await page.getByRole('button', { name: 'Salvar senha' }).click();
  await expect(page.getByRole('alert')).toContainText('não coincidem');
  expect(received).toEqual([]);
  await page
    .getByLabel('Confirmar senha', { exact: true })
    .fill('synthetic pass phrase');
  await page.getByRole('button', { name: 'Salvar senha' }).click();
  await expect(page.getByRole('status')).toContainText('Senha definida');
  await expect(
    page.getByRole('heading', { name: 'Entrar no RentalOps' }),
  ).toBeFocused();
  expect(received).toHaveLength(1);
  expect(received[0].url).not.toContain('synthetic-private-token');
  expect(received[0].body.token).toBe('synthetic-private-token');
  await expect(page.getByLabel('Senha', { exact: true })).toHaveValue('');
});

test('expired/reused links explain the next step without claiming success', async ({
  page,
}, info) => {
  await page.route('**/api/auth/**', (route) =>
    route.fulfill({
      status: route.request().url().endsWith('/password/set') ? 400 : 401,
      json: {},
    }),
  );
  await page.goto('/definir-senha#token=synthetic-expired-token');
  await page
    .getByLabel('Nova senha', { exact: true })
    .fill('synthetic pass phrase');
  await page
    .getByLabel('Confirmar senha', { exact: true })
    .fill('synthetic pass phrase');
  await page.getByRole('button', { name: 'Salvar senha' }).click();
  await expect(page.getByRole('alert')).toContainText(
    'Procure o administrador',
  );
  await expect(page).toHaveURL('/definir-senha');
  await page.getByLabel('Nova senha', { exact: true }).fill('');
  await page.getByLabel('Confirmar senha', { exact: true }).fill('');
  await page.screenshot({
    path: `test-results/evidence/${info.project.name}-auth-link-error.png`,
    fullPage: true,
  });
});

test('login pending, logout, identity revocation and deliberate activity use distinct requests', async ({
  page,
}) => {
  await page.clock.install();
  let active = false;
  let revoked = false;
  let activityCount = 0;
  let release: () => void = () => {};
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/auth/**', async (route) => {
    const path = route.request().url();
    if (path.endsWith('/password/login')) {
      await pending;
      active = true;
      await route.fulfill({ json: identity() });
    } else if (path.endsWith('/logout')) {
      active = false;
      await route.fulfill({ status: 204 });
    } else if (path.endsWith('/activity')) {
      activityCount += 1;
      await route.fulfill({ status: revoked ? 401 : 200, json: identity() });
    } else
      await route.fulfill({
        status: active && !revoked ? 200 : 401,
        json: identity(),
      });
  });
  await page.goto('/clientes');
  await login(page);
  await expect(page.getByRole('button', { name: 'Aguarde…' })).toBeDisabled();
  release();
  await expect(
    page.getByRole('heading', { name: 'Clientes', exact: true }),
  ).toBeVisible();
  expect(activityCount).toBe(0);
  await page.getByRole('button', { name: 'Sair' }).click();
  await expect(page.getByRole('status')).toContainText('Você saiu');
  await login(page);
  await expect(
    page.getByRole('heading', { name: 'Clientes', exact: true }),
  ).toBeVisible();
  revoked = true;
  await page.clock.fastForward(30_001);
  await expect(page.getByRole('status')).toContainText('sessão terminou');
  await expect(
    page.getByRole('heading', { name: 'Entrar no RentalOps' }),
  ).toBeFocused();
});

test('polling is read-only and cannot keep an idle session alive', async ({
  page,
}) => {
  await page.clock.install();
  const snapshot = identity();
  let count = 0;
  await page.route('**/api/auth/**', async (route) => {
    if (route.request().url().endsWith('/activity')) count += 1;
    await route.fulfill({ json: snapshot });
  });
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Sair' })).toBeVisible();
  await page.clock.fastForward(60 * 60 * 1000 + 1);
  await expect(
    page.getByRole('heading', { name: 'Entrar no RentalOps' }),
  ).toBeVisible();
  expect(count).toBe(0);
});

test('unavailable backend gives retry feedback and honors reduced motion', async ({
  page,
}, info) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.route('**/api/auth/**', (route) =>
    route.fulfill({ status: 503, json: {} }),
  );
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('Tente novamente');
  await expect(
    page.getByRole('button', { name: 'Verificar conexão novamente' }),
  ).toBeVisible();
  expect(
    await page
      .getByRole('button', { name: 'Entrar', exact: true })
      .evaluate((element) => getComputedStyle(element).transitionDuration),
  ).toBe('0s');
  await page.screenshot({
    path: `test-results/evidence/${info.project.name}-auth-unavailable.png`,
    fullPage: true,
  });
});
