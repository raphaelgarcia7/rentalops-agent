import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthContext } from '../authContext';
import { CustomerEditor } from './CustomerEditor';
import { CustomersPage } from './CustomersPage';
import type { CustomerDetail } from './api';

const record: CustomerDetail = {
  id: '11111111-1111-4111-8111-111111111111',
  name: 'Pessoa sintética',
  phone: '+5511912345678',
  cpf: null,
  rg: null,
  notes: null,
  email: null,
  address: null,
  version: 1,
  created_by: '22222222-2222-4222-8222-222222222222',
  updated_by: '22222222-2222-4222-8222-222222222222',
  created_at: '2026-10-03T12:00:00Z',
  updated_at: '2026-10-03T12:00:00Z',
  history: [],
};
const empty = { items: [], total: 0, page: 1, page_size: 25 };
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
function view(path = '/clientes') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <CustomersPage />
    </MemoryRouter>,
  );
}
async function fillMinimum() {
  await userEvent.type(screen.getByLabelText('Nome *'), 'Pessoa sintética');
  await userEvent.type(
    screen.getByLabelText('Telefone / WhatsApp *'),
    '(11) 91234-5678',
  );
}

describe('customers interface', () => {
  it('shows loading, error, retry and a true empty list', async () => {
    let finish: (value: unknown) => void = () => {};
    fetchMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    view();
    expect(
      screen.getByRole('heading', { name: 'Carregando clientes…' }),
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
      await screen.findByRole('heading', {
        name: 'Seu primeiro contato começa aqui',
      }),
    ).toBeVisible();
  });
  it('sends exact document or contact searches in body, never URL; paginates', async () => {
    fetchMock.mockResolvedValue(
      response({ ...empty, total: 26, items: [record] }),
    );
    view();
    await screen.findByRole('button', { name: `Abrir ${record.name}` });
    await userEvent.click(screen.getByRole('button', { name: 'Próxima' }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenLastCalledWith(
        '/api/customers/search',
        expect.objectContaining({
          body: JSON.stringify({ name: '', page: 2 }),
        }),
      ),
    );
    await userEvent.selectOptions(screen.getByLabelText('Buscar por'), 'phone');
    await userEvent.type(screen.getByLabelText('Busca'), record.phone);
    await userEvent.click(screen.getByRole('button', { name: /^Buscar$/ }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenLastCalledWith(
        '/api/customers/search',
        expect.objectContaining({
          body: JSON.stringify({ name: '', phone: record.phone, page: 1 }),
        }),
      ),
    );
    expect(
      fetchMock.mock.calls.every(
        ([url]) => !String(url).includes(record.phone),
      ),
    ).toBe(true);
  });
  it('creates minimum fields and shows the true empty rental history', async () => {
    fetchMock.mockImplementation((url: string) =>
      Promise.resolve(
        response(
          url.endsWith('/search') ? empty : record,
          url.endsWith('/search') ? 200 : 201,
        ),
      ),
    );
    view();
    await userEvent.click(screen.getByRole('button', { name: 'Novo cliente' }));
    expect(screen.getByRole('heading', { name: 'Novo cliente' })).toHaveFocus();
    await fillMinimum();
    await userEvent.click(
      screen.getByRole('button', { name: 'Salvar cliente' }),
    );
    expect(
      await screen.findByText(/Nenhuma locação confirmada registrada/),
    ).toBeVisible();
    const write = fetchMock.mock.calls.find(
      ([url]) => url === '/api/customers',
    );
    const payload = JSON.parse(write?.[1].body as string) as {
      cpf: null;
      acknowledged_shared_contact: string[];
    };
    expect(payload.cpf).toBeNull();
    expect(payload.acknowledged_shared_contact).toEqual([]);
    expect(screen.getByRole('status')).toHaveTextContent(
      'Cliente salvo com sucesso',
    );
  });
  it('requires explicit shared-contact confirmation and preserves the form/link', async () => {
    const onSaved = vi.fn();
    fetchMock
      .mockResolvedValueOnce(
        response(
          {
            detail: 'Contato compartilhado.',
            code: 'shared_contact',
            existing_ids: [record.id],
          },
          409,
        ),
      )
      .mockResolvedValueOnce(response(record, 201));
    render(<CustomerEditor onSaved={onSaved} onCancel={() => {}} />);
    await fillMinimum();
    await userEvent.click(
      screen.getByRole('button', { name: 'Salvar cliente' }),
    );
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Contato compartilhado',
    );
    await waitFor(() => expect(screen.getByRole('alert')).toHaveFocus());
    expect(screen.getByLabelText('Nome *')).toHaveValue(record.name);
    expect(
      screen.getByRole('link', { name: /Consultar cadastro/ }),
    ).toHaveAttribute('target', '_blank');
    expect(onSaved).not.toHaveBeenCalled();
    await userEvent.click(
      screen.getByRole('button', {
        name: 'Confirmar pessoa distinta e salvar',
      }),
    );
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(record));
    expect(
      JSON.parse(fetchMock.mock.calls[1][1].body as string)
        .acknowledged_shared_contact,
    ).toEqual([record.id]);
  });
  it('duplicate CPF preserves draft and existing-record link without automatic merge', async () => {
    fetchMock.mockResolvedValue(
      response(
        {
          detail: 'CPF já cadastrado.',
          code: 'duplicate_cpf',
          existing_ids: [record.id],
        },
        409,
      ),
    );
    render(<CustomerEditor onSaved={() => {}} onCancel={() => {}} />);
    await fillMinimum();
    await userEvent.click(
      screen.getByRole('button', { name: 'Salvar cliente' }),
    );
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'CPF já cadastrado',
    );
    expect(screen.getByLabelText('Telefone / WhatsApp *')).toHaveValue(
      '(11) 91234-5678',
    );
    expect(
      screen.getByRole('link', { name: /Consultar cadastro/ }),
    ).toHaveAttribute('href', `/clientes?cliente=${record.id}`);
    expect(
      screen.queryByRole('button', {
        name: 'Confirmar pessoa distinta e salvar',
      }),
    ).not.toBeInTheDocument();
  });
  it('compares a stale version, keeps draft, and retries only after explicit version choice', async () => {
    const current = { ...record, version: 2, name: 'Outra edição' };
    fetchMock
      .mockResolvedValueOnce(
        response(
          { detail: 'Versão desatualizada.', code: 'stale_version' },
          409,
        ),
      )
      .mockResolvedValueOnce(response(current))
      .mockResolvedValueOnce(response({ ...record, version: 3 }));
    const onSaved = vi.fn();
    render(
      <CustomerEditor initial={record} onSaved={onSaved} onCancel={() => {}} />,
    );
    await userEvent.clear(screen.getByLabelText('Nome *'));
    await userEvent.type(screen.getByLabelText('Nome *'), 'Meu rascunho');
    await userEvent.click(
      screen.getByRole('button', { name: 'Salvar cliente' }),
    );
    await screen.findByRole('alert');
    await userEvent.click(
      screen.getByRole('button', { name: 'Consultar versão atual' }),
    );
    expect(
      await screen.findByRole('heading', { name: 'Versão atual 2' }),
    ).toBeVisible();
    expect(screen.getByLabelText('Nome *')).toHaveValue('Meu rascunho');
    await userEvent.click(
      screen.getByRole('button', {
        name: 'Manter meu rascunho e usar versão atual',
      }),
    );
    expect(onSaved).not.toHaveBeenCalled();
    await userEvent.click(
      screen.getByRole('button', { name: 'Salvar cliente' }),
    );
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(JSON.parse(fetchMock.mock.calls[2][1].body as string)).toMatchObject(
      { name: 'Meu rascunho', expected_version: 2 },
    );
  });
  it('allows explicit reload after comparing and maps safe validation fields', async () => {
    fetchMock
      .mockResolvedValueOnce(
        response({ detail: 'Conflito.', code: 'stale_version' }, 409),
      )
      .mockResolvedValueOnce(
        response({ ...record, version: 2, notes: 'Atual' }),
      )
      .mockResolvedValueOnce(
        response({ detail: 'Entrada inválida.', fields: ['phone'] }, 422),
      );
    render(
      <CustomerEditor
        initial={record}
        onSaved={() => {}}
        onCancel={() => {}}
      />,
    );
    await userEvent.click(
      screen.getByRole('button', { name: 'Salvar cliente' }),
    );
    await screen.findByRole('alert');
    await userEvent.click(
      screen.getByRole('button', { name: 'Consultar versão atual' }),
    );
    await screen.findByRole('heading', { name: 'Versão atual 2' });
    await userEvent.click(
      screen.getByRole('button', { name: 'Recarregar dados atuais' }),
    );
    expect(screen.getByLabelText('Observações')).toHaveValue('Atual');
    expect(screen.getByRole('textbox', { name: 'Observações' })).toHaveValue(
      'Atual',
    );
    await userEvent.click(
      screen.getByRole('button', { name: 'Salvar cliente' }),
    );
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Confira: Telefone / WhatsApp',
    );
  });
  it('re-authentication refresh does not discard an editing draft from a stable customer link', async () => {
    fetchMock.mockImplementation((url: string) =>
      Promise.resolve(response(url.endsWith('/search') ? empty : record)),
    );
    const provider = (authenticated: boolean) => (
      <MemoryRouter initialEntries={[`/clientes?cliente=${record.id}`]}>
        <AuthContext.Provider
          value={{ authenticated, logout: () => {}, busy: false }}
        >
          <CustomersPage />
        </AuthContext.Provider>
      </MemoryRouter>
    );
    const rendered = render(provider(true));
    await userEvent.click(
      await screen.findByRole('button', { name: 'Editar cliente' }),
    );
    await userEvent.type(
      screen.getByLabelText('Observações'),
      'Rascunho em memória',
    );
    rendered.rerender(provider(false));
    rendered.rerender(provider(true));
    await waitFor(() =>
      expect(screen.getByLabelText('Observações')).toHaveValue(
        'Rascunho em memória',
      ),
    );
  });
});
