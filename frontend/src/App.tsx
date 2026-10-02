import { Route, Routes } from 'react-router';
import { AppShell } from './components/AppShell';
import { modules } from './modules';
import { HomePage } from './pages/HomePage';
import { ModulePage } from './pages/ModulePage';
import { NotFoundPage } from './pages/NotFoundPage';

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<HomePage />} />
        {modules.map((module) => (
          <Route
            key={module.path}
            path={module.path}
            element={<ModulePage module={module} />}
          />
        ))}
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AppShell>
  );
}
