import { useContext, useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { AuthContext } from '../authContext';
import { StatePanel } from '../components/StatePanel';
import { priceLabel } from '../catalog/api';
import { quotationFeedback, quotationLink, quotationRequest } from './api';
import type { Quotation, QuotationPage } from './api';
import { QuotationEditor } from './QuotationEditor';
import { QuotationDetail } from './QuotationDetail';
import '../catalog/catalog.css';
import './quotations.css';

export function QuotationsPage() {
  const { authenticated } = useContext(AuthContext);
  const [params, setParams] = useSearchParams();
  const identifier = params.get('orcamento');
  const [record, setRecord] = useState<Quotation | null>(null);
  const [mode, setMode] = useState<'list' | 'new' | 'detail' | 'edit'>('list');
  const [data, setData] = useState<QuotationPage | null>(null);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [query, setQuery] = useState<Record<string, string>>({});
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [refresh, setRefresh] = useState(0);
  const newButton = useRef<HTMLButtonElement>(null);
  const loaded = useRef<string | null>(null);
  useEffect(() => {
    if (!authenticated) return;
    const controller = new AbortController();
    queueMicrotask(() => {
      setLoading(true);
      setError('');
    });
    void quotationRequest<QuotationPage>(
      '/search',
      { ...query, page },
      controller.signal,
    )
      .then((value) => {
        if (!controller.signal.aborted) setData(value);
      })
      .catch((problem: unknown) => {
        if (!controller.signal.aborted) setError(quotationFeedback(problem));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [authenticated, query, page, refresh]);
  useEffect(() => {
    if (!authenticated || !identifier || loaded.current === identifier) return;
    const controller = new AbortController();
    void quotationRequest<Quotation>(
      `/${encodeURIComponent(identifier)}`,
      undefined,
      controller.signal,
    )
      .then((value) => {
        if (!controller.signal.aborted) {
          setRecord(value);
          setMode('detail');
          loaded.current = identifier;
        }
      })
      .catch((problem: unknown) => {
        if (!controller.signal.aborted) setError(quotationFeedback(problem));
      });
    return () => controller.abort();
  }, [authenticated, identifier]);
  function close() {
    setMode('list');
    setParams({});
    loaded.current = null;
    setRecord(null);
    setNotice('');
    queueMicrotask(() => newButton.current?.focus());
  }
  function saved(value: Quotation) {
    loaded.current = value.id;
    setParams({ orcamento: value.id });
    setRecord(value);
    setMode('detail');
    setNotice('Orçamento salvo com sucesso. Nenhum estoque foi reservado.');
    setRefresh((value) => value + 1);
  }
  async function edit() {
    if (!record) return;
    try {
      setRecord(await quotationRequest<Quotation>(`/${record.id}`));
      setMode('edit');
      setNotice('');
    } catch (problem) {
      setError(quotationFeedback(problem));
    }
  }
  return (
    <div className="catalog-workspace quotation-workspace">
      <header className="page-heading">
        <span className="section-kicker">SUA LOCADORA · PROPOSTAS</span>
        <h1>Locações</h1>
        <p>
          Orçamentos com acordo, pagamentos manuais e histórico. Confirmar
          reserva e alocar estoque são etapas posteriores.
        </p>
        <Link className="catalog-back" to="/">
          Voltar à visão geral
        </Link>
      </header>
      {notice && (
        <p role="status" className="auth-feedback">
          {notice}
        </p>
      )}
      {mode === 'new' || mode === 'edit' ? (
        <QuotationEditor
          key={mode === 'new' ? 'new' : record?.id}
          initial={mode === 'edit' ? (record ?? undefined) : undefined}
          onSaved={saved}
          onCancel={close}
        />
      ) : mode === 'detail' && record ? (
        <QuotationDetail
          key={`${record.id}-${record.version}`}
          record={record}
          onEdit={() => void edit()}
          onClose={close}
        />
      ) : (
        <>
          <div className="catalog-panel-heading">
            <h2>Orçamentos</h2>
            <button
              className="auth-button"
              ref={newButton}
              onClick={() => {
                setMode('new');
                setError('');
              }}
            >
              Novo orçamento
            </button>
          </div>
          <form
            className="catalog-panel quotation-search"
            onSubmit={(event) => {
              event.preventDefault();
              setQuery(
                Object.fromEntries(
                  Object.entries(filters).filter(([, value]) => value),
                ),
              );
              setPage(1);
            }}
          >
            <div className="catalog-form-grid">
              <label>
                ID do cliente
                <input
                  value={filters.customer_id ?? ''}
                  onChange={(event) =>
                    setFilters((value) => ({
                      ...value,
                      customer_id: event.target.value,
                    }))
                  }
                />
              </label>
              <label>
                ID do orçamento
                <input
                  value={filters.quotation_id ?? ''}
                  onChange={(event) =>
                    setFilters((value) => ({
                      ...value,
                      quotation_id: event.target.value,
                    }))
                  }
                />
              </label>
              <label>
                Estado comercial
                <select
                  value={filters.state ?? ''}
                  onChange={(event) =>
                    setFilters((value) => ({
                      ...value,
                      state: event.target.value,
                    }))
                  }
                >
                  <option value="">Todos</option>
                  <option value="current">Validade vigente</option>
                  <option value="expired">Vencido</option>
                </select>
              </label>
              {(
                [
                  'pickup_date',
                  'event_date',
                  'return_date',
                  'valid_until',
                ] as const
              ).map((key, index) => (
                <label key={key}>
                  {['Retirada', 'Evento', 'Devolução', 'Validade'][index]}
                  <input
                    type="date"
                    value={filters[key] ?? ''}
                    onChange={(event) =>
                      setFilters((value) => ({
                        ...value,
                        [key]: event.target.value,
                      }))
                    }
                  />
                </label>
              ))}
            </div>
            <button className="auth-retry" type="submit">
              Buscar orçamentos
            </button>
          </form>
          {loading ? (
            <p role="status">Carregando orçamentos…</p>
          ) : error ? (
            <div role="alert" className="auth-feedback">
              {error}
              <button
                className="auth-retry"
                onClick={() => setRefresh((value) => value + 1)}
              >
                Tentar novamente
              </button>
            </div>
          ) : data?.items.length ? (
            <>
              <p>
                {data.total} orçamento(s) · página {data.page}
              </p>
              <ul className="catalog-grid">
                {data.items.map((item) => (
                  <li className="catalog-card" key={item.id}>
                    <span className="catalog-badge">
                      Revisão {item.version} ·{' '}
                      {item.expired ? 'Vencido' : 'Validade vigente'}
                    </span>
                    <h3>Orçamento {item.id.slice(0, 8)}</h3>
                    <p className="catalog-price">{priceLabel(item.total)}</p>
                    <p>
                      Evento {item.event_date} · validade {item.valid_until}
                    </p>
                    {item.stock_pending && (
                      <p className="catalog-badge catalog-badge--warning">
                        Pendência de estoque cadastral
                      </p>
                    )}
                    <Link className="auth-retry" to={quotationLink(item.id)}>
                      Abrir orçamento
                    </Link>
                  </li>
                ))}
              </ul>
              <div className="catalog-actions">
                <button
                  className="auth-retry"
                  disabled={page === 1}
                  onClick={() => setPage((value) => value - 1)}
                >
                  Página anterior
                </button>
                <button
                  className="auth-retry"
                  disabled={page * data.page_size >= data.total}
                  onClick={() => setPage((value) => value + 1)}
                >
                  Próxima página
                </button>
              </div>
            </>
          ) : (
            <StatePanel
              icon="calendar"
              showReturnLink={false}
              title="Seu primeiro orçamento começa aqui"
              description="Selecione um cliente e prepare uma proposta. Orçamento não reserva estoque; agenda ainda não considerada."
            />
          )}
        </>
      )}
    </div>
  );
}
