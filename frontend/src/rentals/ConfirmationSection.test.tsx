import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { paymentRequest } from '../payments/api';
import { QuotationError, quotationRequest } from '../quotations/api';
import type { Quotation } from '../quotations/api';
import { rentalRequest } from './api';
import { ConfirmationSection } from './ConfirmationSection';

vi.mock('../payments/api', () => ({ paymentRequest: vi.fn() }));
vi.mock('./api', () => ({ rentalRequest: vi.fn() }));
vi.mock('../quotations/api', async (original) => ({
  ...(await original<object>()),
  quotationRequest: vi.fn(),
}));

const quotation = {
  id: '11111111-1111-4111-8111-111111111111',
  version: 1,
} as Quotation;
const preview = {
  quotation_version: 1,
  financial_version: 2,
  deposit_valid: true,
  pending: false,
  capacity: [
    {
      product_id: 'product',
      name: 'Synthetic arch',
      demand: 1,
      apt: 1,
      available: 1,
      committed: 0,
      shortage: 0,
    },
  ],
};
const rental = {
  id: 'rental',
  state: 'confirmed',
  version: 1,
  quotation_version: 1,
  financial_version: 2,
  pending: [],
  checked_at: '2026-10-09T12:00:00Z',
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(rentalRequest).mockRejectedValue(
    new QuotationError(404, 'Missing'),
  );
  vi.mocked(paymentRequest).mockResolvedValue({ financial_version: 2 });
  vi.mocked(quotationRequest).mockImplementation(async (path) =>
    path.endsWith('/confirmation-preview') ? preview : { current_version: 1 },
  );
});

it('does not present an unavailable rental read as an empty reservation', async () => {
  vi.mocked(rentalRequest).mockRejectedValue(
    new QuotationError(503, 'Consulta indisponível. Tente novamente.'),
  );
  render(<ConfirmationSection quotation={quotation} onConfirmed={vi.fn()} />);
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Consulta indisponível',
  );
  expect(
    screen.queryByText('Nenhuma reserva confirmada para este orçamento.'),
  ).not.toBeInTheDocument();
});

it('requires a fresh preview, disables insufficient stock and preserves the selected quotation', async () => {
  vi.mocked(quotationRequest).mockImplementation(async (path) =>
    path.endsWith('/confirmation-preview')
      ? {
          ...preview,
          pending: true,
          capacity: [{ ...preview.capacity[0], available: 0, shortage: 1 }],
        }
      : { current_version: 1 },
  );
  render(<ConfirmationSection quotation={quotation} onConfirmed={vi.fn()} />);
  expect(
    await screen.findByText('Nenhuma reserva confirmada para este orçamento.'),
  ).toBeVisible();
  await userEvent.click(
    screen.getByRole('button', { name: 'Consultar confirmação' }),
  );
  expect(
    await screen.findByText('Faltam 1. Combine a solução com a equipe.'),
  ).toBeVisible();
  expect(
    screen.getByRole('button', { name: 'Confirmar reserva' }),
  ).toBeDisabled();
  expect(quotationRequest).not.toHaveBeenCalledWith(
    expect.stringContaining('/confirm'),
    expect.objectContaining({ request_id: expect.any(String) }),
  );
});

it('reconciles unknown outcome using the same payload and never claims early success', async () => {
  let tries = 0;
  vi.mocked(quotationRequest).mockImplementation(async (path) => {
    if (path.endsWith('/confirmation-preview')) return preview;
    if (path.endsWith('/confirm')) {
      if (++tries === 1) throw new TypeError('Synthetic lost acknowledgement');
      vi.mocked(rentalRequest).mockImplementation(async (url) =>
        url.includes('/history')
          ? { items: [], page: 1, page_size: 10, total: 0 }
          : rental,
      );
      return rental;
    }
    return { current_version: 1 };
  });
  const onConfirmed = vi.fn();
  render(
    <ConfirmationSection quotation={quotation} onConfirmed={onConfirmed} />,
  );
  await waitFor(() =>
    expect(
      screen.getByRole('button', { name: 'Consultar confirmação' }),
    ).toBeEnabled(),
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Consultar confirmação' }),
  );
  const confirm = await screen.findByRole('button', {
    name: 'Confirmar reserva',
  });
  expect(confirm).toHaveFocus();
  await userEvent.click(confirm);
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Resultado desconhecido',
  );
  expect(onConfirmed).not.toHaveBeenCalled();
  await userEvent.click(
    screen.getByRole('button', { name: 'Reconciliar a mesma confirmação' }),
  );
  expect(
    await screen.findByText('Reserva confirmada · locação v1'),
  ).toBeVisible();
  expect(onConfirmed).toHaveBeenCalledOnce();
  const commands = vi
    .mocked(quotationRequest)
    .mock.calls.filter(([path]) => path.endsWith('/confirm'));
  expect(commands).toHaveLength(2);
  expect(commands[0][1]).toEqual(commands[1][1]);
});

it('reports an authoritative conflict without allocating and permits a new preview', async () => {
  vi.mocked(quotationRequest).mockImplementation(async (path) => {
    if (path.endsWith('/confirmation-preview')) return preview;
    if (path.endsWith('/confirm'))
      throw new QuotationError(
        409,
        'Capacidade insuficiente. O dinheiro foi preservado.',
        'capacity_conflict',
      );
    return { current_version: 1 };
  });
  const callback = vi.fn();
  render(<ConfirmationSection quotation={quotation} onConfirmed={callback} />);
  await waitFor(() =>
    expect(
      screen.getByRole('button', { name: 'Consultar confirmação' }),
    ).toBeEnabled(),
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Consultar confirmação' }),
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'Confirmar reserva' }),
  );
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Capacidade insuficiente',
  );
  expect(callback).not.toHaveBeenCalled();
  expect(
    screen.getByRole('button', { name: 'Consultar confirmação' }),
  ).toBeEnabled();
});
