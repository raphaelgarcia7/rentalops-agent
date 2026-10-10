import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { RentalChanges } from './RentalChanges';
import type { Quotation } from '../quotations/api';

const quotation = {
  id: 'quote',
  version: 1,
  current_version: 1,
  expired: false,
} as Quotation;
const rental = {
  id: 'rental',
  state: 'confirmed',
  version: 1,
  allocations: [{ product_id: 'product', quantity: 1 }],
  signature_commercial_version: 1,
  current_financial: {
    quotation_version: 1,
    financial_version: 2,
    net_received: '200.00',
    remaining: '200.00',
    excess: '0.00',
  },
};
const response = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status });
afterEach(() => vi.unstubAllGlobals());

it('records a request without approval and reconciles unknown cancellation with the identical command', async () => {
  const calls: string[] = [];
  let outcomeUnknown = true;
  const onChanged = vi.fn();
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/cancellations')) {
        calls.push(String(init?.body));
        if (outcomeUnknown) {
          outcomeUnknown = false;
          throw new TypeError('Synthetic lost acknowledgement');
        }
        return response({ ...rental, version: 2 });
      }
      return response(rental);
    }),
  );
  render(
    <MemoryRouter>
      <RentalChanges quotation={quotation} onChanged={onChanged} />
    </MemoryRouter>,
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'Registrar cancelamento' }),
  );
  await userEvent.type(
    screen.getByLabelText('Motivo do cancelamento'),
    'Synthetic request',
  );
  await userEvent.click(
    screen.getByRole('button', {
      name: 'Registrar solicitação sem liberar estoque',
    }),
  );
  expect(
    await screen.findByText(
      /Resultado desconhecido. Reconcile o mesmo cancelamento/,
    ),
  ).toBeVisible();
  expect(screen.getByLabelText('Motivo do cancelamento')).toBeDisabled();
  expect(onChanged).not.toHaveBeenCalled();
  await userEvent.click(
    screen.getByRole('button', { name: 'Reconciliar o mesmo cancelamento' }),
  );
  await screen.findByText(
    /Solicitação registrada. A reserva e o estoque continuam comprometidos/,
  );
  expect(calls).toHaveLength(2);
  expect(calls[0]).toBe(calls[1]);
  expect(JSON.parse(calls[0])).toMatchObject({
    approved: false,
    expected_rental_version: 1,
    expected_financial_version: 2,
    expected_quotation_version: 1,
  });
  expect(onChanged).toHaveBeenCalledOnce();
});

it('requires explicit team approval and presents the released stock separately from money', async () => {
  const commands: object[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/cancellations')) {
        commands.push(JSON.parse(String(init?.body)));
        return response({
          ...rental,
          state: 'cancelled',
          allocations: [],
          version: 2,
        });
      }
      return response(rental);
    }),
  );
  render(
    <MemoryRouter>
      <RentalChanges quotation={quotation} onChanged={vi.fn()} />
    </MemoryRouter>,
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'Registrar cancelamento' }),
  );
  expect(
    screen.getByRole('button', {
      name: 'Registrar solicitação sem liberar estoque',
    }),
  ).toBeDisabled();
  await userEvent.type(
    screen.getByLabelText('Motivo do cancelamento'),
    'Synthetic approved decision',
  );
  await userEvent.click(
    screen.getByRole('checkbox', { name: /A equipe aprova/ }),
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Confirmar cancelamento aprovado' }),
  );
  await screen.findByText(
    /Cancelamento aprovado registrado. Alocação desta reserva liberada/,
  );
  expect(screen.getByText('Sem alocação de estoque')).toBeVisible();
  expect(
    screen.getByText('Dinheiro líquido').nextElementSibling,
  ).toHaveTextContent('R$ 200,00');
  expect(commands[0]).toMatchObject({ approved: true });
});

it('keeps an unapproved cancellation request in review without claiming allocated stock', async () => {
  const review = { ...rental, state: 'review', allocations: [] };
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) =>
      response(
        url.endsWith('/cancellations') ? { ...review, version: 2 } : review,
      ),
    ),
  );
  render(
    <MemoryRouter>
      <RentalChanges quotation={quotation} onChanged={vi.fn()} />
    </MemoryRouter>,
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'Registrar cancelamento' }),
  );
  await userEvent.type(
    screen.getByLabelText('Motivo do cancelamento'),
    'Synthetic review request',
  );
  await userEvent.click(
    screen.getByRole('button', {
      name: 'Registrar solicitação sem liberar estoque',
    }),
  );
  expect(
    await screen.findByText(/A locação permanece em revisão, sem alocação/),
  ).toBeVisible();
  expect(screen.getByText('Sem alocação de estoque')).toBeVisible();
  expect(
    screen.queryByText(/estoque continuam comprometidos/),
  ).not.toBeInTheDocument();
});

it('does not turn an unavailable read into an empty or expired rental flow', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => response({ detail: 'Synthetic read unavailable' }, 503)),
  );
  render(
    <MemoryRouter>
      <RentalChanges quotation={quotation} onChanged={vi.fn()} />
    </MemoryRouter>,
  );
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Não foi possível consultar a locação. Tente novamente.',
  );
  await waitFor(() =>
    expect(
      screen.queryByText('Consultando alterações da locação…'),
    ).not.toBeInTheDocument(),
  );
  expect(
    screen.queryByRole('button', { name: 'Revisar e retomar' }),
  ).not.toBeInTheDocument();
});
