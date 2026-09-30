import type { ReactNode } from 'react';

const modules = [
  {
    id: 'catalogo',
    number: '01',
    title: 'Catálogo',
    description: 'Produtos, itens avulsos e kits de decoração.',
    icon: 'box',
  },
  {
    id: 'estoque',
    number: '02',
    title: 'Estoque',
    description: 'Disponibilidade e quantidades por período.',
    icon: 'layers',
  },
  {
    id: 'reservas',
    number: '03',
    title: 'Reservas',
    description: 'Locações, propostas e acompanhamento.',
    icon: 'calendar',
  },
  {
    id: 'contratos',
    number: '04',
    title: 'Contratos',
    description: 'Documentos e etapas futuras da locação.',
    icon: 'file',
  },
] as const;

type IconName = (typeof modules)[number]['icon'] | 'sparkles' | 'arrow';

function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, ReactNode> = {
    box: <><path d="m12 3 9 5-9 5-9-5 9-5Z" /><path d="m3 8 9 5 9-5M3 8v9l9 5 9-5V8M12 13v9" /></>,
    layers: <><path d="m12 3 9 5-9 5-9-5 9-5Z" /><path d="m3 12 9 5 9-5M3 16l9 5 9-5" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18" /></>,
    file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6M8 13h8M8 17h8" /></>,
    sparkles: <><path d="m12 3 1.4 4.6L18 9l-4.6 1.4L12 15l-1.4-4.6L6 9l4.6-1.4L12 3Z" /><path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z" /></>,
    arrow: <><path d="M5 12h14M13 6l6 6-6 6" /></>,
  };

  return (
    <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      {paths[name]}
    </svg>
  );
}

function BrandMark() {
  return <span className="brand-mark" aria-hidden="true"><span /><span /><span /></span>;
}

function App() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#inicio" aria-label="RentalOps, início">
          <BrandMark />
          <span><strong>rental<span>ops</span></strong><small>RENTAL WORKSPACE</small></span>
        </a>

        <div className="sidebar-label">ESPAÇO DE TRABALHO</div>
        <nav className="main-nav" aria-label="Navegação principal">
          <a className="nav-item nav-item--active" href="#inicio"><span className="nav-dot" />Visão geral</a>
          <a className="nav-item" href="#catalogo"><span className="nav-index">01</span>Catálogo</a>
          <a className="nav-item" href="#estoque"><span className="nav-index">02</span>Estoque</a>
          <a className="nav-item" href="#reservas"><span className="nav-index">03</span>Reservas</a>
          <a className="nav-item" href="#contratos"><span className="nav-index">04</span>Contratos</a>
        </nav>

        <div className="sidebar-bottom">
          <div className="workspace-avatar">R</div>
          <div><strong>Minha locadora</strong><small>Workspace local</small></div>
          <span className="workspace-menu" aria-hidden="true">···</span>
        </div>
      </aside>

      <main className="main-content" id="inicio">
        <header className="topbar">
          <div className="breadcrumb"><span>Workspace</span><i>/</i><strong>Visão geral</strong></div>
          <div className="topbar-status"><span />Ambiente de desenvolvimento</div>
        </header>

        <div className="page-content">
          <section className="welcome-section">
            <div className="welcome-copy">
              <div className="eyebrow"><span />OPERAÇÃO DE LOCAÇÕES</div>
              <h1>Organização que<br /><em>abre espaço</em> para criar.</h1>
              <p>Um espaço para cuidar do catálogo, do estoque e de cada detalhe das suas locações.</p>
            </div>
            <div className="welcome-art" aria-hidden="true">
              <div className="art-orbit art-orbit--outer" />
              <div className="art-orbit art-orbit--inner" />
              <div className="art-sun" />
              <div className="art-object art-object--one"><span /></div>
              <div className="art-object art-object--two"><span /></div>
              <div className="art-object art-object--three"><span /></div>
              <div className="art-ground" />
            </div>
          </section>

          <section className="section-heading" aria-labelledby="modules-title">
            <div><span className="section-kicker">SEU NEGÓCIO, EM CAMADAS</span><h2 id="modules-title">Tudo começa por aqui</h2></div>
            <span className="foundation-badge"><i />Fundação do produto</span>
          </section>

          <section className="module-grid" aria-label="Módulos do RentalOps">
            {modules.map((module, index) => (
              <a className={`module-card module-card--${module.icon}`} href={`#${module.id}`} id={module.id} key={module.id}
                style={{ animationDelay: `${index * 75}ms` }}>
                <div className="module-card__top"><span className="module-icon"><Icon name={module.icon} size={20} /></span><span className="module-number">{module.number}</span></div>
                <div className="module-card__body"><h3>{module.title}</h3><p>{module.description}</p></div>
                <div className="module-card__footer"><span>Em construção</span><Icon name="arrow" size={16} /></div>
              </a>
            ))}
          </section>

          <section className="assistant-banner" aria-label="Assistente operacional planejado">
            <div className="assistant-symbol"><Icon name="sparkles" size={21} /></div>
            <div className="assistant-copy"><span className="section-kicker">UMA NOVA FORMA DE OPERAR</span><h2>Um assistente que entende o contexto da sua locadora.</h2>
              <p>O agente vai consultar as mesmas regras e informações usadas pela operação, com confirmação antes de registrar reservas.</p></div>
            <span className="coming-soon">PLANEJADO</span>
            <div className="banner-glow" aria-hidden="true" />
          </section>

          <footer className="page-footer"><span>RentalOps <i>·</i> Gestão de locações</span><span>Construído com cuidado para operações reais.</span></footer>
        </div>
      </main>
    </div>
  );
}

export default App;
