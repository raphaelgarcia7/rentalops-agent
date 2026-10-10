import { useContext, useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { AuthContext } from '../authContext';
import { catalogRequest, priceLabel } from '../catalog/api';
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
import { rentalRequest } from '../rentals/api';
import type { ChangePreview, RentalRevision, Rental } from '../rentals/api';
import { paymentRequest } from '../payments/api';
import type { Payments } from '../payments/api';

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
  rentalRevision,
  copyFrom,
}: {
  initial?: Quotation;
  onSaved: (value: Quotation) => void;
  onCancel: () => void;
  rentalRevision?: RentalRevision;
  copyFrom?: Quotation;
}) {
  const { authenticated } = useContext(AuthContext);
  const [draft, setDraft] = useState(() => {
    if (!copyFrom) return draftOf(initial);
    const { quotation_id, expected_version, ...value } = draftOf(copyFrom);
    void quotation_id;
    void expected_version;
    return {
      ...value,
      discount: null,
      lines: value.lines.map(({ kind, source_id, quantity }) => ({
        kind,
        source_id,
        quantity,
      })),
    };
  });
  const [lines, setLines] = useState<PickedLine[]>(
    () =>
      (initial ?? copyFrom)?.lines.map((line) => ({
        ...(initial
          ? draftOf(initial).lines.find(
              (entry) => entry.retained_line_id === line.id,
            )!
          : {
              kind: line.kind,
              source_id: line.source_id,
              quantity: line.quantity,
            }),
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
  const [changePreview, setChangePreview] = useState<ChangePreview | null>(
    null,
  );
  const [reviewed, setReviewed] = useState(false);
  const [applications, setApplications] = useState(
    () =>
      rentalRevision?.financial.receipts.map((receipt) => ({
        receipt_id: receipt.id,
        deposit: receipt.applied_deposit,
        balance: receipt.applied_balance,
      })) ?? [],
  );
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [versionReason, setVersionReason] = useState('');
  const [current, setCurrent] = useState<Quotation | null>(null);
  const [revisionState, setRevisionState] = useState(rentalRevision);
  const [conflictingRevision, setConflictingRevision] =
    useState<RentalRevision | null>(null);
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
    setChangePreview(null);
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
  async function loadConflict() {
    if (!initial) return;
    const current = await quotationRequest<Quotation>(`/${initial.id}`);
    if (revisionState) {
      const financial = await paymentRequest<Payments>(initial.id);
      const rental = revisionState.id
        ? await rentalRequest<Rental>(`/${revisionState.id}`)
        : null;
      setConflictingRevision({
        ...revisionState,
        expected_rental_version: rental?.version ?? 0,
        expected_quotation_version: current.current_version,
        expected_financial_version: financial.financial_version,
        financial,
      });
    }
    setCurrent(current);
  }
  async function calculate(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      if (rentalRevision) {
        const { id, mode, financial, ...versions } = revisionState!;
        void mode;
        void financial;
        const body = { ...versions, draft: payload() };
        const value = id
          ? await rentalRequest<ChangePreview>(
              `/${id}/change-preview`,
              undefined,
              body,
            )
          : await quotationRequest<ChangePreview>(
              `/${initial!.id}/resumption-preview`,
              body,
            );
        setChangePreview(value);
        setPreview(value.after);
      } else setPreview(await quotationRequest<Offer>('/preview', payload()));
    } catch (problem) {
      setError(quotationFeedback(problem));
      if (
        problem instanceof QuotationError &&
        problem.status === 409 &&
        initial
      ) {
        try {
          await loadConflict();
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
    const standard = {
      ...payload(),
      request_id: crypto.randomUUID(),
      catalog_versions: preview!.catalog_versions,
      reason: initial ? versionReason : null,
    };
    const { id, mode, financial, ...versions } = revisionState ?? {};
    void financial;
    const body =
      pending.current ??
      (rentalRevision
        ? {
            ...versions,
            draft: payload(),
            request_id: standard.request_id,
            reason: versionReason,
            catalog_versions: standard.catalog_versions,
            ...(mode === 'resume'
              ? { payments_reviewed: reviewed, applications }
              : {}),
          }
        : standard);
    pending.current = body;
    try {
      let saved: Quotation;
      if (rentalRevision) {
        if (id)
          await rentalRequest<Rental>(
            `/${id}/${mode === 'resume' ? 'resumptions' : 'changes'}`,
            undefined,
            body,
          );
        else
          await quotationRequest<Rental>(`/${initial!.id}/resumptions`, body);
        saved = await quotationRequest<Quotation>(`/${initial!.id}`);
      } else
        saved = await quotationRequest<Quotation>(
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
        problem.status < 500 &&
        problem.status !== 401
      ) {
        pending.current = null;
        setUncertain(false);
        setPreview(null);
        if (problem.status === 409 && initial) {
          try {
            await loadConflict();
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
    if (conflictingRevision) {
      setRevisionState(conflictingRevision);
      setApplications(
        conflictingRevision.financial.receipts.map((receipt) => ({
          receipt_id: receipt.id,
          deposit: receipt.applied_deposit,
          balance: receipt.applied_balance,
        })),
      );
      setReviewed(false);
      setConflictingRevision(null);
    }
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
        {rentalRevision
          ? rentalRevision.mode === 'resume'
            ? 'Revisar e retomar locação'
            : 'Alterar aluguel do cliente'
          : initial
            ? 'Nova revisão do orçamento'
            : 'Novo orçamento'}
      </h2>
      <p>
        Preços por locação. Dados negociados ficam somente na memória desta
        tela. Datas e horários locais: São Paulo.
      </p>
      {copyFrom && (
        <p>
          Nova proposta baseada em locação concluída. Confira datas e preços
          atuais na prévia. Nenhum pagamento ou desconto anterior será
          transferido.
        </p>
      )}
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
          {conflictingRevision && (
            <p>
              Locação v{conflictingRevision.expected_rental_version} ·
              financeiro v{conflictingRevision.expected_financial_version} ·
              líquido {priceLabel(conflictingRevision.financial.net_received)}.
              Compare antes de refazer a prévia; a retomada exige conferir
              novamente os valores.
            </p>
          )}
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
        {rentalRevision?.mode === 'resume' && (
          <fieldset disabled={busy || uncertain}>
            <legend>Conferência dos valores líquidos existentes</legend>
            <p>
              A retomada preserva os recebimentos. Valores devolvidos não podem
              ser reaproveitados. O novo sinal precisa de uma única origem
              suficiente; confira também preços e datas.
            </p>
            {revisionState!.financial.receipts.length === 0 && (
              <p>
                Nenhum recebimento anterior. Retomar não confirma nem aloca
                estoque.
              </p>
            )}
            {revisionState!.financial.receipts.map((receipt, index) => (
              <div className="quotation-line" key={receipt.id}>
                <p>
                  Recebimento {index + 1} · líquido {priceLabel(receipt.net)} ·
                  devolvido
                  {priceLabel(receipt.refunded)}
                </p>
                <div className="catalog-form-grid">
                  {(['deposit', 'balance'] as const).map((key) => (
                    <label key={key}>
                      {key === 'deposit'
                        ? 'Aplicar ao sinal'
                        : 'Aplicar ao saldo'}{' '}
                      do recebimento {index + 1} (R$)
                      <input
                        required
                        inputMode="decimal"
                        pattern="[0-9]+[.][0-9]{2}"
                        value={applications[index][key]}
                        onChange={(event) => {
                          pending.current = null;
                          setApplications((values) =>
                            values.map((value, i) =>
                              i === index
                                ? { ...value, [key]: event.target.value }
                                : value,
                            ),
                          );
                        }}
                      />
                    </label>
                  ))}
                </div>
              </div>
            ))}
            <label className="quotation-checkbox">
              <input
                type="checkbox"
                required
                checked={reviewed}
                onChange={(event) => {
                  setReviewed(event.target.checked);
                  pending.current = null;
                }}
              />
              Conferi os preços, as datas e as aplicações dos valores líquidos
              desta revisão
            </label>
          </fieldset>
        )}
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
                maxLength={rentalRevision ? 1000 : 4000}
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
          {changePreview && (
            <section
              className="quotation-conflict"
              aria-label="Antes e depois da alteração"
            >
              <h3>Confira antes de gravar</h3>
              <p>
                Total anterior {priceLabel(changePreview.before.total)} → novo{' '}
                {priceLabel(changePreview.after.total)}
              </p>
              <p>
                Retirada {changePreview.before.pickup_date} →{' '}
                {changePreview.after.pickup_date} · devolução{' '}
                {changePreview.before.return_date} →{' '}
                {changePreview.after.return_date}
              </p>
              <ul>
                {changePreview.before.lines.map((line, index) => (
                  <li key={index}>
                    Antes: {line.quantity} × {line.name} ·{' '}
                    {priceLabel(line.unit_price)}
                    <ul>
                      {line.items.map((item) => (
                        <li key={item.product_id}>
                          {item.quantity} × {item.name}
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
              <ul>
                {changePreview.after.lines.map((line, index) => (
                  <li key={index}>
                    Depois: {line.quantity} × {line.name} ·{' '}
                    {priceLabel(line.unit_price)}
                    <ul>
                      {line.items.map((item) => (
                        <li key={item.product_id}>
                          {item.quantity} × {item.name}
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
              <p>
                Dinheiro líquido{' '}
                {priceLabel(changePreview.financial.net_received)} · saldo
                projetado {priceLabel(changePreview.financial.remaining)} ·
                excesso pendente {priceLabel(changePreview.financial.excess)}
              </p>
              <p>
                Sinal histórico{' '}
                {priceLabel(changePreview.financial.historical_deposit)}.
                Aumento após confirmação vai ao saldo; excesso exige decisão da
                equipe, sem devolução ou crédito automático.
              </p>
              <p>
                Estoque será validado novamente ao gravar.{' '}
                {rentalRevision?.mode === 'resume' &&
                  'Retomar volta à revisão e não aloca estoque.'}{' '}
                A nova revisão comercial exige nova assinatura quando contratos
                estiverem disponíveis.
              </p>
            </section>
          )}
          <OfferSummary
            offer={preview}
            financialTerms={
              changePreview
                ? {
                    deposit: changePreview.financial.deposit_due,
                    balance: changePreview.financial.balance_due,
                  }
                : undefined
            }
          />
          <button
            type="button"
            className="auth-button"
            disabled={
              busy ||
              uncertain ||
              (Boolean(initial) && !versionReason.trim()) ||
              (rentalRevision?.mode === 'resume' && !reviewed)
            }
            onClick={() => void save()}
          >
            {busy
              ? 'Salvando…'
              : rentalRevision
                ? rentalRevision.mode === 'resume'
                  ? 'Retomar em revisão'
                  : 'Confirmar alteração da locação'
                : initial
                  ? 'Salvar nova revisão'
                  : 'Salvar orçamento'}
          </button>
        </>
      )}
    </section>
  );
}
