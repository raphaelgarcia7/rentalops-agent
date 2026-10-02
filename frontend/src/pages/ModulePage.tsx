import { StatePanel } from '../components/StatePanel';
import type { WorkspaceModule } from '../modules';

export function ModulePage({ module }: { module: WorkspaceModule }) {
  return (
    <>
      <header className="page-heading">
        <span className="section-kicker">ESPAÇO DE TRABALHO</span>
        <h1>{module.title}</h1>
        <p>{module.description}</p>
      </header>
      <StatePanel
        icon={module.icon}
        title="Em construção"
        description={module.plannedDescription}
      />
    </>
  );
}
