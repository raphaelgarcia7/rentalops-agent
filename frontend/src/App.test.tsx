import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Workspace } from './App';

function renderRoute(path = '/') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Workspace logout={() => {}} busy={false} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ items: [], total: 0, page: 1, page_size: 25 }),
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe('workspace routing', () => {
  it('offers functional home links and explicitly planned features', () => {
    renderRoute();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Organização que',
    );
    expect(
      screen.getByRole('link', { name: 'Abrir Catálogo' }),
    ).toHaveAttribute('href', '/catalogo');
    expect(
      screen.getByRole('link', { name: 'Abrir Clientes' }),
    ).toHaveAttribute('href', '/clientes');
    expect(
      screen.getByRole('link', { name: 'Abrir Locações' }),
    ).toHaveAttribute('href', '/locacoes');
    expect(screen.getAllByText('Em construção')).toHaveLength(2);
    expect(screen.getByText('Abrir acervo')).toBeVisible();
    expect(
      screen.getByText(/O assistente conversacional está planejado/),
    ).toBeVisible();
  });

  it.each([
    ['/clientes', 'Clientes', /Essas funções ainda serão implementadas/],
    ['/locacoes', 'Locações', /registro de reservas ainda serão implementados/],
  ])(
    'opens %s directly with active navigation and honest scope',
    (path, title, description) => {
      renderRoute(path);
      expect(
        screen.getByRole('heading', { level: 1, name: title }),
      ).toBeVisible();
      expect(
        screen.getByRole('heading', { name: 'Em construção' }),
      ).toBeVisible();
      expect(screen.getByText(description)).toBeVisible();
      const nav = within(
        screen.getByRole('navigation', { name: 'Navegação principal' }),
      );
      expect(nav.getByRole('link', { name: title })).toHaveAttribute(
        'aria-current',
        'page',
      );
      expect(
        nav.getByRole('link', { name: 'Visão geral' }),
      ).not.toHaveAttribute('aria-current');
      expect(screen.getByRole('button', { name: 'Sair' })).toBeVisible();
    },
  );

  it('updates page title and moves focus to content after card navigation', async () => {
    const user = userEvent.setup();
    renderRoute();
    await user.click(screen.getByRole('link', { name: 'Abrir Clientes' }));
    expect(screen.getByRole('main', { name: 'Clientes' })).toHaveFocus();
    expect(document.title).toBe('Clientes · RentalOps');
    await user.click(
      screen.getByRole('link', { name: 'Voltar à visão geral' }),
    );
    expect(screen.getByRole('main', { name: 'Visão geral' })).toHaveFocus();
    expect(document.title).toBe('Visão geral · RentalOps');
  });

  it.each(['/catalogo/', '/CATALOGO'])(
    'keeps the page title aligned with router matching for %s',
    (path) => {
      renderRoute(path);
      expect(
        screen.getByRole('heading', { level: 1, name: 'Catálogo' }),
      ).toBeVisible();
      expect(document.title).toBe('Catálogo · RentalOps');
    },
  );

  it.each(['/nao-existe', '/catalogo/nao-existe'])(
    'provides a recovery path for %s',
    async (path) => {
      const user = userEvent.setup();
      renderRoute(path);
      expect(
        screen.getByRole('heading', {
          level: 1,
          name: 'Esse caminho não existe.',
        }),
      ).toBeVisible();
      expect(
        screen.getByRole('navigation').querySelector('[aria-current="page"]'),
      ).toBeNull();
      await user.click(
        screen.getByRole('link', { name: 'Voltar à visão geral' }),
      );
      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
        'Organização que',
      );
    },
  );
});
