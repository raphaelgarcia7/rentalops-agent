# RentalOps

RentalOps é um sistema para organizar locações de decorações e itens para festas e eventos. Ele combina uma operação web tradicional com um assistente de IA que poderá ajudar a consultar o catálogo, verificar disponibilidade e preparar reservas.

O projeto é construído como um monorepo: frontend, backend, documentação e infraestrutura ficam no mesmo repositório, com dependências e ciclos de execução próprios.

## Problema que queremos resolver

Uma locação pode incluir kits, itens avulsos, quantidades, datas, estoque e detalhes que precisam ser esclarecidos antes da confirmação. O RentalOps centraliza essas informações para que a equipe consiga montar propostas consistentes e acompanhar reservas com segurança.

## Escopo do produto

- Gerenciar produtos e itens avulsos.
- Criar kits compostos por produtos do catálogo.
- Manter cadastro de clientes.
- Consultar disponibilidade por período.
- Criar reservas com kits, itens avulsos ou ambos.
- Calcular uma proposta e solicitar confirmação antes de registrar uma reserva.
- Acompanhar reservas e, numa etapa posterior, contratos.
- Oferecer uma interface conversacional para os mesmos fluxos da operação web.

## Princípios do sistema e do agente

- As telas web e as ferramentas do agente usam os mesmos serviços de aplicação.
- Estoque, preços, disponibilidade e reservas são validados por regras explícitas e dados persistidos.
- O modelo interpreta pedidos, coleta informações que faltam, escolhe operações disponíveis e explica resultados. Ele não é a fonte de verdade comercial.
- O estado da conversa pode ajudar a dar continuidade ao atendimento, mas não substitui registros de negócio.
- A primeira entrega funcional deve ser uma fatia vertical de ponta a ponta, começando por catálogo, período, disponibilidade e composição de uma reserva.
- Decisões centrais de AI Engineering devem registrar alternativas, recomendação, trade-offs e comportamento em caso de falha em `docs/`.

## Estrutura do repositório

```text
.
├── backend/   # API Python e, futuramente, serviços de aplicação e agente
├── frontend/  # Interface web React e TypeScript
├── docs/      # Escopo, arquitetura e registros de decisão
├── infra/     # Configurações de execução e implantação
├── .env.example
└── README.md
```

O backend usa o layout `src/` para separar o pacote Python do restante da configuração. Frontend e backend podem ser desenvolvidos e implantados independentemente, mantendo contratos explícitos entre eles.

## Tecnologias

- **Backend:** Python, FastAPI e `uv`.
- **Frontend:** React, TypeScript e Vite.
- **Assistente:** a arquitetura de agente será adicionada quando o primeiro fluxo de locação for definido; as escolhas de estado, ferramentas, memória e persistência serão documentadas antes da implementação.

## Estado atual

O backend expõe apenas uma verificação de saúde (`GET /health`). O frontend oferece uma visão geral e navegação responsiva para Catálogo (`/catalogo`), Clientes (`/clientes`) e Locações (`/locacoes`), com links ativos, acesso direto, histórico do navegador e recuperação de endereços inexistentes. Componentes e tokens visuais são compartilhados entre as telas.

As três áreas apresentam explicitamente o estado **Em construção**. Ainda não há cadastros, dados de negócio, preços, estoque, reservas, persistência, autenticação ou assistente funcional. A interface atual não chama a API nem confirma operações comerciais.

## Requisitos

- Python 3.14.
- [uv](https://docs.astral.sh/uv/).
- Node.js 24 ou superior.
- Uma chave da OpenAI quando a integração do assistente for implementada.

## Executar localmente

### Backend

Na raiz do repositório, instale as dependências e inicie a API:

```bash
uv sync --project backend
uv run --project backend uvicorn rentalops_api.main:app --reload
```

A API fica em `http://127.0.0.1:8000`. A documentação interativa fica em `http://127.0.0.1:8000/docs`; a verificação de saúde fica em `http://127.0.0.1:8000/health`.

### Frontend

Em outro terminal:

```bash
cd frontend
npm ci
npm run dev
```

Acesse `http://localhost:5173`.

As rotas usam o histórico do navegador, conforme o [modo declarativo do React Router](https://reactrouter.com/start/declarative/installation). Em uma futura hospedagem estática, configurar o servidor para retornar `index.html` nas rotas da aplicação; o servidor do Vite já oferece esse comportamento localmente. Hospedagem não faz parte desta entrega.

### Verificar o frontend

Em `frontend/`:

```bash
npm run lint
npm run format:check
npm test
npm run build
npm audit --audit-level=high
npx playwright install chromium
npm run test:e2e
```

Vitest e Testing Library verificam a integração das telas e rotas. Playwright testa o build de produção servido pelo preview do Vite na porta 4173: links, histórico, atualização da página, teclado, foco, movimento reduzido, recuperação e acessibilidade com axe nas larguras 320, 390, 768 e 1440 px. As capturas ficam em `frontend/test-results/evidence/` e o relatório em `frontend/playwright-report/`, ambos ignorados pelo Git. Esses testes não certificam todos os dispositivos nem substituem validação pela equipe da locadora. Estados de carregamento e erro de negócio serão adicionados com operações reais; esta estrutura é estática.

## Configuração local

Copie `.env.example` para `.env` na raiz do repositório. A chave `OPENAI_API_KEY` será necessária quando o backend passar a chamar o modelo. O arquivo `.env` está no `.gitignore`; nunca versione credenciais.

## Documentação

- [Princípios de arquitetura](docs/architecture.md)
- [Infraestrutura e implantação](infra/README.md)

## Desenvolvimento

Cada capacidade deve ser construída incrementalmente e manter regras de negócio testáveis sem depender do modelo. Antes de adotar uma solução entre alternativas razoáveis para uma parte central de AI Engineering, documente as opções e a recomendação em `docs/decisions/`.
