import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { FinancialSection } from './FinancialSection';
import type { Payments } from './api';

export const state: Payments = {
  quotation_id: '11111111-1111-4111-8111-111111111111',
  quotation_version: 1,
  financial_version: 0,
  reconciled_quotation_version: null,
  total: '400.00',
  estimated_deposit: '200.00',
  estimated_balance: '200.00',
  received: '0.00',
  refunded: '0.00',
  net_received: '0.00',
  applied_deposit: '0.00',
  applied_balance: '0.00',
  deposit_remaining: '200.00',
  balance_remaining: '200.00',
  remaining: '400.00',
  pending: '0.00',
  excess: '0.00',
  deposit_validated: false,
  fully_paid: false,
  requires_reconciliation: false,
  commercial_version_pending: false,
  receipts: [],
  refunds: [],
};

afterEach(() => {
  vi.unstubAllGlobals();
});

function setup(onPost: (body: string) => Promise<Response>, current = state) {
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === 'POST') return onPost(String(init.body));
    return new Response(
      JSON.stringify(
        url.endsWith('/history')
          ? { items: [], total: 0, page: 1, page_size: 50 }
          : current,
      ),
      { status: 200 },
    );
  });
  vi.stubGlobal('fetch', fetcher);
  render(<FinancialSection quotationId={state.quotation_id} />);
  return fetcher;
}

it('requires preview and explicit confirmation, with server versions and exact money strings', async () => {
  const sent: string[] = [];
  setup(async (body) => {
    sent.push(body);
    return new Response(
      JSON.stringify({
        ...state,
        financial_version: 1,
        received: '250.00',
        pending: '250.00',
      }),
    );
  });
  const user = userEvent.setup();
  await screen.findByText(
    'Nenhum recebimento registrado. Comprovante é opcional.',
  );
  await user.type(screen.getByLabelText('Valor em reais'), '250,00');
  await user.click(
    screen.getByRole('button', { name: 'Revisar operação financeira' }),
  );
  expect(sent).toHaveLength(0);
  const confirm = screen.getByRole('button', {
    name: 'Confirmar registro financeiro',
  });
  expect(confirm).toHaveFocus();
  await user.click(confirm);
  await screen.findByText(/Registro financeiro salvo/);
  expect(JSON.parse(sent[0])).toMatchObject({
    amount: '250.00',
    expected_financial_version: 0,
    expected_quotation_version: 1,
    method: 'pix',
  });
  expect(screen.getByText(/Sinal não validado/)).toBeInTheDocument();
});

it.each(['connection', 'server'])(
  'preserves the exact request and prevents editing after unknown %s outcome',
  async (failure) => {
    const sent: string[] = [];
    setup(async (body) => {
      sent.push(body);
      if (sent.length === 1) {
        if (failure === 'connection')
          throw new TypeError('Synthetic lost response');
        return new Response(
          JSON.stringify({ detail: 'Synthetic unavailable' }),
          {
            status: 503,
          },
        );
      }
      return new Response(JSON.stringify({ ...state, financial_version: 1 }));
    });
    const user = userEvent.setup();
    await screen.findByLabelText('Valor em reais');
    await user.type(screen.getByLabelText('Valor em reais'), '200.00');
    await user.click(
      screen.getByRole('button', { name: 'Revisar operação financeira' }),
    );
    await user.click(
      screen.getByRole('button', { name: 'Confirmar registro financeiro' }),
    );
    await screen.findByText(/Resultado desconhecido/);
    expect(screen.getByLabelText('Valor em reais')).toBeDisabled();
    await user.click(
      screen.getByRole('button', { name: 'Repetir a mesma operação' }),
    );
    await screen.findByText(/Registro financeiro salvo/);
    expect(sent).toHaveLength(2);
    expect(sent[1]).toBe(sent[0]);
  },
);

it('preserves form on version conflict and prepares a new explicit operation', async () => {
  let attempts = 0;
  const sent: string[] = [];
  const fetcher = setup(async (body) => {
    sent.push(body);
    attempts++;
    return attempts === 1
      ? new Response(
          JSON.stringify({
            detail: 'Os dados mudaram. Consulte a versão atual.',
          }),
          { status: 409 },
        )
      : new Response(JSON.stringify(state));
  });
  const user = userEvent.setup();
  await screen.findByLabelText('Valor em reais');
  await user.type(screen.getByLabelText('Valor em reais'), '200.00');
  await user.click(
    screen.getByRole('button', { name: 'Revisar operação financeira' }),
  );
  await user.click(
    screen.getByRole('button', { name: 'Confirmar registro financeiro' }),
  );
  await screen.findByText('Os dados mudaram. Consulte a versão atual.');
  expect(screen.getByLabelText('Valor em reais')).toHaveValue('200.00');
  await waitFor(() => expect(fetcher.mock.calls.length).toBeGreaterThan(3));
  await user.click(
    screen.getByRole('button', { name: 'Revisar operação financeira' }),
  );
  await user.click(
    screen.getByRole('button', { name: 'Confirmar registro financeiro' }),
  );
  await screen.findByText(/Registro financeiro salvo/);
  expect(JSON.parse(sent[0]).request_id).not.toBe(
    JSON.parse(sent[1]).request_id,
  );
});
