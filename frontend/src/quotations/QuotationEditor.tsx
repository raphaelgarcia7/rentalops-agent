import { useContext, useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { AuthContext } from '../authContext';
import { catalogRequest } from '../catalog/api';
import type { CatalogPage, Product, Kit } from '../catalog/api';
import { customerRequest } from '../customers/api';
import type { CustomerPageData } from '../customers/api';
import {
  dateLabels,
  draftOf,
  quotationRequest,
  quotationFeedback,
  QuotationError,
} from './api';
import type { Draft, LineInput, Offer, Quotation } from './api';
import { OfferSummary } from './OfferSummary';

type PickedLine = LineInput & {
  label: string;
  key: string;
  custom: boolean;
  customItems: { product_id: string; quantity: number }[];
  price: string;
  reason: string;
};
export function QuotationEditor({
  initial,
  onSaved,
  onCancel,
}: {
  initial?: Quotation;
  onSaved: (value: Quotation) => void;
  onCancel: () => void;
}) {
  const { authenticated } = useContext(AuthContext);
  const [draft, setDraft] = useState(() => draftOf(initial));
  const [lines, setLines] = useState<PickedLine[]>(
    () =>
      initial?.lines.map((line) => ({
        ...draftOf(initial).lines.find(
          (entry) => entry.retained_line_id === line.id,
        )!,
        label: line.name,
        key: line.id,
        custom: false,
        customItems: line.items.map((item) => ({
          product_id: item.product_id,
          quantity: item.quantity,
        })),
        price: line.unit_price,
        reason: line.negotiation_reason ?? '',
      })) ?? [],
  );
  const [customers, setCustomers] = useState<CustomerPageData['items']>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [kits, setKits] = useState<Kit[]>([]);
  const [customerSearch, setCustomerSearch] = useState('');
  const [sourceSearch, setSourceSearch] = useState('');
  const [kind, setKind] = useState<'product' | 'kit'>('kit');
  const [source, setSource] = useState('');
  const [preview, setPreview] = useState<Offer | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [versionReason, setVersionReason] = useState('');
  const [current, setCurrent] = useState<Quotation | null>(null);
  const [uncertain, setUncertain] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const pending = useRef<object | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const alert = useRef<HTMLDivElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, []);
  useEffect(() => {
    if (error) alert.current?.focus();
  }, [error]);
  useEffect(() => {
    if (!authenticated) return;
    const controller = new AbortController();
    queueMicrotask(() => {
      setLoading(true);
      setError('');
    });
    void Promise.all([
      customerRequest<CustomerPageData>(
        '/search',
        'POST',
        { name: customerSearch, page_size: 100 },
        controller.signal,
      ),
      catalogRequest<CatalogPage<Product>>(
        `products?search=${encodeURIComponent(sourceSearch)}&page_size=100`,
        undefined,
        controller.signal,
      ),
      catalogRequest<CatalogPage<Kit>>(
        `kits?search=${encodeURIComponent(sourceSearch)}&page_size=100`,
        undefined,
        controller.signal,
      ),
    ])
      .then(([customerPage, productPage, kitPage]) => {
        if (!controller.signal.aborted) {
          setCustomers(customerPage.items);
          setProducts(productPage.items);
          setKits(kitPage.items);
        }
      })
      .catch((problem: unknown) => {
        if (!controller.signal.aborted) setError(quotationFeedback(problem));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [authenticated, customerSearch, sourceSearch, refresh]);
  function changed() {
    setPreview(null);
    setError('');
    pending.current = null;
  }
  function updateDraft(changes: Partial<Draft>) {
    changed();
    setDraft((value) => ({ ...value, ...changes }));
  }
  function updateLine(index: number, changes: Partial<PickedLine>) {
    changed();
    setLines((value) =>
      value.map((line, i) => (i === index ? { ...line, ...changes } : line)),
    );
  }
  function addLine() {
    const record = (kind === 'kit' ? kits : products).find(
      (record) => record.id === source,
    );
    if (!record) return;
    changed();
    setLines((value) => [
      ...value,
      {
        kind,
        source_id: record.id,
        quantity: 1,
        label: record.name,
        key: crypto.randomUUID(),
        custom: false,
        customItems:
          'items' in record
            ? record.items.map((item) => ({
                product_id: item.product_id,
                quantity: item.quantity,
              }))
            : [],
        price: record.price,
        reason: '',
      },
    ]);
    setSource('');
  }
  function payload(): Draft {
    return {
      ...draft,
      lines: lines.map((line) => ({
        kind: line.kind,
        source_id: line.source_id,
        quantity: line.quantity,
        ...(line.retained_line_id
          ? { retained_line_id: line.retained_line_id }
          : {}),
        ...(line.custom
          ? {
              unit_price: line.price,
              negotiation_reason: line.reason,
              ...(line.kind === 'kit' ? { items: line.customItems } : {}),
            }
          : {}),
      })),
    };
  }
  async function calculate(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      setPreview(await quotationRequest<Offer>('/preview', payload()));
    } catch (problem) {
      setError(quotationFeedback(problem));
      if (
        problem instanceof QuotationError &&
        problem.status === 409 &&
        initial
      ) {
        try {
          setCurrent(await quotationRequest<Quotation>(`/${initial.id}`));
        } catch {
          /* Retry preserves the draft and shows its original failure. */
        }
      }
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    if (!preview && !pending.current) return;
    setBusy(true);
    setError('');
    const body = pending.current ?? {
      ...payload(),
      request_id: crypto.randomUUID(),
      catalog_versions: preview!.catalog_versions,
      reason: initial ? versionReason : null,
    };
    pending.current = body;
    try {
      const saved = await quotationRequest<Quotation>(
        initial ? `/${initial.id}/versions` : '',
        body,
      );
      pending.current = null;
      setUncertain(false);
      onSaved(saved);
    } catch (problem) {
      setError(quotationFeedback(problem));
      if (
        problem instanceof QuotationError &&
        problem.status !== 503 &&
        problem.status !== 401
      ) {
        pending.current = null;
        setUncertain(false);
        setPreview(null);
        if (problem.status === 409 && initial) {
          try {
            setCurrent(await quotationRequest<Quotation>(`/${initial.id}`));
          } catch {
            /* The retained draft remains available for retry. */
          }
        }
      } else setUncertain(true);
    } finally {
      setBusy(false);
    }
  }
  function acceptCurrent(keep: boolean) {
    if (!current) return;
    if (keep) {
      setDraft((value) => ({ ...value, expected_version: current.version }));
      // Old retained IDs are no longer from the current revision; preserve negotiated values explicitly.
      setLines((value) =>
        value.map((line) => ({
          ...line,
          retained_line_id: undefined,
          custom: true,
          reason: line.reason,
        })),
      );
    } else {
      setDraft(draftOf(current));
      setLines(
        current.lines.map((line) => ({
          ...draftOf(current).lines.find(
            (entry) => entry.retained_line_id === line.id,
          )!,
          key: line.id,
          label: line.name,
          custom: false,
          customItems: line.items.map((item) => ({
            product_id: item.product_id,
            quantity: item.quantity,
          })),
          price: line.unit_price,
          reason: line.negotiation_reason ?? '',
        })),
      );
    }
    changed();
    setCurrent(null);
  }
  return (
    <section
      className="catalog-panel quotation-editor"
      aria-labelledby="quotation-editor-title"
    >
      <h2 id="quotation-editor-title" ref={heading} tabIndex={-1}>
        {initial ? 'Nova revisão do orçamento' : 'Novo orçamento'}
      </h2>
      <p>
        Preços por locação. Dados negociados ficam somente na memória desta
        tela. Datas e horários locais: São Paulo.
      </p>
      {error && (
        <div role="alert" tabIndex={-1} ref={alert} className="auth-feedback">
          {error}
          <button
            type="button"
            className="auth-retry"
            onClick={() => setRefresh((value) => value + 1)}
            disabled={busy}
          >
            Reconsultar opções
          </button>
        </div>
      )}
      {loading && <p role="status">Carregando clientes e catálogo…</p>}
      {current && (
        <section
          className="quotation-conflict"
          aria-label="Comparação de conflito"
        >
          <h3>Versão atual {current.version}</h3>
          <p>
            Total atual {current.total} · validade {current.valid_until}. Seu
            rascunho continua abaixo.
          </p>
          <ul>
            {current.lines.map((line) => (
              <li key={line.id}>
                {line.name} · {line.quantity} × {line.unit_price}
              </li>
            ))}
          </ul>
          <button
            type="button"
            className="auth-retry"
            onClick={() => acceptCurrent(true)}
          >
            Manter rascunho após comparar
          </button>
          <button
            type="button"
            className="auth-retry"
            onClick={() => acceptCurrent(false)}
          >
            Carregar revisão atual
          </button>
        </section>
      )}
      {uncertain && (
        <div className="quotation-conflict" role="status">
          <p>
            Resultado da gravação desconhecido. Reconcile com a mesma chave
            antes de editar.
          </p>
          <button
            type="button"
            className="auth-button"
            disabled={busy}
            onClick={() => void save()}
          >
            Reconciliar mesma gravação
          </button>
        </div>
      )}
      <form onSubmit={(event) => void calculate(event)}>
        <fieldset disabled={busy || uncertain}>
          <legend>Cliente e datas</legend>
          <div className="catalog-form-grid">
            <label>
              Buscar cliente por nome
              <input
                value={customerSearch}
                onChange={(event) => setCustomerSearch(event.target.value)}
                maxLength={200}
              />
            </label>
            <label>
              Cliente
              <select
                aria-label="Cliente"
                required
                value={draft.customer_id}
                disabled={Boolean(initial)}
                onChange={(event) =>
                  updateDraft({ customer_id: event.target.value })
                }
              >
                <option value="">Selecione um cliente</option>
                {initial &&
                  !customers.some(
                    (customer) => customer.id === initial.customer_id,
                  ) && (
                    <option value={initial.customer_id}>
                      Cliente vinculado
                    </option>
                  )}
                {customers.map((customer) => (
                  <option key={customer.id} value={customer.id}>
                    {customer.name}
                  </option>
                ))}
              </select>
            </label>
            {Object.entries(dateLabels).map(([key, label]) => (
              <label key={key}>
                {label}
                <input
                  type="date"
                  required
                  value={draft[key as keyof typeof dateLabels]}
                  onChange={(event) =>
                    updateDraft({ [key]: event.target.value })
                  }
                />
              </label>
            ))}
            {(['pickup_time', 'event_time', 'return_time'] as const).map(
              (key, index) => (
                <label key={key}>
                  {
                    [
                      'Horário da retirada (opcional)',
                      'Horário do evento (opcional)',
                      'Horário da devolução (opcional)',
                    ][index]
                  }
                  <input
                    type="time"
                    value={draft[key] ?? ''}
                    onChange={(event) =>
                      updateDraft({ [key]: event.target.value || null })
                    }
                  />
                </label>
              ),
            )}
          </div>
        </fieldset>
        <fieldset disabled={busy || uncertain}>
          <legend>Itens comerciais</legend>
          <div className="catalog-form-grid">
            <label>
              Buscar no catálogo
              <input
                value={sourceSearch}
                onChange={(event) => setSourceSearch(event.target.value)}
                maxLength={200}
              />
            </label>
            <label>
              Tipo de item
              <select
                aria-label="Tipo de item"
                value={kind}
                onChange={(event) => {
                  setKind(event.target.value as 'product' | 'kit');
                  setSource('');
                }}
              >
                <option value="kit">Kit</option>
                <option value="product">Produto avulso</option>
              </select>
            </label>
            <label>
              Item do catálogo
              <select
                aria-label="Item do catálogo"
                value={source}
                onChange={(event) => setSource(event.target.value)}
              >
                <option value="">Selecione um item ativo</option>
                {(kind === 'kit' ? kits : products)
                  .filter(
                    (item) =>
                      item.is_active &&
                      !('needs_review' in item && item.needs_review),
                  )
                  .map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
              </select>
            </label>
          </div>
          <button
            type="button"
            className="auth-retry"
            disabled={!source || lines.length >= 1000}
            onClick={addLine}
          >
            Adicionar item
          </button>
          <p>
            Até 100 resultados por busca; refine o nome para localizar outros
            itens. Kits têm preço próprio.
          </p>
          {lines.length === 0 && (
            <p>Adicione ao menos um kit ou produto avulso.</p>
          )}
          {lines.map((line, index) => (
            <section
              className="quotation-line"
              key={line.key}
              aria-label={`Linha ${index + 1}`}
            >
              <h3>
                {index + 1}. {line.label}
              </h3>
              <div className="catalog-form-grid">
                <label>
                  Quantidade
                  <input
                    type="number"
                    min={1}
                    max={2147483647}
                    required
                    step={1}
                    value={line.quantity}
                    onChange={(event) =>
                      updateLine(index, {
                        quantity: Number(event.target.value),
                      })
                    }
                  />
                </label>
                <label className="quotation-checkbox">
                  <input
                    type="checkbox"
                    checked={line.custom}
                    onChange={(event) =>
                      updateLine(index, { custom: event.target.checked })
                    }
                  />
                  Negociar preço / composição
                </label>
              </div>
              {line.custom && (
                <div className="catalog-form-grid">
                  <label>
                    Preço unitário acordado (R$)
                    <input
                      required
                      inputMode="decimal"
                      value={line.price}
                      pattern="[0-9]+([.][0-9]{1,2})?"
                      onChange={(event) =>
                        updateLine(index, { price: event.target.value })
                      }
                    />
                  </label>
                  <label>
                    Motivo do preço / composição
                    <textarea
                      aria-label="Motivo do preço / composição"
                      required
                      maxLength={4000}
                      value={line.reason}
                      onChange={(event) =>
                        updateLine(index, { reason: event.target.value })
                      }
                    />
                  </label>
                </div>
              )}
              {line.kind === 'kit' && (
                <div>
                  <h4>Composição efetiva</h4>
                  {line.customItems.map((item, itemIndex) => (
                    <div
                      className="quotation-component"
                      key={`${item.product_id}-${itemIndex}`}
                    >
                      <span>
                        {products.find(
                          (product) => product.id === item.product_id,
                        )?.name ??
                          initial?.lines
                            .flatMap((entry) => entry.items)
                            .find(
                              (entry) => entry.product_id === item.product_id,
                            )?.name ??
                          'Produto do catálogo'}
                      </span>
                      {line.custom ? (
                        <>
                          <label>
                            Quantidade do componente {itemIndex + 1}
                            <input
                              type="number"
                              required
                              min={1}
                              max={2147483647}
                              step={1}
                              value={item.quantity}
                              onChange={(event) =>
                                updateLine(index, {
                                  customItems: line.customItems.map(
                                    (component, i) =>
                                      i === itemIndex
                                        ? {
                                            ...component,
                                            quantity: Number(
                                              event.target.value,
                                            ),
                                          }
                                        : component,
                                  ),
                                })
                              }
                            />
                          </label>
                          <button
                            type="button"
                            className="auth-retry"
                            onClick={() =>
                              updateLine(index, {
                                customItems: line.customItems.filter(
                                  (_, i) => i !== itemIndex,
                                ),
                              })
                            }
                          >
                            Remover componente {itemIndex + 1}
                          </button>
                        </>
                      ) : (
                        <span>Quantidade {item.quantity}</span>
                      )}
                    </div>
                  ))}
                  {line.custom && (
                    <label>
                      Adicionar componente
                      <select
                        aria-label="Adicionar componente"
                        value=""
                        onChange={(event) => {
                          if (event.target.value)
                            updateLine(index, {
                              customItems: [
                                ...line.customItems,
                                { product_id: event.target.value, quantity: 1 },
                              ],
                            });
                        }}
                      >
                        <option value="">Selecione produto ativo</option>
                        {products
                          .filter(
                            (product) =>
                              product.is_active &&
                              !line.customItems.some(
                                (item) => item.product_id === product.id,
                              ),
                          )
                          .map((product) => (
                            <option key={product.id} value={product.id}>
                              {product.name}
                            </option>
                          ))}
                      </select>
                    </label>
                  )}
                </div>
              )}
              <div className="catalog-actions">
                <button
                  type="button"
                  className="auth-retry"
                  onClick={() => {
                    changed();
                    setLines((value) => value.filter((_, i) => i !== index));
                  }}
                >
                  Remover linha {index + 1}
                </button>
                {line.retained_line_id && (
                  <button
                    type="button"
                    className="auth-retry"
                    disabled={
                      loading ||
                      !(line.kind === 'kit' ? kits : products).some(
                        (item) => item.id === line.source_id,
                      )
                    }
                    onClick={() => {
                      const record = (
                        line.kind === 'kit' ? kits : products
                      ).find((item) => item.id === line.source_id);
                      if (record)
                        updateLine(index, {
                          retained_line_id: undefined,
                          custom: false,
                          price: record.price,
                          customItems:
                            'items' in record
                              ? record.items.map((item) => ({
                                  product_id: item.product_id,
                                  quantity: item.quantity,
                                }))
                              : [],
                          reason: '',
                        });
                    }}
                  >
                    Usar valores atuais do catálogo
                  </button>
                )}
              </div>
            </section>
          ))}
        </fieldset>
        <fieldset disabled={busy || uncertain}>
          <legend>Desconto único</legend>
          <div className="catalog-form-grid">
            <label>
              Tipo de desconto
              <select
                aria-label="Tipo de desconto"
                value={draft.discount?.kind ?? ''}
                onChange={(event) =>
                  updateDraft({
                    discount: event.target.value
                      ? {
                          kind: event.target.value as 'amount' | 'percent',
                          value: '0.00',
                          reason: null,
                        }
                      : null,
                  })
                }
              >
                <option value="">Sem desconto</option>
                <option value="amount">Em reais</option>
                <option value="percent">Percentual</option>
              </select>
            </label>
            {draft.discount && (
              <>
                <label>
                  Valor do desconto
                  <input
                    required
                    inputMode="decimal"
                    pattern="[0-9]+([.][0-9]{1,2})?"
                    value={draft.discount.value}
                    onChange={(event) =>
                      updateDraft({
                        discount: {
                          ...draft.discount!,
                          value: event.target.value,
                        },
                      })
                    }
                  />
                </label>
                <label>
                  Motivo do desconto
                  <textarea
                    aria-label="Motivo do desconto"
                    maxLength={4000}
                    required={Number(draft.discount.value) > 0}
                    value={draft.discount.reason ?? ''}
                    onChange={(event) =>
                      updateDraft({
                        discount: {
                          ...draft.discount!,
                          reason: event.target.value || null,
                        },
                      })
                    }
                  />
                </label>
              </>
            )}
          </div>
          {initial && (
            <label>
              Motivo da nova revisão
              <textarea
                aria-label="Motivo da nova revisão"
                required
                maxLength={4000}
                value={versionReason}
                onChange={(event) => {
                  setVersionReason(event.target.value);
                  pending.current = null;
                }}
              />
            </label>
          )}
        </fieldset>
        <div className="catalog-actions">
          <button
            type="button"
            className="auth-retry"
            disabled={busy || uncertain}
            onClick={onCancel}
          >
            Cancelar edição
          </button>
          <button
            type="submit"
            className="auth-button"
            disabled={busy || uncertain || lines.length === 0}
          >
            {busy ? 'Aguarde…' : 'Calcular prévia'}
          </button>
        </div>
      </form>
      {preview && (
        <>
          <OfferSummary offer={preview} />
          <button
            type="button"
            className="auth-button"
            disabled={
              busy || uncertain || (Boolean(initial) && !versionReason.trim())
            }
            onClick={() => void save()}
          >
            {busy
              ? 'Salvando…'
              : initial
                ? 'Salvar nova revisão'
                : 'Salvar orçamento'}
          </button>
        </>
      )}
    </section>
  );
}
