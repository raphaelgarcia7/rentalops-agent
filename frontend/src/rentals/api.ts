import { QuotationError } from '../quotations/api';
import type { Offer } from '../quotations/api';

export type RentalSummary = {
  id: string;
  version: number;
  state: 'confirmed';
  inventory_pending: boolean;
  financial_pending: boolean;
};
export type Rental = RentalSummary & {
  quotation_id: string;
  quotation_version: number;
  financial_version: number;
  checked_at: string;
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
): Promise<T> {
  const response = await fetch(`/api/rentals${path}`, {
    credentials: 'same-origin',
    cache: 'no-store',
    signal,
  });
  if (!response.ok) {
    if (response.status === 401)
      window.dispatchEvent(new Event('rentalops-session-ended'));
    throw new QuotationError(
      response.status,
      'Não foi possível consultar a locação. Tente novamente.',
    );
  }
  return (await response.json()) as T;
}
