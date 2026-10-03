import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CatalogPage } from './CatalogPage';
import type { CatalogPage as Page, Product, ProductDetail } from './api';
import { RecordEditor } from './RecordEditor';
import { RecordDetail } from './RecordDetail';

const product: ProductDetail = {
  id: '11111111-1111-4111-8111-111111111111',
  name: 'Mesa branca',
  price: '100.01',
  is_active: true,
  version: 1,
  total_quantity: 5,
  maintenance_quantity: 1,
  apt_quantity: 4,
  created_by: '22222222-2222-4222-8222-222222222222',
  updated_by: '22222222-2222-4222-8222-222222222222',
  created_at: '2026-10-03T12:00:00Z',
  updated_at: '2026-10-03T12:00:00Z',
  description: null,
  category: null,
  color: null,
  dimensions: null,
  replacement_value: null,
  observation: 'Conferir tampo',
  history: [],
  movements: [],
  maintenance: [],
  photos: [],
};
const empty: Page<Product> = { items: [], total: 0, page: 1, page_size: 25 };
const response = (data: unknown, status = 200) => ({
  ok: status < 400,
  status,
  json: async () => data,
});
const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockResolvedValue(response(empty));
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => vi.unstubAllGlobals());
function view() {
  render(
    <MemoryRouter>
      <CatalogPage />
    </MemoryRouter>,
  );
}

describe('catalog interface', () => {
  it('shows loading, empty and retryable connection error', async () => {
    let finish: (value: unknown) => void = () => {};
    fetchMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    view();
    expect(
      screen.getByRole('heading', { name: 'Carregando catálogo…' }),
    ).toBeVisible();
    await act(async () =>
      finish(response({ detail: 'Serviço indisponível.' }, 503)),
    );
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Serviço indisponível',
    );
    await userEvent.click(
      screen.getByRole('button', { name: 'Tentar novamente' }),
    );
    expect(
      await screen.findByRole('heading', { name: 'Seu acervo começa aqui' }),
    ).toBeVisible();
    expect(
      screen.getAllByRole('link', { name: 'Voltar à visão geral' }),
    ).toHaveLength(1);
  });

  it('creates with only required fields and exact decimal string', async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation((_url: string, options?: RequestInit) =>
      Promise.resolve(
        response(
          options?.method === 'POST' ? product : empty,
          options?.method === 'POST' ? 201 : 200,
        ),
      ),
    );
    view();
    await user.click(screen.getByRole('button', { name: 'Novo produto' }));
    expect(screen.getByRole('heading', { name: 'Novo produto' })).toHaveFocus();
    await user.type(screen.getByLabelText('Nome'), 'Mesa branca');
    await user.type(screen.getByLabelText('Preço por locação (R$)'), '100,01');
    await user.click(screen.getByRole('button', { name: 'Salvar cadastro' }));
    expect(
      await screen.findByText('Alteração salva com histórico.'),
    ).toBeVisible();
    expect(
      screen.getByRole('heading', { name: 'Mesa branca', level: 2 }),
    ).toHaveFocus();
    const call = fetchMock.mock.calls.find(
      ([, options]) => options?.method === 'POST',
    );
    expect(JSON.parse(call?.[1].body as string)).toMatchObject({
      name: 'Mesa branca',
      price: '100.01',
      initial_quantity: 0,
      observation: null,
    });
    expect(screen.getByText(/antes dos compromissos do período/)).toBeVisible();
    expect(screen.getByText(/Sem foto/)).toBeVisible();
  });

  it('preserves edit draft on 409 and requires explicit version review', async () => {
    const user = userEvent.setup();
    const saved = vi.fn();
    fetchMock.mockImplementation((_url: string, options?: RequestInit) =>
      Promise.resolve(
        response(
          options?.method === 'PATCH'
            ? { detail: 'Outra pessoa alterou. Seu rascunho foi mantido.' }
            : { ...product, version: 2, name: 'Nome atual' },
          options?.method === 'PATCH' ? 409 : 200,
        ),
      ),
    );
    render(
      <RecordEditor
        kind="products"
        initial={product}
        onSaved={saved}
        onCancel={() => {}}
      />,
    );
    expect(screen.queryByLabelText('Quantidade inicial')).toBeNull();
    await user.clear(screen.getByLabelText('Nome'));
    await user.type(screen.getByLabelText('Nome'), 'Meu rascunho');
    await user.click(screen.getByRole('button', { name: 'Salvar cadastro' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('rascunho');
    expect(screen.getByLabelText('Nome')).toHaveValue('Meu rascunho');
    expect(
      screen.getByRole('button', { name: 'Salvar cadastro' }),
    ).toBeDisabled();
    await user.click(
      screen.getByRole('button', { name: 'Consultar versão atual' }),
    );
    expect(await screen.findByText(/Versão atual 2: Nome atual/)).toBeVisible();
    expect(screen.getByLabelText('Nome')).toHaveValue('Meu rascunho');
    await user.click(
      screen.getByRole('button', { name: 'Revisar e usar esta versão' }),
    );
    expect(
      screen.getByRole('button', { name: 'Salvar cadastro' }),
    ).toBeEnabled();
    expect(saved).not.toHaveBeenCalled();
  });

  it('keeps fields on network failure and prevents double submit while pending', async () => {
    const user = userEvent.setup();
    let reject: (reason: Error) => void = () => {};
    fetchMock.mockImplementationOnce(
      () =>
        new Promise((_, failure) => {
          reject = failure;
        }),
    );
    render(
      <RecordEditor
        kind="products"
        initial={product}
        onSaved={() => {}}
        onCancel={() => {}}
      />,
    );
    await user.click(screen.getByRole('button', { name: 'Salvar cadastro' }));
    expect(screen.getByRole('button', { name: 'Salvando…' })).toBeDisabled();
    expect(screen.getByLabelText('Nome')).toBeDisabled();
    await act(async () => reject(new Error('Synthetic network failure')));
    expect(await screen.findByRole('alert')).toHaveTextContent('rascunho');
    expect(screen.getByLabelText('Nome')).toHaveValue('Mesa branca');
  });

  it('composes kits from active products only with own price and aggregated rows', async () => {
    const user = userEvent.setup();
    const inactive = {
      ...product,
      id: 'inactive',
      name: 'Mesa inativa',
      is_active: false,
    };
    fetchMock.mockResolvedValue(
      response({ ...empty, items: [product, inactive], total: 2 }),
    );
    render(<RecordEditor kind="kits" onSaved={() => {}} onCancel={() => {}} />);
    expect(
      await screen.findByRole('button', { name: 'Adicionar Mesa branca' }),
    ).toBeVisible();
    expect(
      screen.queryByRole('button', { name: 'Adicionar Mesa inativa' }),
    ).toBeNull();
    expect(screen.getByText(/nunca outros kits/)).toBeVisible();
    expect(screen.queryByLabelText('Quantidade inicial')).toBeNull();
    await user.click(
      screen.getByRole('button', { name: 'Adicionar Mesa branca' }),
    );
    await user.click(
      screen.getByRole('button', { name: 'Adicionar Mesa branca' }),
    );
    expect(screen.getByLabelText('Quantidade de Mesa branca')).toHaveValue(2);
    await user.click(
      screen.getByRole('button', { name: 'Remover Mesa branca' }),
    );
    expect(screen.getByText(/Nenhum componente/)).toBeVisible();
    expect(
      fetchMock.mock.calls.every(([url]) =>
        String(url).startsWith('/api/products?'),
      ),
    ).toBe(true);
  });

  it('searches by encoded name and renders stock labels and pagination', async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValue(
      response({ ...empty, items: [product], total: 26 }),
    );
    view();
    expect(
      await screen.findByRole('heading', { name: 'Mesa branca', level: 2 }),
    ).toBeVisible();
    await user.type(screen.getByLabelText('Buscar por nome'), 'branca & azul');
    await user.click(screen.getByRole('button', { name: 'Buscar' }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenLastCalledWith(
        expect.stringContaining('search=branca%20%26%20azul&page=1'),
        expect.any(Object),
      ),
    );
    await user.click(screen.getByRole('button', { name: 'Próxima' }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenLastCalledWith(
        expect.stringContaining('page=2'),
        expect.any(Object),
      ),
    );
  });

  it('maintenance, release and inactivation use explicit reason and version', async () => {
    const user = userEvent.setup();
    const saved = vi.fn();
    fetchMock.mockResolvedValue(response({ ...product, version: 2 }));
    render(
      <RecordDetail
        kind="products"
        record={{
          ...product,
          maintenance: [
            {
              id: 'entry',
              quantity: 1,
              released_quantity: 0,
              reason: 'Reparo',
            },
          ],
        }}
        onChange={saved}
        onEdit={() => {}}
        onClose={() => {}}
      />,
    );
    await user.click(
      screen.getByRole('button', { name: 'Liberar manutenção: Reparo' }),
    );
    expect(
      screen.getByRole('heading', { name: 'Liberar unidades' }),
    ).toHaveFocus();
    await user.type(screen.getByLabelText('Motivo'), 'Conferido e apto');
    await user.click(screen.getByRole('button', { name: 'Liberar unidades' }));
    await waitFor(() => expect(saved).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body).toEqual({
      expected_version: 1,
      reason: 'Conferido e apto',
      quantity: 1,
    });
    expect(
      screen.getByRole('heading', { name: 'Mesa branca', level: 2 }),
    ).toHaveFocus();
    await user.click(screen.getByRole('button', { name: 'Inativar produto' }));
    expect(
      screen.getByRole('heading', { name: 'Confirmar inativação' }),
    ).toHaveFocus();
    await user.click(screen.getByRole('button', { name: 'Cancelar operação' }));
    expect(
      screen.getByRole('heading', { name: 'Mesa branca', level: 2 }),
    ).toHaveFocus();
  });

  it('photo missing, loading, read error and failed upload are actionable', async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValue(
      response({ detail: 'Armazenamento de fotos indisponível.' }, 503),
    );
    const photo = {
      id: 'photo',
      format: 'PNG',
      size: 40,
      sha256: 'hash',
      order: 0,
      is_principal: true,
    };
    render(
      <RecordDetail
        kind="products"
        record={{ ...product, photos: [photo] }}
        onChange={() => {}}
        onEdit={() => {}}
        onClose={() => {}}
      />,
    );
    expect(screen.getByText('Foto principal')).toBeVisible();
    expect(screen.getByText('Carregando foto…')).toBeVisible();
    const image = document.querySelector('img');
    if (!image) throw new Error('Missing photo preview');
    fireEvent.error(image);
    expect(screen.getByRole('alert')).toHaveTextContent('carregar');
    await user.click(
      screen.getByRole('button', { name: 'Tentar carregar foto' }),
    );
    expect(screen.getByText('Carregando foto…')).toBeVisible();
    const file = new File(['synthetic'], 'synthetic.png', {
      type: 'image/png',
    });
    await user.upload(screen.getByLabelText('Adicionar foto'), file);
    await user.click(screen.getByRole('button', { name: 'Enviar foto' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Armazenamento');
    expect(fetchMock.mock.calls[0][1].body).toBeInstanceOf(FormData);
  });
});
