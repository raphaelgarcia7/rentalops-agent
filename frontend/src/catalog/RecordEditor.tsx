import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { CatalogError, catalogRequest, feedback, priceLabel } from './api';
import { HistoryValue } from './RecordDetail';
import type { CatalogDetail, CatalogPage, KitItem, Kind, Product } from './api';

export function RecordEditor({
  kind,
  initial,
  onSaved,
  onCancel,
}: {
  kind: Kind;
  initial?: CatalogDetail;
  onSaved: (record: CatalogDetail) => void;
  onCancel: () => void;
}) {
  const product = initial && 'total_quantity' in initial ? initial : undefined;
  const [name, setName] = useState(initial?.name ?? '');
  const [price, setPrice] = useState(initial?.price.replace('.', ',') ?? '');
  const [quantity, setQuantity] = useState('0');
  const [optional, setOptional] = useState({
    description: product?.description ?? '',
    category: product?.category ?? '',
    color: product?.color ?? '',
    dimensions: product?.dimensions ?? '',
    replacement_value: product?.replacement_value?.replace('.', ',') ?? '',
    observation: product?.observation ?? '',
  });
  const [items, setItems] = useState<KitItem[]>(
    initial && 'items' in initial ? initial.items : [],
  );
  const [version, setVersion] = useState(initial?.version);
  const [current, setCurrent] = useState<CatalogDetail | null>(null);
  const [conflict, setConflict] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      kind === 'kits' &&
      (!items.length || items.some((item) => !item.is_active))
    ) {
      setError(
        'Adicione ao menos um produto ativo. Remova ou substitua componentes inativos. Kits não podem conter outros kits.',
      );
      return;
    }
    setBusy(true);
    setError('');
    const body =
      kind === 'products'
        ? {
            name,
            price: price.replace(',', '.'),
            ...Object.fromEntries(
              Object.entries(optional).map(([key, value]) => [
                key,
                value.trim()
                  ? key === 'replacement_value'
                    ? value.replace(',', '.')
                    : value
                  : null,
              ]),
            ),
            ...(initial
              ? { expected_version: version }
              : { initial_quantity: Number(quantity) }),
          }
        : {
            name,
            price: price.replace(',', '.'),
            items: items.map((item) => ({
              product_id: item.product_id,
              quantity: item.quantity,
            })),
            ...(initial ? { expected_version: version } : {}),
          };
    try {
      const record = await catalogRequest<CatalogDetail>(
        initial ? `${kind}/${initial.id}` : kind,
        { method: initial ? 'PATCH' : 'POST', body },
      );
      onSaved(record);
    } catch (failure) {
      setError(feedback(failure));
      setConflict(
        failure instanceof CatalogError &&
          failure.status === 409 &&
          Boolean(initial),
      );
    } finally {
      setBusy(false);
    }
  }

  async function consultCurrent() {
    if (!initial) return;
    setBusy(true);
    try {
      setCurrent(await catalogRequest<CatalogDetail>(`${kind}/${initial.id}`));
    } catch (failure) {
      setError(feedback(failure));
    } finally {
      setBusy(false);
    }
  }

  const optionalLabels = {
    description: 'Descrição',
    category: 'Categoria',
    color: 'Cor',
    dimensions: 'Medidas',
    replacement_value: 'Valor de reposição (R$)',
    observation: 'Observação',
  };

  return (
    <section className="catalog-panel" aria-labelledby="editor-heading">
      <div className="catalog-panel-heading">
        <div>
          <span className="section-kicker">
            {initial ? 'EDITAR CADASTRO' : 'CADASTRO PROGRESSIVO'}
          </span>
          <h2 id="editor-heading" ref={heading} tabIndex={-1}>
            {initial
              ? `Editar ${initial.name}`
              : kind === 'products'
                ? 'Novo produto'
                : 'Novo kit'}
          </h2>
        </div>
        <button className="auth-retry" onClick={onCancel} disabled={busy}>
          Cancelar
        </button>
      </div>
      <p className="catalog-help">
        {kind === 'products'
          ? 'Cadastre a unidade completa. Cores ou tamanhos com estoques distintos devem ser produtos separados.'
          : 'Defina o preço comercial do kit. Ele usa o estoque dos produtos e aceita somente produtos, nunca outros kits.'}
      </p>
      {error && (
        <p role="alert" className="auth-feedback auth-feedback--error">
          {error}
        </p>
      )}
      {conflict && (
        <div className="catalog-conflict">
          <p>
            Seu rascunho continua nos campos abaixo. Confira o cadastro antes de
            salvar novamente.
          </p>
          <button
            className="auth-retry"
            type="button"
            disabled={busy}
            onClick={() => void consultCurrent()}
          >
            Consultar versão atual
          </button>
          {current && (
            <>
              <p>
                Versão atual {current.version}: {current.name} ·{' '}
                {priceLabel(current.price)}.
              </p>
              <details>
                <summary>Ver dados atuais e histórico</summary>
                {Object.entries(current)
                  .filter(([key]) =>
                    [
                      'name',
                      'price',
                      'description',
                      'category',
                      'color',
                      'dimensions',
                      'replacement_value',
                      'observation',
                      'total_quantity',
                      'maintenance_quantity',
                      'is_active',
                      'items',
                    ].includes(key),
                  )
                  .map(([key, value]) => (
                    <HistoryValue key={key} name={key} value={value} />
                  ))}
                {current.history.map((entry) => (
                  <p key={entry.id} className="catalog-help">
                    {entry.reason} ·{' '}
                    {new Date(entry.created_at).toLocaleString('pt-BR')}
                  </p>
                ))}
              </details>
              <button
                type="button"
                className="auth-retry"
                onClick={() => {
                  setVersion(current.version);
                  setConflict(false);
                  setError('');
                }}
              >
                Revisar e usar esta versão
              </button>
            </>
          )}
        </div>
      )}
      <form
        className="catalog-form"
        onSubmit={(event) => void submit(event)}
        aria-busy={busy}
      >
        <fieldset disabled={busy}>
          <legend className="sr-only">Dados do cadastro</legend>
          <div className="catalog-form-grid">
            <label>
              Nome
              <input
                required
                maxLength={200}
                value={name}
                onChange={(event) => setName(event.target.value)}
                autoComplete="off"
              />
            </label>
            <label>
              Preço por locação (R$)
              <input
                required
                inputMode="decimal"
                pattern="[0-9]+([.,][0-9]{1,2})?"
                maxLength={13}
                placeholder="0,00"
                value={price}
                onChange={(event) => setPrice(event.target.value)}
              />
            </label>
            {kind === 'products' && !initial && (
              <label>
                Quantidade inicial
                <input
                  type="number"
                  required
                  min={0}
                  max={2147483647}
                  step={1}
                  value={quantity}
                  onChange={(event) => setQuantity(event.target.value)}
                />
              </label>
            )}
          </div>
          {kind === 'products' ? (
            <>
              {initial && (
                <p className="catalog-help">
                  Para mudar o saldo, use Ajustar estoque com motivo e
                  histórico.
                </p>
              )}
              <details className="catalog-optionals">
                <summary>Mais detalhes (opcionais)</summary>
                <div className="catalog-form-grid">
                  {Object.entries(optionalLabels).map(([key, label]) => {
                    const field = key as keyof typeof optional;
                    const long =
                      field === 'description' || field === 'observation';
                    return (
                      <label key={key}>
                        {label}
                        {long ? (
                          <textarea
                            rows={3}
                            maxLength={4000}
                            value={optional[field]}
                            onChange={(event) =>
                              setOptional({
                                ...optional,
                                [field]: event.target.value,
                              })
                            }
                          />
                        ) : (
                          <input
                            inputMode={
                              field === 'replacement_value' ? 'decimal' : 'text'
                            }
                            pattern={
                              field === 'replacement_value'
                                ? '[0-9]+([.,][0-9]{1,2})?'
                                : undefined
                            }
                            maxLength={
                              field === 'replacement_value'
                                ? 13
                                : field === 'dimensions'
                                  ? 200
                                  : 100
                            }
                            value={optional[field]}
                            onChange={(event) =>
                              setOptional({
                                ...optional,
                                [field]: event.target.value,
                              })
                            }
                          />
                        )}
                      </label>
                    );
                  })}
                </div>
              </details>
            </>
          ) : (
            <KitComposer items={items} onChange={setItems} />
          )}
        </fieldset>
        <div className="catalog-actions">
          <button
            className="auth-button"
            disabled={busy || conflict}
            type="submit"
          >
            {busy ? 'Salvando…' : 'Salvar cadastro'}
          </button>
          <p className="catalog-help">
            {initial
              ? `Edição da versão ${version}.`
              : kind === 'products'
                ? 'Fotos e detalhes podem ser incluídos depois.'
                : 'Composição e preço definidos pela equipe.'}
          </p>
        </div>
      </form>
    </section>
  );
}

function KitComposer({
  items,
  onChange,
}: {
  items: KitItem[];
  onChange: (items: KitItem[]) => void;
}) {
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [data, setData] = useState<CatalogPage<Product> | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() => {
      setLoading(true);
      setError('');
    });
    void catalogRequest<CatalogPage<Product>>(
      `products?search=${encodeURIComponent(query)}&page=${page}`,
      undefined,
      controller.signal,
    )
      .then(setData)
      .catch((failure: unknown) => {
        if (!controller.signal.aborted) setError(feedback(failure));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [query, page]);
  return (
    <section className="kit-composer" aria-labelledby="composition-heading">
      <h3 id="composition-heading">Composição do kit</h3>
      <p className="catalog-help">
        Somente produtos ativos. Quantidade mínima de 1; produtos repetidos são
        somados. O preço do kit é definido acima.
      </p>
      {items.length ? (
        <ul className="catalog-composition">
          {items.map((item) => (
            <li key={item.product_id}>
              <div>
                <strong>{item.name}</strong>
                {!item.is_active && (
                  <span className="catalog-badge catalog-badge--warning">
                    Inativo · substitua ou remova
                  </span>
                )}
              </div>
              <label>
                Quantidade de {item.name}
                <input
                  type="number"
                  required
                  min={1}
                  max={2147483647}
                  step={1}
                  value={item.quantity || ''}
                  onChange={(event) =>
                    onChange(
                      items.map((row) =>
                        row.product_id === item.product_id
                          ? { ...row, quantity: Number(event.target.value) }
                          : row,
                      ),
                    )
                  }
                />
              </label>
              <button
                type="button"
                className="auth-retry"
                onClick={() =>
                  onChange(
                    items.filter((row) => row.product_id !== item.product_id),
                  )
                }
                aria-label={`Remover ${item.name}`}
              >
                Remover
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p>Nenhum componente. Adicione um produto abaixo.</p>
      )}
      <div className="catalog-search">
        <label>
          Buscar produto para o kit
          <input
            value={search}
            maxLength={200}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
        <button
          className="auth-retry"
          type="button"
          onClick={() => {
            setPage(1);
            setQuery(search);
          }}
        >
          Buscar produtos
        </button>
      </div>
      {loading ? (
        <p role="status">Carregando produtos…</p>
      ) : error ? (
        <p role="alert" className="auth-feedback auth-feedback--error">
          {error}
        </p>
      ) : (
        <>
          <ul className="catalog-picker">
            {data?.items
              .filter((item) => item.is_active)
              .map((item) => (
                <li key={item.id}>
                  <span>
                    {item.name}{' '}
                    <small>{priceLabel(item.price)} por locação</small>
                  </span>
                  <button
                    type="button"
                    className="auth-retry"
                    onClick={() => {
                      const existing = items.find(
                        (row) => row.product_id === item.id,
                      );
                      onChange(
                        existing
                          ? items.map((row) =>
                              row.product_id === item.id
                                ? { ...row, quantity: row.quantity + 1 }
                                : row,
                            )
                          : [
                              ...items,
                              {
                                product_id: item.id,
                                name: item.name,
                                quantity: 1,
                                is_active: true,
                              },
                            ],
                      );
                    }}
                    aria-label={`Adicionar ${item.name}`}
                  >
                    Adicionar
                  </button>
                </li>
              ))}
          </ul>
          {!data?.items.some((item) => item.is_active) && (
            <p>
              Nenhum produto ativo nesta página. Cadastre produtos ou ajuste a
              busca.
            </p>
          )}
          {data && data.total > 25 && (
            <div className="catalog-actions">
              <button
                type="button"
                className="auth-retry"
                disabled={page === 1}
                onClick={() => setPage(page - 1)}
              >
                Produtos anteriores
              </button>
              <span>Página {page}</span>
              <button
                type="button"
                className="auth-retry"
                disabled={page * 25 >= data.total}
                onClick={() => setPage(page + 1)}
              >
                Próximos produtos
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
