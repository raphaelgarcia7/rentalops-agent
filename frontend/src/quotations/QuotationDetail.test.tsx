import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { QuotationDetail } from './QuotationDetail';
import type { Quotation } from './api';
import type { Payments } from '../payments/api';

const record: Quotation = {
  id: '11111111-1111-4111-8111-111111111111',
  customer_id: '22222222-2222-4222-8222-222222222222',
  version: 1,
  current_version: 1,
  lines: [],
  capacity: [],
  total: '400.00',
  subtotal: '400.00',
  discount_amount: '0.00',
  estimated_deposit: '200.00',
  estimated_balance: '200.00',
  revised_at: '2026-10-10T12:00:00Z',
  created_at: '2026-10-10T12:00:00Z',
  pickup_date: '2026-10-11',
  event_date: '2026-10-12',
  return_date: '2026-10-13',
  valid_until: '2026-10-10',
  pickup_time: null,
  event_time: null,
  return_time: null,
  discount: null,
  catalog_versions: {},
  state: 'current',
  expired: false,
  requires_revision: false,
  capacity_mode: 'allocation_aware',
  capacity_checked_at: '2026-10-10T12:00:00Z',
  stock_pending: false,
  planning_available_from: '2026-10-14',
  reason: null,
  actor_id: 'synthetic',
  session_id: 'synthetic',
};
const empty: Payments = {
  quotation_id: record.id,
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
const paid: Payments = {
  ...empty,
  financial_version: 2,
  reconciled_quotation_version: 1,
  received: '200.00',
  net_received: '200.00',
  applied_deposit: '200.00',
  deposit_remaining: '0.00',
  remaining: '200.00',
  deposit_validated: true,
  receipts: [
    {
      id: 'receipt',
      revision: 1,
      amount: '200.00',
      method: 'pix',
      business_date: '2026-10-08',
      observation: null,
      actor_id: 'synthetic',
      session_id: 'synthetic',
      created_at: record.revised_at,
      refunded: '0.00',
      net: '200.00',
      applied_deposit: '200.00',
      applied_balance: '0.00',
      pending: '0.00',
      proofs: [],
    },
  ],
};
const rental = {
  state: 'confirmed',
  allocations: [],
  current_financial: paid,
  confirmation_deposit: '200.00',
  signature_commercial_version: 1,
  id: 'rental',
  version: 1,
  quotation_version: 1,
  financial_version: 2,
  checked_at: '2026-10-10T12:00:00Z',
  pending: [],
};
const page = (items: unknown[]) => ({
  items,
  total: items.length,
  page: 1,
  page_size: 50,
});
afterEach(() => vi.unstubAllGlobals());

it.each([
  { unknown: false, readFailure: false },
  { unknown: true, readFailure: false },
  { unknown: false, readFailure: true },
  { unknown: true, readFailure: true },
])(
  'refreshes externally paid financial facts and history through confirmation/replay: %j',
  async ({ unknown, readFailure }) => {
    let financial = empty;
    let confirmed = false;
    let unavailable = readFailure;
    const payloads: string[] = [];
    const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
      if (confirmed && unavailable && url.endsWith('/payments/history'))
        return new Response('{}', { status: 503 });
      let result: unknown = record;
      if (url.endsWith('/payments')) result = financial;
      else if (url.endsWith('/payments/history'))
        result = page(
          financial.financial_version
            ? [
                ...['receipt', 'reconciliation'].map((operation, index) => ({
                  id: String(index),
                  operation,
                  financial_version: index + 1,
                  quotation_version: 1,
                  created_at: record.revised_at,
                  before: empty,
                  after: paid,
                })),
              ]
            : [],
        );
      else if (url.endsWith('/confirmation-preview'))
        result = {
          quotation_version: 1,
          financial_version: 2,
          deposit_valid: true,
          pending: false,
          capacity: [],
        };
      else if (url.endsWith('/confirm')) {
        payloads.push(String(init?.body));
        confirmed = true;
        if (unknown && payloads.length === 1)
          throw new TypeError('Synthetic lost acknowledgement');
        result = rental;
      } else if (url.includes('/rentals/by-quotation/')) {
        if (!confirmed) return new Response('{}', { status: 404 });
        result = rental;
      } else if (url.endsWith('/versions')) result = [record];
      else if (url.includes('/rentals/rental/history')) result = page([]);
      return new Response(JSON.stringify(result));
    });
    vi.stubGlobal('fetch', fetcher);
    render(
      <MemoryRouter>
        <QuotationDetail record={record} onEdit={vi.fn()} onClose={vi.fn()} />
      </MemoryRouter>,
    );
    const panel = within(
      screen.getByRole('region', { name: 'Financeiro deste orçamento' }),
    );
    await panel.findByText('Sinal não validado');
    expect(
      panel.getByText('Nenhuma movimentação financeira no histórico.'),
    ).toBeVisible();
    financial = paid; // Another attendant receives and reconciles while the detail stays open.
    await userEvent.click(
      await screen.findByRole('button', { name: 'Consultar confirmação' }),
    );
    await panel.findByText('Sinal validado em um único recebimento');
    expect(
      panel.getByText(/Versão comercial 1 · Financeiro 2 · Conferida 1/),
    ).toBeVisible();
    expect(
      panel.getByText(/Recebimento registrado · financeiro 1/),
    ).toBeVisible();
    expect(
      panel.getByText(/Conciliação substituída · financeiro 2/),
    ).toBeVisible();
    expect(
      panel.queryByText('Nenhuma movimentação financeira no histórico.'),
    ).not.toBeInTheDocument();
    expect(
      panel.getByText('Recebido registrado').nextElementSibling,
    ).toHaveTextContent('200,00');
    await userEvent.click(
      await screen.findByRole('button', { name: 'Confirmar reserva' }),
    );
    if (readFailure) {
      expect(await panel.findByRole('alert')).toHaveTextContent(
        'Não foi possível consultar o financeiro',
      );
      expect(panel.queryByText('Sinal não validado')).not.toBeInTheDocument();
      expect(
        panel.queryByText('Sinal validado em um único recebimento'),
      ).not.toBeInTheDocument();
      expect(
        panel.queryByText('Nenhuma movimentação financeira no histórico.'),
      ).not.toBeInTheDocument();
      unavailable = false;
      await userEvent.click(
        panel.getByRole('button', { name: 'Reconsultar financeiro' }),
      );
    }
    if (unknown) {
      await screen.findByText(/Resultado desconhecido/);
      expect(
        screen.queryByText('Reserva confirmada · locação v1'),
      ).not.toBeInTheDocument();
      await panel.findByText('Sinal validado em um único recebimento');
      await userEvent.click(
        screen.getByRole('button', { name: 'Reconciliar a mesma confirmação' }),
      );
    }
    await screen.findByText('Reserva confirmada · locação v1');
    expect(screen.getByText('Validade comercial vigente')).toBeVisible();
    expect(
      screen.queryByText('Validade vigente · não é reserva confirmada'),
    ).not.toBeInTheDocument();
    await waitFor(() =>
      expect(
        panel.getByText('Sinal validado em um único recebimento'),
      ).toBeVisible(),
    );
    expect(panel.queryByText('Sinal não validado')).not.toBeInTheDocument();
    expect(payloads).toHaveLength(unknown ? 2 : 1);
    if (unknown) expect(payloads[1]).toBe(payloads[0]);
  },
);
