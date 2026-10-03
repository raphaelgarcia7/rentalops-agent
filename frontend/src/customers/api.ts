export const addressLabels = {
  postal_code: 'CEP',
  street: 'Logradouro',
  number: 'Número',
  complement: 'Complemento',
  neighborhood: 'Bairro',
  city: 'Cidade',
  state: 'UF',
} as const;
export const fieldLabels = {
  name: 'Nome',
  phone: 'Telefone / WhatsApp',
  email: 'E-mail',
  notes: 'Observações',
  cpf: 'CPF',
  rg: 'RG',
  address: 'Endereço',
  ...addressLabels,
} as const;
export type Address = Record<keyof typeof addressLabels, string | null>;
export type Customer = {
  id: string;
  name: string;
  phone: string;
  email: string | null;
  notes: string | null;
  cpf: string | null;
  rg: string | null;
  address: Address | null;
  version: number;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
};
export type CustomerDetail = Customer & {
  history: {
    id: string;
    actor_id: string;
    session_id: string;
    created_at: string;
    version: number;
    changed_fields: string[];
  }[];
};
export type CustomerPageData = {
  items: Pick<Customer, 'id' | 'name' | 'phone' | 'version'>[];
  total: number;
  page: number;
  page_size: number;
};
export class CustomerError extends Error {
  status: number;
  code: string;
  existingIds: string[];
  constructor(
    status: number,
    message: string,
    code = '',
    existingIds: string[] = [],
  ) {
    super(message);
    this.status = status;
    this.code = code;
    this.existingIds = existingIds;
  }
}
export async function customerRequest<T>(
  path: string,
  method: 'POST' | 'PATCH' | 'GET',
  body?: object,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`/api/customers${path}`, {
    method,
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
      existing_ids?: string[];
      fields?: string[];
    };
    const fields = data.fields
      ?.map((field) => fieldLabels[field as keyof typeof fieldLabels])
      .filter(Boolean);
    throw new CustomerError(
      response.status,
      fields?.length
        ? `Confira: ${fields.join(', ')}.`
        : (data.detail ?? 'Não foi possível concluir. Tente novamente.'),
      data.code,
      data.existing_ids,
    );
  }
  return (await response.json()) as T;
}
export function customerFeedback(error: unknown) {
  return error instanceof CustomerError
    ? error.message
    : 'Não foi possível conectar. Seu rascunho foi mantido. Tente novamente.';
}
export function customerLink(id: string) {
  return `/clientes?cliente=${encodeURIComponent(id)}`;
}
