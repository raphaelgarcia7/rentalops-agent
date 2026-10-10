export type Proof = {
  id: string;
  receipt_id: string;
  content_type: string;
  size: number;
  sha256: string;
  actor_id: string;
  created_at: string;
};
export type Receipt = {
  id: string;
  revision: number;
  amount: string;
  method: 'pix' | 'cash' | 'card';
  business_date: string;
  observation: string | null;
  actor_id: string;
  session_id: string;
  created_at: string;
  refunded: string;
  net: string;
  applied_deposit: string;
  applied_balance: string;
  pending: string;
  proofs: Proof[];
};
export type Payments = {
  quotation_id: string;
  quotation_version: number;
  financial_version: number;
  reconciled_quotation_version: number | null;
  total: string;
  estimated_deposit: string;
  estimated_balance: string;
  received: string;
  refunded: string;
  net_received: string;
  applied_deposit: string;
  applied_balance: string;
  deposit_remaining: string;
  balance_remaining: string;
  remaining: string;
  pending: string;
  excess: string;
  deposit_validated: boolean;
  fully_paid: boolean;
  requires_reconciliation: boolean;
  commercial_version_pending: boolean;
  receipts: Receipt[];
  refunds: {
    id: string;
    receipt_id: string;
    amount: string;
    method: string;
    business_date: string;
    reason: string;
    actor_id: string;
    session_id: string;
    created_at: string;
  }[];
};
export type FinancialEvent = {
  id: string;
  financial_version: number;
  quotation_version: number;
  operation: string;
  actor_id: string;
  session_id: string;
  reason: string | null;
  before: Payments;
  after: Payments;
  created_at: string;
};
export type History = {
  items: FinancialEvent[];
  page: number;
  page_size: number;
  total: number;
};
export class PaymentError extends Error {
  status: number;
  code: string;
  constructor(status: number, message: string, code = '') {
    super(message);
    this.status = status;
    this.code = code;
  }
}
export async function paymentRequest<T>(
  id: string,
  path = '',
  body?: object | FormData,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(
    `/api/quotations/${encodeURIComponent(id)}/payments${path}`,
    {
      method: body ? 'POST' : 'GET',
      credentials: 'same-origin',
      cache: 'no-store',
      signal,
      headers:
        body && !(body instanceof FormData)
          ? { 'Content-Type': 'application/json' }
          : undefined,
      body:
        body instanceof FormData
          ? body
          : body
            ? JSON.stringify(body)
            : undefined,
    },
  );
  if (!response.ok) {
    if (response.status === 401)
      window.dispatchEvent(new Event('rentalops-session-ended'));
    const data = (await response.json().catch(() => ({}))) as {
      detail?: string;
      code?: string;
    };
    throw new PaymentError(
      response.status,
      data.detail ??
        'Não foi possível concluir. Confira os campos; seu formulário foi mantido.',
      data.code,
    );
  }
  return (await response.json()) as T;
}
export const methods = { pix: 'Pix', cash: 'Dinheiro', card: 'Cartão' };
export const operations: Record<string, string> = {
  receipt: 'Recebimento registrado',
  reconciliation: 'Conciliação substituída',
  correction: 'Recebimento corrigido',
  refund: 'Devolução realizada registrada',
  proof: 'Comprovante anexado',
};
export const businessToday = () =>
  new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(
    new Date(),
  );
