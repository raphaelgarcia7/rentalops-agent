import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { Link, NavLink, useLocation } from 'react-router';
import { modules } from '../modules';

export function AppShell({
  children,
  logout,
  logoutBusy,
}: {
  children: ReactNode;
  logout: () => void;
  logoutBusy: boolean;
}) {
  const { pathname } = useLocation();
  const mainRef = useRef<HTMLElement>(null);
  const previousPath = useRef(pathname);
  const pageTitle =
    pathname === '/'
      ? 'Visão geral'
      : (modules.find(
          (module) => module.path === pathname.replace(/\/$/, '').toLowerCase(),
        )?.title ?? 'Página não encontrada');
  useEffect(() => {
    document.title = `${pageTitle} · RentalOps`;
    if (previousPath.current !== pathname) {
      mainRef.current?.focus();
      window.scrollTo(0, 0);
      previousPath.current = pathname;
    }
  }, [pathname, pageTitle]);
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Pular para o conteúdo
      </a>
      <aside className="sidebar" aria-label="Espaço de trabalho">
        <Link className="brand" to="/" aria-label="RentalOps, início">
          <span className="brand-mark" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
          <span>
            <strong>
              rental<span>ops</span>
            </strong>
            <small>ESPAÇO DE TRABALHO</small>
          </span>
        </Link>
        <div className="sidebar-label">MINHA LOCADORA</div>
        <nav className="main-nav" aria-label="Navegação principal">
          <NavLink className="nav-item" to="/" end>
            <span className="nav-index" aria-hidden="true">
              ○
            </span>
            Visão geral
          </NavLink>
          {modules.map((module) => (
            <NavLink
              className="nav-item"
              key={module.path}
              to={module.path}
              end
            >
              <span className="nav-index" aria-hidden="true">
                {module.number}
              </span>
              {module.title}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="workspace-avatar" aria-hidden="true">
            R
          </span>
          <div>
            <strong>RentalOps</strong>
            <small>Versão inicial</small>
          </div>
        </div>
      </aside>
      <div className="main-content">
        <header className="topbar">
          <div className="breadcrumb">
            <span>Workspace</span>
            <span aria-hidden="true">/</span>
            <strong>{pageTitle}</strong>
          </div>
          <button
            className="auth-retry"
            type="button"
            disabled={logoutBusy}
            onClick={logout}
          >
            {logoutBusy ? 'Saindo…' : 'Sair'}
          </button>
        </header>
        <main
          className="page-content"
          id="main-content"
          ref={mainRef}
          tabIndex={-1}
          aria-label={pageTitle}
        >
          {children}
        </main>
        <footer className="page-footer">
          <span>RentalOps · Gestão de locações</span>
          <span>Um espaço para sua operação.</span>
        </footer>
      </div>
    </div>
  );
}
