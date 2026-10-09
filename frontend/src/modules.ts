export const modules = [
  {
    path: '/catalogo',
    number: '01',
    title: 'Catálogo',
    description: 'Produtos, itens avulsos e kits de decoração.',
    plannedDescription:
      'Cadastre produtos completos, estoque cadastral, manutenção e kits com preço próprio.',
    icon: 'box',
  },
  {
    path: '/clientes',
    number: '02',
    title: 'Clientes',
    description: 'Contatos e histórico de cada cliente.',
    plannedDescription:
      'Cadastre pessoas físicas pelo nome e telefone e complete os documentos depois. O histórico de locações será integrado em uma próxima entrega.',
    icon: 'users',
  },
  {
    path: '/locacoes',
    number: '03',
    title: 'Locações',
    description: 'Propostas e acompanhamento das locações.',
    plannedDescription:
      'Prepare orçamentos e registre pagamentos manuais com histórico. A confirmação de reservas será implementada em uma próxima etapa.',
    icon: 'calendar',
  },
] as const;

export type WorkspaceModule = (typeof modules)[number];
