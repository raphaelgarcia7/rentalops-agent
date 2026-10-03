import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

test('real PostgreSQL: private first access, login, logout, recovery and deactivation', async ({
  page,
  request,
}, info) => {
  const setup = await request.post('http://127.0.0.1:8000/__test/setup');
  expect(setup.status()).toBe(200);
  const account = (await setup.json()) as { email: string; token: string };
  // No token/password goes to console, journal, source snapshot or evidence caption.
  await page.goto(`/definir-senha#token=${account.token}`);
  await expect(page).toHaveURL('/definir-senha');
  await page
    .getByLabel('Nova senha', { exact: true })
    .fill('synthetic browser pass phrase');
  await page
    .getByLabel('Confirmar senha', { exact: true })
    .fill('synthetic browser pass phrase');
  await page.getByRole('button', { name: 'Salvar senha' }).click();
  await expect(page.getByRole('status')).toContainText('Senha definida');
  await page.getByLabel('E-mail', { exact: true }).fill(account.email);
  await page
    .getByLabel('Senha', { exact: true })
    .fill('synthetic browser pass phrase');
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1 })).toContainText(
    'Organização',
  );
  const cookies = await page.context().cookies();
  const cookie = cookies.find((item) => item.name === 'rentalops_session');
  expect(cookie?.httpOnly).toBe(true);
  expect(cookie?.sameSite).toBe('Lax');
  expect(await page.evaluate(() => Object.keys(localStorage))).toEqual([]);
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.getByRole('button', { name: 'Sair' }).click();
  await expect(page.getByRole('status')).toContainText('Você saiu');
  await page
    .getByLabel('Senha', { exact: true })
    .fill('synthetic browser pass phrase');
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Sair' })).toBeVisible();
  const reset = await request.post('http://127.0.0.1:8000/__test/control', {
    data: { email: account.email, operation: 'reset' },
  });
  expect(reset.status()).toBe(200);
  const recovery = (await reset.json()) as { token: string };
  // Fresh page load revalidates server-side revocation without mocked API.
  await page.reload();
  await expect(
    page.getByRole('heading', { name: 'Entrar no RentalOps' }),
  ).toBeVisible();
  await page.goto(`/definir-senha#token=${recovery.token}`);
  await page
    .getByLabel('Nova senha', { exact: true })
    .fill('new synthetic browser phrase');
  await page
    .getByLabel('Confirmar senha', { exact: true })
    .fill('new synthetic browser phrase');
  await page.getByRole('button', { name: 'Salvar senha' }).click();
  await expect(page.getByRole('status')).toContainText('Senha definida');
  await page.getByLabel('E-mail', { exact: true }).fill(account.email);
  await page
    .getByLabel('Senha', { exact: true })
    .fill('new synthetic browser phrase');
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Sair' })).toBeVisible();
  expect(
    (
      await request.post('http://127.0.0.1:8000/__test/control', {
        data: { email: account.email, operation: 'deactivate' },
      })
    ).status(),
  ).toBe(200);
  await page.reload();
  await expect(
    page.getByRole('heading', { name: 'Entrar no RentalOps' }),
  ).toBeVisible();
  await page.getByLabel('E-mail', { exact: true }).fill(account.email);
  await page
    .getByLabel('Senha', { exact: true })
    .fill('new synthetic browser phrase');
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText(
    'E-mail ou senha inválidos',
  );
  await page.getByLabel('E-mail', { exact: true }).fill('');
  await page.getByLabel('Senha', { exact: true }).fill('');
  await page.screenshot({
    path: `test-results/evidence/${info.project.name}-auth-live-deactivated.png`,
    fullPage: true,
  });
});
