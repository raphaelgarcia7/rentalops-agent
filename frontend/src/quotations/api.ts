export type Component = {
  product_id: string;
  quantity: number;
  name: string;
  source_version: number;
};
export type LineInput = {
  kind: 'product' | 'kit';
  source_id: string;
  quantity: number;
  retained_line_id?: string;
  unit_price?: string;
  items?: Pick<Component, 'product_id' | 'quantity'>[];
  negotiation_reason?: string;
};
export type Dates = {
  pickup_date: string;
  event_date: string;
  return_date: string;
  valid_until: string;
  pickup_time: string | null;
  event_time: string | null;
  return_time: string | null;
};
export type Draft = Dates & {
  customer_id: string;
  lines: LineInput[];
  discount: {
    kind: 'amount' | 'percent';
    value: string;
    reason: string | null;
  } | null;
  quotation_id?: string;
  expected_version?: number;
};
export type Offer = Dates & {
  customer_id: string;
  lines: (Omit<LineInput, 'items'> & {
    id?: string;
    name: string;
    unit_price: string;
    items: Component[];
    source_version: number;
  })[];
  discount: Draft['discount'];
  subtotal: string;
  discount_amount: string;
  total: string;
  estimated_deposit: string;
  estimated_balance: string;
  catalog_versions: Record<string, number>;
  state: 'current' | 'expired';
  expired: boolean;
  requires_revision: boolean;
  capacity: {
    product_id: string;
    name: string;
    demand: number;
    apt: number;
    shortage: number;
  }[];
  capacity_mode: string;
  capacity_checked_at: string;
  stock_pending: boolean;
  planning_available_from: string;
};
export type Quotation = Omit<Offer, 'lines'> & {
  lines: (Offer['lines'][number] & { id: string })[];
  id: string;
  version: number;
  current_version: number;
  reason: string | null;
  actor_id: string;
  session_id: string;
  created_at: string;
  revised_at: string;
};
export type QuotationPage = {
  items: Quotation[];
  total: number;
  page: number;
  page_size: number;
};
export const dateLabels = {
  pickup_date: 'Retirada prevista',
  event_date: 'Data do evento',
  return_date: 'Devolução prevista',
  valid_until: 'Validade comercial',
} as const;
export class QuotationError extends Error {
  status: number;
  code: string;
  constructor(status: number, message: string, code = '') {
    super(message);
    this.status = status;
    this.code = code;
  }
}
export async function quotationRequest<T>(
  path: string,
  body?: object,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`/api/quotations${path}`, {
    method: body ? 'POST' : 'GET',
    credentials: 'same-origin',
    cache: 'no-store',
    signal,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    if (response.status === 401)
      window.dispatchEvent(new Event('rentalops-session-ended'));
    const data = (await response.json().catch(() => ({}))) as {
      detail?: string;
      code?: string;
      fields?: string[];
    };
    throw new QuotationError(
      response.status,
      response.status === 422
        ? 'Confira cliente, datas, itens, valores e motivos. Total mínimo R$ 0,01.'
        : (data.detail ??
            'Não foi possível concluir. Seu rascunho foi mantido.'),
      data.code,
    );
  }
  return (await response.json()) as T;
}
export function quotationFeedback(error: unknown) {
  return error instanceof QuotationError
    ? error.message
    : 'Resultado desconhecido por falha de conexão. Seu rascunho e a chave foram mantidos; tente reconciliar a mesma gravação.';
}
export function quotationLink(id: string) {
  return `/locacoes?orcamento=${encodeURIComponent(id)}`;
}
export function draftOf(record?: Quotation): Draft {
  return {
    customer_id: record?.customer_id ?? '',
    pickup_date: record?.pickup_date ?? '',
    event_date: record?.event_date ?? '',
    return_date: record?.return_date ?? '',
    valid_until: record?.valid_until ?? '',
    pickup_time: record?.pickup_time ?? null,
    event_time: record?.event_time ?? null,
    return_time: record?.return_time ?? null,
    discount: record?.discount ?? null,
    lines:
      record?.lines.map((line) => ({
        kind: line.kind,
        source_id: line.source_id,
        quantity: line.quantity,
        retained_line_id: line.id,
      })) ?? [],
    ...(record
      ? { quotation_id: record.id, expected_version: record.version }
      : {}),
  };
}
