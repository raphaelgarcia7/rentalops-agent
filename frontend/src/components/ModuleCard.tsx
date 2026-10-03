import { Link } from 'react-router';
import type { WorkspaceModule } from '../modules';
import { Icon } from './Icon';

export function ModuleCard({ module }: { module: WorkspaceModule }) {
  return (
    <Link
      className="module-card"
      to={module.path}
      aria-label={`Abrir ${module.title}`}
    >
      <div className="module-card__top">
        <span className="module-icon">
          <Icon name={module.icon} />
        </span>
        <span className="module-number" aria-hidden="true">
          {module.number}
        </span>
      </div>
      <div className="module-card__body">
        <h3>{module.title}</h3>
        <p>{module.description}</p>
      </div>
      <div className="module-card__footer">
        <span>
          {module.path === '/catalogo' ? 'Abrir acervo' : 'Em construção'}
        </span>
        <Icon name="arrow" size={20} />
      </div>
    </Link>
  );
}
