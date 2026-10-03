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
      'Este espaço será dedicado ao cadastro de clientes e ao histórico de suas locações. Essas funções ainda serão implementadas.',
    icon: 'users',
  },
  {
    path: '/locacoes',
    number: '03',
    title: 'Locações',
    description: 'Propostas e acompanhamento das locações.',
    plannedDescription:
      'Este espaço será dedicado às propostas e ao acompanhamento de locações. A consulta de disponibilidade e o registro de reservas ainda serão implementados.',
    icon: 'calendar',
  },
] as const;

export type WorkspaceModule = (typeof modules)[number];
