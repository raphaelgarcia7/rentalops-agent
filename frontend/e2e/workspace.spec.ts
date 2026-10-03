import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  const identity = {
    user_id: 'synthetic',
    session_id: 'synthetic',
    expires_at: new Date(Date.now() + 12 * 60 * 60 * 1000).toISOString(),
    idle_expires_at: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
  };
  await page.route('**/api/auth/**', async (route) => {
    await route.fulfill({ json: identity });
  });
});

const pages = [
  {
    path: '/',
    title: 'Organização que abre espaço para criar.',
    label: 'home',
  },
  { path: '/catalogo', title: 'Catálogo', label: 'catalogo' },
  { path: '/clientes', title: 'Clientes', label: 'clientes' },
  { path: '/locacoes', title: 'Locações', label: 'locacoes' },
  { path: '/nao-existe', title: 'Esse caminho não existe.', label: '404' },
];

for (const route of pages) {
  test(`${route.label}: direct route, readable layout and accessibility`, async ({
    page,
  }, testInfo) => {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(route.path);
    await expect(
      page.getByRole('heading', { level: 1, name: route.title }),
    ).toBeVisible();
    const nav = page.getByRole('navigation', { name: 'Navegação principal' });
    for (const name of ['Visão geral', 'Catálogo', 'Clientes', 'Locações']) {
      const link = nav.getByRole('link', { name, exact: true });
      await expect(link).toBeVisible();
      const box = await link.boundingBox();
      expect(box?.height).toBeGreaterThanOrEqual(44);
      expect(box?.width).toBeGreaterThanOrEqual(44);
    }
    expect(
      await page.evaluate(
        () =>
          document.documentElement.scrollWidth <=
          document.documentElement.clientWidth,
      ),
    ).toBe(true);
    if (route.path !== '/' && route.label !== '404') {
      await expect(
        page.getByRole('heading', { name: 'Em construção' }),
      ).toBeVisible();
      await expect(
        nav.getByRole('link', { name: route.title, exact: true }),
      ).toHaveAttribute('aria-current', 'page');
      await expect(page.getByRole('button', { name: 'Sair' })).toBeVisible();
    }
    const result = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
      .analyze();
    expect(result.violations).toEqual([]);
    expect(errors).toEqual([]);
    await page.screenshot({
      path: `test-results/evidence/${testInfo.project.name}-${route.label}.png`,
      fullPage: true,
    });
  });
}

test('navigation works with history, refresh and return links', async ({
  page,
}) => {
  await page.goto('/');
  await page.getByRole('link', { name: 'Abrir Catálogo' }).click();
  await expect(page).toHaveURL('/catalogo');
  await expect(page.getByRole('main')).toBeFocused();
  await page
    .getByRole('navigation')
    .getByRole('link', { name: 'Clientes', exact: true })
    .click();
  await expect(page).toHaveURL('/clientes');
  await page.goBack();
  await expect(
    page.getByRole('heading', { level: 1, name: 'Catálogo' }),
  ).toBeVisible();
  await page.goForward();
  await expect(
    page.getByRole('heading', { level: 1, name: 'Clientes' }),
  ).toBeVisible();
  await page.reload();
  await expect(page).toHaveTitle('Clientes · RentalOps');
  await page
    .getByRole('navigation')
    .getByRole('link', { name: 'Locações', exact: true })
    .click();
  await expect(page).toHaveURL('/locacoes');
  await page.getByRole('link', { name: 'Voltar à visão geral' }).click();
  await expect(page).toHaveURL('/');
});

test('keyboard skip link, navigation and route focus remain usable', async ({
  page,
}, testInfo) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toContainText(
    'Organização',
  );
  await page.keyboard.press('Tab');
  const skip = page.getByRole('link', { name: 'Pular para o conteúdo' });
  await expect(skip).toBeFocused();
  await expect(skip).toBeInViewport();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('main')).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(
    page.getByRole('link', { name: 'Abrir Catálogo' }),
  ).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(
    page.getByRole('heading', { level: 1, name: 'Catálogo' }),
  ).toBeVisible();
  await expect(page.getByRole('main')).toBeFocused();
  await page.keyboard.press('Tab');
  const back = page.getByRole('link', { name: 'Voltar à visão geral' });
  await expect(back).toBeFocused();
  await expect(back).toBeInViewport();
  expect(
    await back.evaluate((element) => getComputedStyle(element).outlineWidth),
  ).toBe('3px');
  await page.screenshot({
    path: `test-results/evidence/${testInfo.project.name}-keyboard-focus.png`,
    fullPage: true,
  });
  await page.keyboard.press('Enter');
  await expect(page.getByRole('main')).toBeFocused();
  await page.getByRole('link', { name: 'RentalOps, início' }).focus();
  await page.keyboard.press('Tab');
  await expect(
    page
      .getByRole('navigation')
      .getByRole('link', { name: 'Visão geral', exact: true }),
  ).toBeFocused();
  await page.keyboard.press('Tab');
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL('/catalogo');
});

test('reduced motion disables decorative animation and transitions', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.goto('/');
  await expect(page.locator('.art-object--one')).toHaveCSS(
    'animation-name',
    'object-float',
  );
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await expect(page.locator('.art-object--one')).toHaveCSS(
    'animation-name',
    'none',
  );
  await expect(page.locator('.module-card').first()).toHaveCSS(
    'transition-duration',
    '0s',
  );
  await expect(
    page.getByRole('link', { name: 'Abrir Locações' }),
  ).toBeVisible();
});

test('short landscape viewport keeps navigation and recovery available', async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 844, height: 390 });
  await page.goto('/nao-existe');
  await page
    .getByRole('navigation')
    .getByRole('link', { name: 'Clientes', exact: true })
    .click();
  await expect(
    page.getByRole('heading', { level: 1, name: 'Clientes' }),
  ).toBeVisible();
  await page.getByRole('link', { name: 'Voltar à visão geral' }).click();
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth <=
        document.documentElement.clientWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: `test-results/evidence/${testInfo.project.name}-landscape.png`,
    fullPage: true,
  });
});

test('305px content width accommodates a native scrollbar in a 320px window', async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 305, height: 740 });
  for (const path of [
    '/',
    '/catalogo',
    '/clientes',
    '/locacoes',
    '/nao-existe',
  ]) {
    await page.goto(path);
    expect(
      await page.evaluate(
        () =>
          document.documentElement.scrollWidth <=
          document.documentElement.clientWidth,
      ),
    ).toBe(true);
    const links = page.getByRole('navigation').getByRole('link');
    for (const link of await links.all()) {
      await expect(link).toBeInViewport();
    }
  }
  await page.screenshot({
    path: `test-results/evidence/${testInfo.project.name}-scrollbar-budget-305.png`,
    fullPage: true,
  });
});
