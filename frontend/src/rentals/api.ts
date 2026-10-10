import { QuotationError } from '../quotations/api';
import type { Offer } from '../quotations/api';
import type { Payments } from '../payments/api';

export type RentalSummary = {
  id: string;
  version: number;
  state: 'confirmed' | 'cancelled' | 'review' | 'out' | 'completed';
  inventory_pending: boolean;
  financial_pending: boolean;
};
export type Rental = RentalSummary & {
  allocations: {
    product_id: string;
    quantity: number;
    pickup_date: string;
    return_date: string;
  }[];
  quotation_id: string;
  quotation_version: number;
  financial_version: number;
  checked_at: string;
  current_financial: Payments;
  confirmation_deposit: string;
  signature_commercial_version: number;
  pending: {
    id: string;
    kind: 'inventory' | 'financial';
    source: string;
    source_version: number;
    created_at: string;
    resolved: boolean;
  }[];
};
export type Preview = {
  quotation_version: number;
  financial_version: number;
  deposit_valid: boolean;
  pending: boolean;
  capacity: Offer['capacity'];
  checked_at: string;
};
export type History = {
  items: {
    id: string;
    version: number;
    operation: string;
    reason: string | null;
    actor_id: string;
    created_at: string;
  }[];
  page: number;
  page_size: number;
  total: number;
};
export async function rentalRequest<T>(
  path: string,
  signal?: AbortSignal,
  body?: object,
): Promise<T> {
  const response = await fetch(`/api/rentals${path}`, {
    credentials: 'same-origin',
    cache: 'no-store',
    signal,
    method: body ? 'POST' : 'GET',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    if (response.status === 401)
      window.dispatchEvent(new Event('rentalops-session-ended'));
    const data = (await response.json().catch(() => ({}))) as {
      detail?: string;
      code?: string;
      capacity?: Offer['capacity'];
    };
    throw new QuotationError(
      response.status,
      response.status >= 500
        ? 'Não foi possível consultar a locação. Tente novamente.'
        : (data.detail ??
            'Não foi possível consultar a locação. Tente novamente.'),
      data.code,
      data.capacity,
    );
  }
  return (await response.json()) as T;
}

export type ChangePreview = {
  before: Offer;
  after: Offer;
  financial: {
    net_received: string;
    remaining: string;
    excess: string;
    historical_deposit: string;
    deposit_due: string;
    balance_due: string;
    requires_payment_review: boolean;
  };
  requires_new_signature: boolean;
};
export type RentalRevision = {
  id?: string;
  mode: 'change' | 'resume';
  expected_rental_version: number;
  expected_quotation_version: number;
  expected_financial_version: number;
  financial: Payments;
};
export const rentalStateLabel = {
  confirmed: 'Reserva confirmada',
  cancelled: 'Locação cancelada',
  review: 'Locação em revisão',
  out: 'Materiais em uso',
  completed: 'Locação concluída',
};
