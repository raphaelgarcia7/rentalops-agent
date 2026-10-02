import { Link } from 'react-router';
import { Icon } from './Icon';
import type { IconName } from './Icon';

export function StatePanel({
  icon,
  title,
  description,
}: {
  icon: IconName;
  title: string;
  description: string;
}) {
  return (
    <section className="state-panel" aria-label={title}>
      <span className="state-icon">
        <Icon name={icon} size={32} />
      </span>
      <h2>{title}</h2>
      <p>{description}</p>
      <Link className="text-link" to="/">
        Voltar à visão geral <Icon name="arrow" size={18} />
      </Link>
    </section>
  );
}
