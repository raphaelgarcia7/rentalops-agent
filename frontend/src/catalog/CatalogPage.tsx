import { useContext, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router';
import { AuthContext } from '../authContext';
import { StatePanel } from '../components/StatePanel';
import { catalogRequest, feedback, priceLabel, productRecord } from './api';
import type {
  CatalogDetail,
  CatalogPage as PageData,
  CatalogRecord,
  Kind,
} from './api';
import { RecordEditor } from './RecordEditor';
import { RecordDetail } from './RecordDetail';
import './catalog.css';

export function CatalogPage() {
  const { authenticated } = useContext(AuthContext);
  const [kind, setKind] = useState<Kind>('products');
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [refresh, setRefresh] = useState(0);
  const [data, setData] = useState<PageData<CatalogRecord> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [selected, setSelected] = useState<CatalogDetail | null>(null);
  const [mode, setMode] = useState<'list' | 'detail' | 'new' | 'edit'>('list');
  const [opening, setOpening] = useState(false);
  const newButton = useRef<HTMLButtonElement>(null);
  const selectionGeneration = useRef(0);

  useEffect(() => {
    if (!authenticated) return;
    const controller = new AbortController();
    queueMicrotask(() => {
      setLoading(true);
      setError('');
    });
    void catalogRequest<PageData<CatalogRecord>>(
      `${kind}?search=${encodeURIComponent(query)}&page=${page}`,
      undefined,
      controller.signal,
    )
      .then((next) => {
        if (!controller.signal.aborted) setData(next);
      })
      .catch((failure: unknown) => {
        if (!controller.signal.aborted) setError(feedback(failure));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [kind, query, page, refresh, authenticated]);

  async function open(record: CatalogRecord) {
    const generation = ++selectionGeneration.current;
    setOpening(true);
    setError('');
    setNotice('');
    try {
      const detail = await catalogRequest<CatalogDetail>(
        `${kind}/${record.id}`,
      );
      if (generation === selectionGeneration.current) {
        setSelected(detail);
        setMode('detail');
      }
    } catch (failure) {
      if (generation === selectionGeneration.current)
        setError(feedback(failure));
    } finally {
      if (generation === selectionGeneration.current) setOpening(false);
    }
  }

  function saved(record: CatalogDetail) {
    setSelected(record);
    setMode('detail');
    setNotice('Alteração salva com histórico.');
    setError('');
    setRefresh((value) => value + 1);
  }
  function close() {
    setMode('list');
    setSelected(null);
    setNotice('');
    queueMicrotask(() => newButton.current?.focus());
  }

  return (
    <div className="catalog-workspace">
      <header className="page-heading">
        <span className="section-kicker">SUA LOCADORA · ACERVO</span>
        <h1>Catálogo</h1>
        <p>Produtos completos, preços por locação e kits do seu acervo.</p>
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
        <RecordEditor
          key={`${kind}-${mode}-${selected?.id ?? 'new'}`}
          kind={kind}
          initial={mode === 'edit' && selected ? selected : undefined}
          onSaved={saved}
          onCancel={() => {
            if (selected) setMode('detail');
            else close();
          }}
        />
      ) : mode === 'detail' && selected ? (
        <RecordDetail
          key={selected.id}
          record={selected}
          kind={kind}
          onChange={saved}
          onEdit={() => {
            setMode('edit');
            setNotice('');
          }}
          onClose={close}
        />
      ) : (
        <>
          <div className="catalog-toolbar">
            <div
              className="catalog-switch"
              role="group"
              aria-label="Tipo de cadastro"
            >
              {(['products', 'kits'] as const).map((item) => (
                <button
                  className="auth-retry"
                  aria-pressed={kind === item}
                  key={item}
                  disabled={opening}
                  onClick={() => {
                    setKind(item);
                    setPage(1);
                    setSearch('');
                    setQuery('');
                    setData(null);
                    setNotice('');
                  }}
                >
                  {item === 'products' ? 'Produtos' : 'Kits'}
                </button>
              ))}
            </div>
            <button
              ref={newButton}
              className="auth-button"
              disabled={opening}
              onClick={() => {
                setSelected(null);
                setNotice('');
                setMode('new');
              }}
            >
              {kind === 'products' ? 'Novo produto' : 'Novo kit'}
            </button>
          </div>
          <form
            className="catalog-search"
            role="search"
            onSubmit={(event) => {
              event.preventDefault();
              setPage(1);
              setQuery(search.trim());
              setRefresh((value) => value + 1);
            }}
          >
            <label>
              Buscar por nome
              <input
                maxLength={200}
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder={
                  kind === 'products' ? 'Ex.: mesa branca' : 'Ex.: kit festa'
                }
              />
            </label>
            <button className="auth-retry" type="submit" disabled={opening}>
              Buscar
            </button>
          </form>
          {kind === 'products' && (
            <p className="catalog-help">
              Estoque apto antes dos compromissos do período. Cores e tamanhos
              com estoque distinto são produtos separados.
            </p>
          )}
          {opening && <p role="status">Abrindo cadastro…</p>}
          {loading ? (
            <StatePanel
              icon="box"
              title="Carregando catálogo…"
              showReturnLink={false}
              description="Buscando os cadastros da locadora."
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
              icon="box"
              showReturnLink={false}
              title={
                query
                  ? 'Nenhum resultado'
                  : kind === 'products'
                    ? 'Seu acervo começa aqui'
                    : 'Monte seu primeiro kit'
              }
              description={
                query
                  ? 'Tente outro nome ou limpe a busca.'
                  : kind === 'products'
                    ? 'Cadastre nome, preço por locação e quantidade. Os detalhes e as fotos podem vir depois.'
                    : 'Cadastre produtos primeiro e reúna-os em um kit com preço comercial próprio.'
              }
            />
          ) : (
            <>
              <p className="catalog-result-count">
                {data.total} {kind === 'products' ? 'produto(s)' : 'kit(s)'} ·
                Página {page}
              </p>
              <ul className="catalog-grid">
                {data.items.map((record) => (
                  <li key={record.id} className="catalog-card">
                    <div className="catalog-card-heading">
                      <span className="catalog-badge">
                        {record.is_active ? 'Ativo' : 'Inativo'}
                      </span>
                      {!productRecord(record) && record.needs_review && (
                        <span className="catalog-badge catalog-badge--warning">
                          Precisa de revisão
                        </span>
                      )}
                    </div>
                    <h2>{record.name}</h2>
                    <p className="catalog-price">
                      {priceLabel(record.price)} <span>por locação</span>
                    </p>
                    {productRecord(record) ? (
                      <p className="catalog-card-stock">
                        <strong>{record.apt_quantity}</strong> aptos{' '}
                        <span>
                          · {record.total_quantity} total ·{' '}
                          {record.maintenance_quantity} em manutenção
                        </span>
                      </p>
                    ) : (
                      <p className="catalog-help">
                        {record.items.length} produto(s) · Sem estoque próprio
                      </p>
                    )}
                    <button
                      className="auth-retry"
                      disabled={opening}
                      onClick={() => void open(record)}
                      aria-label={`Abrir ${record.name}`}
                    >
                      Abrir cadastro <span aria-hidden="true">→</span>
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
