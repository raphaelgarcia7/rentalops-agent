export type HistoryEntry = {
  id: string;
  actor_id: string;
  session_id: string;
  operation: string;
  reason: string;
  created_at: string;
  snapshot: Record<string, unknown>;
};
export type Movement = Omit<HistoryEntry, 'snapshot'> & {
  quantity: number;
  total_after: number;
  maintenance_after: number;
};
export type Maintenance = {
  id: string;
  quantity: number;
  released_quantity: number;
  reason: string;
};
export type Photo = {
  id: string;
  format: string;
  size: number;
  sha256: string;
  order: number;
  is_principal: boolean;
};
export type RecordSummary = {
  id: string;
  name: string;
  price: string;
  version: number;
  is_active: boolean;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
};
export type Product = RecordSummary & {
  total_quantity: number;
  maintenance_quantity: number;
  apt_quantity: number;
  description: string | null;
  category: string | null;
  color: string | null;
  dimensions: string | null;
  replacement_value: string | null;
  observation: string | null;
};
export type KitItem = {
  product_id: string;
  name: string;
  quantity: number;
  is_active: boolean;
};
export type Kit = RecordSummary & {
  items: KitItem[];
  needs_review: boolean;
};
export type ProductDetail = Product & {
  history: HistoryEntry[];
  movements: Movement[];
  maintenance: Maintenance[];
  photos: Photo[];
};
export type KitDetail = Kit & { history: HistoryEntry[] };
export type CatalogRecord = Product | Kit;
export type CatalogDetail = ProductDetail | KitDetail;
export type Kind = 'products' | 'kits';
export type CatalogPage<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

export class CatalogError extends Error {
  status: number;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

export async function catalogRequest<T>(
  path: string,
  options?: { method: 'POST' | 'PATCH'; body: object | FormData },
  signal?: AbortSignal,
): Promise<T> {
  const multipart = options?.body instanceof FormData;
  const response = await fetch(`/api/${path}`, {
    method: options?.method ?? 'GET',
    credentials: 'same-origin',
    cache: 'no-store',
    signal,
    headers:
      options && !multipart
        ? { 'Content-Type': 'application/json' }
        : undefined,
    body: options
      ? multipart
        ? (options.body as FormData)
        : JSON.stringify(options.body)
      : undefined,
  });
  if (!response.ok) {
    if (response.status === 401)
      window.dispatchEvent(new Event('rentalops-session-ended'));
    const data = (await response.json().catch(() => ({}))) as {
      detail?: unknown;
    };
    throw new CatalogError(
      response.status,
      typeof data.detail === 'string'
        ? data.detail
        : 'Não foi possível concluir. Tente novamente em instantes.',
    );
  }
  return (await response.json()) as T;
}

export function feedback(error: unknown): string {
  return error instanceof CatalogError
    ? error.message
    : 'Não foi possível conectar. Seu rascunho foi mantido. Tente novamente.';
}

export function priceLabel(value: string): string {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(Number(value));
}

export function productRecord(record: CatalogRecord): record is Product {
  return 'total_quantity' in record;
}

export function productDetail(record: CatalogDetail): record is ProductDetail {
  return 'movements' in record;
}

export const operationLabels: Record<string, string> = {
  initial: 'Estoque inicial',
  entry: 'Entrada',
  withdrawal: 'Baixa',
  correction: 'Correção',
  maintenance: 'Manutenção / avaria',
  release: 'Liberação',
  created: 'Cadastro',
  edited: 'Edição',
  inactivated: 'Inativação',
  photo_added: 'Foto adicionada',
  photo_edited: 'Foto principal / ordem',
  photo_detached: 'Foto retirada da galeria',
};
