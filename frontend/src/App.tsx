import { Route, Routes } from 'react-router';
import { AppShell } from './components/AppShell';
import { modules } from './modules';
import { HomePage } from './pages/HomePage';
import { ModulePage } from './pages/ModulePage';
import { NotFoundPage } from './pages/NotFoundPage';
import { AuthGate } from './auth';
import { useContext } from 'react';
import { AuthContext } from './authContext';
import { CatalogPage } from './catalog/CatalogPage';
import { CustomersPage } from './customers/CustomersPage';
import { QuotationsPage } from './quotations/QuotationsPage';

export default function App() {
  return (
    <AuthGate>
      <AuthenticatedWorkspace />
    </AuthGate>
  );
}

function AuthenticatedWorkspace() {
  const { logout, busy } = useContext(AuthContext);
  return <Workspace logout={logout} busy={busy} />;
}

export function Workspace({
  logout,
  busy,
}: {
  logout: () => void;
  busy: boolean;
}) {
  return (
    <AppShell logout={logout} logoutBusy={busy}>
      <Routes>
        <Route path="/" element={<HomePage />} />
        {modules.map((module) => (
          <Route
            key={module.path}
            path={module.path}
            element={
              module.path === '/catalogo' ? (
                <CatalogPage />
              ) : module.path === '/clientes' ? (
                <CustomersPage />
              ) : module.path === '/locacoes' ? (
                <QuotationsPage />
              ) : (
                <ModulePage module={module} />
              )
            }
          />
        ))}
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AppShell>
  );
}
