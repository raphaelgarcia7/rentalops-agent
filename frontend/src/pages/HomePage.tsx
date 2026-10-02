import { Icon } from '../components/Icon';
import { ModuleCard } from '../components/ModuleCard';
import { WelcomeArt } from '../components/WelcomeArt';
import { modules } from '../modules';

export function HomePage() {
  return (
    <>
      <section className="welcome-section">
        <div className="welcome-copy">
          <div className="eyebrow">OPERAÇÃO DE LOCAÇÕES</div>
          <h1>
            Organização que
            <br />
            <em>abre espaço</em> para criar.
          </h1>
          <p>
            Seu espaço de trabalho começa aqui. Explore as áreas que vão dar
            forma à operação da sua locadora.
          </p>
        </div>
        <WelcomeArt />
      </section>
      <section aria-labelledby="modules-title">
        <div className="section-heading">
          <div>
            <span className="section-kicker">SEU NEGÓCIO, EM CAMADAS</span>
            <h2 id="modules-title">Tudo começa por aqui</h2>
          </div>
          <span className="foundation-badge">Em desenvolvimento</span>
        </div>
        <div className="module-grid">
          {modules.map((module) => (
            <ModuleCard key={module.path} module={module} />
          ))}
        </div>
      </section>
      <section className="assistant-banner" aria-labelledby="assistant-title">
        <span className="assistant-symbol">
          <Icon name="sparkles" />
        </span>
        <div className="assistant-copy">
          <span className="section-kicker">PRÓXIMOS PASSOS</span>
          <h2 id="assistant-title">Uma nova forma de cuidar das locações.</h2>
          <p>
            O assistente conversacional está planejado. Por enquanto, você pode
            navegar pela estrutura inicial do RentalOps.
          </p>
        </div>
        <span className="coming-soon">Planejado</span>
      </section>
    </>
  );
}
