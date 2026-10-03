import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import {
  catalogRequest,
  feedback,
  operationLabels,
  priceLabel,
  productDetail,
} from './api';
import type { CatalogDetail, Kind, Photo, ProductDetail } from './api';

type Action = {
  kind: 'stock' | 'maintenance' | 'release' | 'inactivate' | 'detach';
  target?: string;
};

export function RecordDetail({
  record,
  kind,
  onChange,
  onEdit,
  onClose,
}: {
  record: CatalogDetail;
  kind: Kind;
  onChange: (record: CatalogDetail) => void;
  onEdit: () => void;
  onClose: () => void;
}) {
  const [action, setAction] = useState<Action | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, []);
  const isProduct = productDetail(record);
  return (
    <section className="catalog-panel" aria-labelledby="detail-heading">
      <div className="catalog-panel-heading">
        <div>
          <span className="section-kicker">
            {isProduct ? 'PRODUTO COMPLETO' : 'KIT DE PRODUTOS'}
          </span>
          <h2 id="detail-heading" ref={heading} tabIndex={-1}>
            {record.name}
          </h2>
          <span className="catalog-badge">
            {record.is_active ? 'Ativo' : 'Inativo'}
          </span>
        </div>
        <button className="auth-retry" onClick={onClose}>
          Voltar à lista
        </button>
      </div>
      <p className="catalog-price">
        {priceLabel(record.price)} <span>por locação</span>
      </p>
      <div className="catalog-actions">
        <button className="auth-retry" onClick={onEdit}>
          {!isProduct && record.needs_review
            ? 'Revisar kit'
            : 'Editar cadastro'}
        </button>
        {isProduct && (
          <>
            <button
              className="auth-retry"
              onClick={() => setAction({ kind: 'stock' })}
            >
              Ajustar estoque
            </button>
            <button
              className="auth-retry"
              onClick={() => setAction({ kind: 'maintenance' })}
            >
              Registrar manutenção
            </button>
          </>
        )}
        {record.is_active && (
          <button
            className="auth-retry"
            onClick={() => setAction({ kind: 'inactivate' })}
          >
            Inativar {isProduct ? 'produto' : 'kit'}
          </button>
        )}
      </div>
      {action && (
        <CommandForm
          key={`${action.kind}-${action.target}`}
          action={action}
          record={record}
          kind={kind}
          onCancel={() => {
            setAction(null);
            heading.current?.focus();
          }}
          onSaved={(next) => {
            onChange(next);
            setAction(null);
            heading.current?.focus();
          }}
        />
      )}
      {isProduct ? (
        <>
          <dl className="catalog-stock">
            <div>
              <dt>Total cadastrado</dt>
              <dd>{record.total_quantity}</dd>
            </div>
            <div>
              <dt>Em manutenção</dt>
              <dd>{record.maintenance_quantity}</dd>
            </div>
            <div>
              <dt>Aptos à locação</dt>
              <dd>{record.apt_quantity}</dd>
            </div>
          </dl>
          <p className="catalog-help">
            Unidades aptas antes dos compromissos do período. Este saldo
            cadastral não garante disponibilidade para uma data.
          </p>
          <dl className="catalog-attributes">
            {(
              [
                ['Descrição', record.description],
                ['Categoria', record.category],
                ['Cor', record.color],
                ['Medidas', record.dimensions],
                [
                  'Reposição',
                  record.replacement_value
                    ? priceLabel(record.replacement_value)
                    : null,
                ],
                ['Observação', record.observation],
              ] as const
            )
              .filter(([, value]) => value)
              .map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
          </dl>
          <section
            className="catalog-section"
            aria-labelledby="maintenance-title"
          >
            <h3 id="maintenance-title">Manutenção e avarias</h3>
            {record.maintenance.some(
              (entry) => entry.quantity > entry.released_quantity,
            ) ? (
              <ul className="catalog-maintenance">
                {record.maintenance
                  .filter((entry) => entry.quantity > entry.released_quantity)
                  .map((entry) => (
                    <li key={entry.id}>
                      <div>
                        <strong>
                          {entry.quantity - entry.released_quantity} unidade(s)
                          pendente(s)
                        </strong>
                        <p>{entry.reason}</p>
                      </div>
                      <button
                        className="auth-retry"
                        onClick={() =>
                          setAction({ kind: 'release', target: entry.id })
                        }
                        aria-label={`Liberar manutenção: ${entry.reason}`}
                      >
                        Liberar unidades
                      </button>
                    </li>
                  ))}
              </ul>
            ) : (
              <p className="catalog-help">
                Nenhuma unidade aguardando liberação.
              </p>
            )}
          </section>
          <PhotoGallery
            record={record}
            onChange={onChange}
            onDetach={(target) => setAction({ kind: 'detach', target })}
          />
          <section className="catalog-section" aria-labelledby="stock-history">
            <h3 id="stock-history">Histórico de estoque</h3>
            <ol className="catalog-history">
              {record.movements.map((row) => (
                <li key={row.id}>
                  <div>
                    <strong>{operationLabels[row.operation]}</strong>
                    <time dateTime={row.created_at}>
                      {new Date(row.created_at).toLocaleString('pt-BR')}
                    </time>
                  </div>
                  <p>
                    {row.reason} · Quantidade: {row.quantity}
                  </p>
                  <p className="catalog-help">
                    Saldo após a ação: {row.total_after} total ·{' '}
                    {row.maintenance_after} em manutenção.
                  </p>
                  <details>
                    <summary>Responsável</summary>
                    <p className="catalog-help">
                      Identificação: {row.actor_id}
                    </p>
                  </details>
                </li>
              ))}
            </ol>
          </section>
        </>
      ) : (
        <section className="catalog-section" aria-labelledby="kit-items-title">
          <h3 id="kit-items-title">Composição do kit</h3>
          {record.needs_review && (
            <p className="auth-feedback auth-feedback--error">
              Kit precisa de revisão: remova ou substitua os produtos inativos.
              A composição foi preservada.
            </p>
          )}
          <p className="catalog-help">
            Kit sem estoque próprio. Seu preço comercial não é recalculado
            quando preços dos produtos mudam.
          </p>
          <ul className="catalog-composition">
            {record.items.map((item) => (
              <li key={item.product_id}>
                <strong>{item.name}</strong>
                <span>{item.quantity} unidade(s)</span>
                {!item.is_active && (
                  <span className="catalog-badge catalog-badge--warning">
                    Inativo · revisar
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
      <section className="catalog-section" aria-labelledby="catalog-history">
        <h3 id="catalog-history">Histórico cadastral</h3>
        <ol className="catalog-history">
          {record.history.map((row) => (
            <li key={row.id}>
              <div>
                <strong>
                  {operationLabels[row.operation] ?? row.operation}
                </strong>
                <time dateTime={row.created_at}>
                  {new Date(row.created_at).toLocaleString('pt-BR')}
                </time>
              </div>
              <p>{row.reason}</p>
              <details>
                <summary>Dados desta alteração</summary>
                <p className="catalog-help">Responsável: {row.actor_id}</p>
                {Object.entries(row.snapshot)
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
              </details>
            </li>
          ))}
        </ol>
        <p className="catalog-help">
          Versão {record.version} · As alterações preservam o histórico.
        </p>
      </section>
    </section>
  );
}

export function HistoryValue({
  name,
  value,
}: {
  name: string;
  value: unknown;
}) {
  const labels: Record<string, string> = {
    name: 'Nome',
    price: 'Preço',
    description: 'Descrição',
    category: 'Categoria',
    color: 'Cor',
    dimensions: 'Medidas',
    replacement_value: 'Reposição',
    observation: 'Observação',
    total_quantity: 'Total',
    maintenance_quantity: 'Manutenção',
    is_active: 'Ativo',
    items: 'Composição',
  };
  if (Array.isArray(value))
    return (
      <ul>
        {value.map((item: unknown, index) => {
          if (!item || typeof item !== 'object') return null;
          const fields = item as Record<string, unknown>;
          return (
            <li key={index}>
              {String(fields.name ?? 'Produto')} · {String(fields.quantity)}{' '}
              unidade(s)
            </li>
          );
        })}
      </ul>
    );
  if (value === null) return null;
  return (
    <p className="catalog-help">
      {labels[name]}:{' '}
      {typeof value === 'boolean' ? (value ? 'Sim' : 'Não') : String(value)}
    </p>
  );
}

function CommandForm({
  action,
  record,
  kind,
  onSaved,
  onCancel,
}: {
  action: Action;
  record: CatalogDetail;
  kind: Kind;
  onSaved: (record: CatalogDetail) => void;
  onCancel: () => void;
}) {
  const [operation, setOperation] = useState('entry');
  const [quantity, setQuantity] = useState('1');
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [version] = useState(record.version);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, []);
  const titles = {
    stock: 'Ajustar estoque',
    maintenance: 'Registrar manutenção',
    release: 'Liberar unidades',
    inactivate: 'Confirmar inativação',
    detach: 'Retirar foto da galeria',
  };
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError('');
    const route =
      action.kind === 'stock'
        ? 'stock-adjustments'
        : action.kind === 'maintenance'
          ? 'maintenance'
          : action.kind === 'release'
            ? `maintenance/${action.target}/release`
            : action.kind === 'detach'
              ? `photos/${action.target}/detach`
              : 'inactivate';
    try {
      onSaved(
        await catalogRequest<CatalogDetail>(`${kind}/${record.id}/${route}`, {
          method: 'POST',
          body: {
            expected_version: version,
            reason,
            ...(action.kind === 'stock'
              ? { operation, quantity: Number(quantity) }
              : action.kind === 'maintenance' || action.kind === 'release'
                ? { quantity: Number(quantity) }
                : {}),
          },
        }),
      );
    } catch (failure) {
      setError(feedback(failure));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="catalog-command" aria-labelledby="command-title">
      <h3 id="command-title" tabIndex={-1} ref={heading}>
        {titles[action.kind]}
      </h3>
      {action.kind === 'inactivate' && (
        <p>
          O cadastro ficará inativo. Identificação e histórico serão
          preservados.
          {kind === 'products' &&
            ' Kits com este produto precisarão de revisão.'}
        </p>
      )}
      {action.kind === 'detach' && (
        <p>
          A foto sairá da galeria; o arquivo e sua identificação serão
          preservados no histórico.
        </p>
      )}
      {error && (
        <p role="alert" className="auth-feedback auth-feedback--error">
          {error}
        </p>
      )}
      <form
        className="catalog-form"
        onSubmit={(event) => void submit(event)}
        aria-busy={busy}
      >
        <fieldset disabled={busy}>
          <legend className="sr-only">Confirmar operação</legend>
          {action.kind === 'stock' && (
            <label>
              Operação
              <select
                value={operation}
                onChange={(event) => setOperation(event.target.value)}
              >
                <option value="entry">Entrada — acrescentar unidades</option>
                <option value="withdrawal">Baixa — retirar unidades</option>
                <option value="correction">
                  Correção — definir total conferido
                </option>
              </select>
            </label>
          )}
          {!['inactivate', 'detach'].includes(action.kind) && (
            <label>
              {action.kind === 'stock' && operation === 'correction'
                ? 'Novo total conferido'
                : 'Quantidade da operação'}
              <input
                type="number"
                required
                step={1}
                min={
                  action.kind === 'stock' && operation === 'correction' ? 0 : 1
                }
                max={2147483647}
                value={quantity}
                onChange={(event) => setQuantity(event.target.value)}
              />
            </label>
          )}
          <label>
            Motivo
            <textarea
              required
              rows={2}
              maxLength={4000}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          </label>
        </fieldset>
        <div className="catalog-actions">
          <button className="auth-button" type="submit" disabled={busy}>
            {busy ? 'Confirmando…' : titles[action.kind]}
          </button>
          <button
            className="auth-retry"
            type="button"
            disabled={busy}
            onClick={onCancel}
          >
            Cancelar operação
          </button>
        </div>
      </form>
    </section>
  );
}

function PhotoGallery({
  record,
  onChange,
  onDetach,
}: {
  record: ProductDetail;
  onChange: (record: CatalogDetail) => void;
  onDetach: (id: string) => void;
}) {
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const picked = file.current?.files?.[0];
    if (!picked) {
      setError('Selecione uma foto JPEG, PNG ou WebP.');
      return;
    }
    if (picked.size > 10 * 1024 * 1024) {
      setError('Foto excede o limite de 10 MiB.');
      return;
    }
    setBusy(true);
    setError('');
    const body = new FormData();
    body.set('file', picked);
    body.set('expected_version', String(record.version));
    try {
      onChange(
        await catalogRequest<ProductDetail>(`products/${record.id}/photos`, {
          method: 'POST',
          body,
        }),
      );
      if (file.current) file.current.value = '';
    } catch (failure) {
      setError(feedback(failure));
    } finally {
      setBusy(false);
    }
  }
  async function edit(photo: Photo, principal: boolean, order: number) {
    setBusy(true);
    setError('');
    try {
      onChange(
        await catalogRequest<ProductDetail>(
          `products/${record.id}/photos/${photo.id}`,
          {
            method: 'PATCH',
            body: {
              expected_version: record.version,
              is_principal: principal,
              order,
            },
          },
        ),
      );
    } catch (failure) {
      setError(feedback(failure));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="catalog-section" aria-labelledby="photos-title">
      <h3 id="photos-title">Fotos do produto</h3>
      <p className="catalog-help">
        Fotos privadas e opcionais no cadastro. JPEG, PNG ou WebP; até 10 MiB e
        20 megapixels. A foto principal identifica o produto.
      </p>
      {!record.photos.length && (
        <p className="catalog-photo-empty">
          Sem foto. Adicione uma imagem real do produto quando estiver
          disponível.
        </p>
      )}
      {error && (
        <p role="alert" className="auth-feedback auth-feedback--error">
          {error}
        </p>
      )}
      <div className="catalog-gallery">
        {record.photos.map((photo, index) => (
          <div className="catalog-photo-card" key={photo.id}>
            <PhotoPreview photo={photo} name={record.name} />
            <span className="catalog-badge">
              {photo.is_principal ? 'Foto principal' : `Foto ${index + 1}`}
            </span>
            {!photo.is_principal && (
              <button
                className="auth-retry"
                disabled={busy}
                onClick={() => void edit(photo, true, photo.order)}
              >
                Usar como principal
              </button>
            )}
            <form
              className="catalog-photo-order"
              onSubmit={(event) => {
                event.preventDefault();
                const data = new FormData(event.currentTarget);
                void edit(photo, photo.is_principal, Number(data.get('order')));
              }}
            >
              <label>
                Ordem da foto {index + 1}
                <input
                  type="number"
                  name="order"
                  required
                  min={0}
                  max={2147483647}
                  step={1}
                  defaultValue={photo.order}
                />
              </label>
              <button className="auth-retry" disabled={busy}>
                Salvar ordem
              </button>
            </form>
            <button
              className="auth-retry"
              disabled={busy}
              onClick={() => onDetach(photo.id)}
            >
              Retirar da galeria
            </button>
          </div>
        ))}
      </div>
      <form
        className="catalog-form"
        onSubmit={(event) => void upload(event)}
        aria-busy={busy}
      >
        <label>
          Adicionar foto
          <input
            ref={file}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            disabled={busy}
          />
        </label>
        <button className="auth-button" type="submit" disabled={busy}>
          {busy ? 'Enviando foto…' : 'Enviar foto'}
        </button>
      </form>
    </section>
  );
}

function PhotoPreview({ photo, name }: { photo: Photo; name: string }) {
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [retry, setRetry] = useState(0);
  return (
    <div className="catalog-photo-preview">
      {state === 'loading' && <p role="status">Carregando foto…</p>}
      {state === 'error' && (
        <>
          <p role="alert">Não foi possível carregar esta foto.</p>
          <button
            className="auth-retry"
            onClick={() => {
              setState('loading');
              setRetry(retry + 1);
            }}
          >
            Tentar carregar foto
          </button>
        </>
      )}
      <img
        key={retry}
        src={`/api/photos/${photo.id}?retry=${retry}`}
        alt={`Foto de ${name}`}
        hidden={state !== 'ready'}
        onLoad={() => setState('ready')}
        onError={() => setState('error')}
      />
    </div>
  );
}
