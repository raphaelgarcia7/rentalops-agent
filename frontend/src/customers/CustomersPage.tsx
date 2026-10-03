import { useContext, useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { AuthContext } from '../authContext';
import { StatePanel } from '../components/StatePanel';
import { customerFeedback, customerRequest } from './api';
import type { CustomerDetail as Detail, CustomerPageData } from './api';
import { CustomerDetail } from './CustomerDetail';
import { CustomerEditor } from './CustomerEditor';
import '../catalog/catalog.css';
import './customers.css';

export function CustomersPage() {
  const { authenticated } = useContext(AuthContext);
  const [params, setParams] = useSearchParams();
  const identifier = params.get('cliente');
  const [mode, setMode] = useState<'list' | 'new' | 'detail' | 'edit'>('list');
  const [selected, setSelected] = useState<Detail | null>(null);
  const [data, setData] = useState<CustomerPageData | null>(null);
  const [search, setSearch] = useState('');
  const [kind, setKind] = useState<'name' | 'phone' | 'cpf'>('name');
  const [query, setQuery] = useState({ name: '' });
  const [page, setPage] = useState(1);
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [opening, setOpening] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const newButton = useRef<HTMLButtonElement>(null);
  const generation = useRef(0);
  const loadedIdentifier = useRef<string | null>(null);
  useEffect(() => {
    if (!authenticated) return;
    const controller = new AbortController();
    queueMicrotask(() => {
      setLoading(true);
      setError('');
    });
    void customerRequest<CustomerPageData>(
      '/search',
      'POST',
      { ...query, page },
      controller.signal,
    )
      .then((result) => {
        if (!controller.signal.aborted) setData(result);
      })
      .catch((problem: unknown) => {
        if (!controller.signal.aborted) setError(customerFeedback(problem));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [authenticated, query, page, refresh]);
  useEffect(() => {
    if (
      !authenticated ||
      !identifier ||
      loadedIdentifier.current === identifier
    )
      return;
    const controller = new AbortController();
    const current = ++generation.current;
    queueMicrotask(() => {
      setOpening(true);
      setError('');
    });
    void customerRequest<Detail>(
      `/${encodeURIComponent(identifier)}`,
      'GET',
      undefined,
      controller.signal,
    )
      .then((result) => {
        if (!controller.signal.aborted && generation.current === current) {
          setSelected(result);
          setMode('detail');
          loadedIdentifier.current = identifier;
        }
      })
      .catch((problem: unknown) => {
        if (!controller.signal.aborted) setError(customerFeedback(problem));
      })
      .finally(() => {
        if (!controller.signal.aborted) setOpening(false);
      });
    return () => controller.abort();
  }, [authenticated, identifier]);
  function close() {
    generation.current++;
    loadedIdentifier.current = null;
    setParams({});
    setMode('list');
    setSelected(null);
    setNotice('');
    queueMicrotask(() => newButton.current?.focus());
  }
  function saved(record: Detail) {
    setSelected(record);
    setMode('detail');
    setNotice('Cliente salvo com sucesso.');
    setRefresh((value) => value + 1);
  }
  return (
    <div className="catalog-workspace customer-workspace">
      <header className="page-heading">
        <span className="section-kicker">SUA LOCADORA · RELACIONAMENTOS</span>
        <h1>Clientes</h1>
        <p>
          Comece pelo contato. Complete os detalhes conforme o atendimento
          avança.
        </p>
        <Link className="catalog-back" to="/">
          Voltar à visão geral
        </Link>
      </header>
      {notice && (
        <p className="auth-feedback" role="status">
          {notice}
        </p>
      )}
      {mode === 'new' || mode === 'edit' ? (
        <CustomerEditor
          key={`${mode}-${selected?.id ?? 'new'}`}
          initial={mode === 'edit' && selected ? selected : undefined}
          onSaved={saved}
          onCancel={() => (selected ? setMode('detail') : close())}
        />
      ) : mode === 'detail' && selected ? (
        <CustomerDetail
          record={selected}
          onEdit={() => {
            setMode('edit');
            setNotice('');
          }}
          onClose={close}
        />
      ) : (
        <>
          <div className="catalog-toolbar">
            <p className="catalog-help">
              Pessoas físicas · documentação opcional no primeiro contato
            </p>
            <button
              className="auth-button"
              ref={newButton}
              disabled={opening}
              onClick={() => {
                setParams({});
                setSelected(null);
                setNotice('');
                setMode('new');
              }}
            >
              Novo cliente
            </button>
          </div>
          <form
            className="catalog-search"
            role="search"
            onSubmit={(event) => {
              event.preventDefault();
              setPage(1);
              setQuery({ name: '', [kind]: search.trim() });
              setRefresh((value) => value + 1);
            }}
          >
            <label>
              <span id="customer-search-label">Buscar por</span>
              <select
                aria-labelledby="customer-search-label"
                value={kind}
                onChange={(event) => {
                  setKind(event.target.value as typeof kind);
                  setSearch('');
                }}
              >
                <option value="name">Nome</option>
                <option value="phone">Telefone</option>
                <option value="cpf">CPF</option>
              </select>
            </label>
            <label>
              Busca
              <input
                autoComplete="off"
                maxLength={kind === 'name' ? 200 : 50}
                type={kind === 'phone' ? 'tel' : 'text'}
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </label>
            <button className="auth-retry" disabled={opening}>
              Buscar
            </button>
          </form>
          {opening && <p role="status">Abrindo cliente…</p>}
          {loading ? (
            <StatePanel
              icon="users"
              title="Carregando clientes…"
              description="Consultando os cadastros da locadora."
              showReturnLink={false}
            />
          ) : error ? (
            <>
              <p className="auth-feedback auth-feedback--error" role="alert">
                {error}
              </p>
              <button
                className="auth-retry"
                onClick={() => setRefresh((value) => value + 1)}
              >
                Tentar novamente
              </button>
            </>
          ) : !data?.items.length ? (
            <StatePanel
              icon="users"
              title={
                Object.values(query).some(Boolean)
                  ? 'Nenhum cliente encontrado'
                  : 'Seu primeiro contato começa aqui'
              }
              description="Cadastre nome e telefone. Você pode completar os detalhes depois."
              showReturnLink={false}
            />
          ) : (
            <>
              <p className="catalog-result-count">
                {data.total} cliente(s) · Página {page}
              </p>
              <ul className="catalog-grid">
                {data.items.map((record) => (
                  <li className="catalog-card" key={record.id}>
                    <span className="catalog-badge">Pessoa física</span>
                    <h2>{record.name}</h2>
                    <p className="customer-contact">{record.phone}</p>
                    <button
                      className="auth-retry"
                      disabled={opening}
                      aria-label={`Abrir ${record.name}`}
                      onClick={() => {
                        setNotice('');
                        setParams({ cliente: record.id });
                      }}
                    >
                      Consultar cliente <span aria-hidden="true">→</span>
                    </button>
                  </li>
                ))}
              </ul>
              <div className="catalog-pagination">
                <button
                  className="auth-retry"
                  disabled={page === 1 || opening}
                  onClick={() => setPage(page - 1)}
                >
                  Anterior
                </button>
                <span>
                  Página {page} de {Math.ceil(data.total / data.page_size)}
                </span>
                <button
                  className="auth-retry"
                  disabled={page * data.page_size >= data.total || opening}
                  onClick={() => setPage(page + 1)}
                >
                  Próxima
                </button>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
