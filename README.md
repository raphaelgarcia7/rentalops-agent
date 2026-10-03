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

- **Backend:** Python, FastAPI, SQLAlchemy 2 síncrono, Psycopg 3, Alembic e `uv`.
- **Persistência:** PostgreSQL 17; migrações por comando explícito.
- **Frontend:** React, TypeScript e Vite.
- **Assistente:** a arquitetura de agente será adicionada quando o primeiro fluxo de locação for definido; as escolhas de estado, ferramentas, memória e persistência serão documentadas antes da implementação.

## Estado atual

O backend expõe `GET /health` para verificar o processo e `GET /health/ready` para verificar a conexão PostgreSQL. A primeira migração cria somente identidades mínimas da equipe: UUID, e-mail normalizado e único, estado ativo e instantes UTC. Nenhuma conta é criada automaticamente. Essa tabela não implementa login nem concede acesso; autenticação e provisionamento permanecem na ROP-021.

O frontend oferece uma visão geral e navegação responsiva para Catálogo (`/catalogo`), Clientes (`/clientes`) e Locações (`/locacoes`), com links ativos, acesso direto, histórico do navegador e recuperação de endereços inexistentes. Componentes e tokens visuais são compartilhados entre as telas.

As três áreas apresentam explicitamente o estado **Em construção**. Ainda não há cadastros operacionais, dados comerciais, preços, estoque, reservas, autenticação ou assistente funcional. A interface atual não chama a API nem confirma operações comerciais. ROP-007 prepara a persistência para os próximos cadastros de catálogo e clientes, sem antecipar suas regras.

## Requisitos

- Python 3.14.
- [uv](https://docs.astral.sh/uv/).
- Node.js 24 ou superior.
- PostgreSQL 17 local e bancos separados para desenvolvimento e testes.
- Uma chave da OpenAI quando a integração do assistente for implementada.

## Executar localmente

### Backend

Na raiz do repositório, instale as dependências e inicie a API:

```bash
uv sync --project backend --locked
uv run --project backend uvicorn rentalops_api.main:app --reload
```

A API fica em `http://127.0.0.1:8000`. A documentação interativa fica em `http://127.0.0.1:8000/docs`; a verificação de saúde fica em `http://127.0.0.1:8000/health`. Essa rota responde 200 sem banco. Readiness responde `200 {"status":"ready"}` com conexão acessível ou `503 {"status":"unavailable"}` em falha/configuração inválida, sem detalhes internos. Ela verifica conectividade, não versão da migração. Importar fontes e iniciar a API não aplica DDL.

### PostgreSQL e migrações

Crie um banco local de desenvolvimento e outro dedicado aos testes, usando uma conta PostgreSQL autorizada. Configure `DATABASE_URL` e `TEST_DATABASE_URL` no `.env` da raiz, conforme os exemplos sintéticos. Não copie credenciais reais para comandos compartilhados, logs ou arquivos versionados. Variáveis definidas no ambiente prevalecem sobre `.env`, inclusive quando vazias.

Na raiz, aplique a migração explicitamente ao banco escolhido em `DATABASE_URL`:

```bash
uv run --project backend alembic -c backend/alembic.ini upgrade head
uv run --project backend alembic -c backend/alembic.ini current
```

Repetir `upgrade head` preserva registros. Não execute downgrade em banco existente: ele remove `users`. A suíte verifica downgrade somente no namespace descartável que ela própria criou. Não use `create_all` para implantação. Migração offline não é suportada nesta entrega.

Veja [isolamento e instância descartável](infra/database/README.md) para executar sem tocar em bancos ou autenticação de um serviço existente.

### Verificar o backend

Na raiz, após configurar `TEST_DATABASE_URL`:

```bash
uv sync --project backend --locked
uv run --project backend ruff check backend
uv run --project backend ruff format --check backend
uv run --project backend mypy --config-file backend/pyproject.toml
uv run --project backend pytest backend/tests
uv export --project backend --locked --all-groups --no-emit-project --format requirements-txt -o audit-requirements.txt --quiet
uv run --project backend pip-audit -r audit-requirements.txt --disable-pip --no-deps
```

O arquivo exportado contém dependências de produção e desenvolvimento, sem o pacote local. Guarde-o fora do repositório quando possível. Testes unitários isolados: `uv run --project backend pytest backend/tests/unit`. A suíte completa falha claramente se o alvo de integração faltar ou for inseguro, sem skip/fallback. Ela exige PostgreSQL em `127.0.0.1`, `localhost` ou `::1`, nome com segmento `test`, sem opções de query no URL, e alvo distinto do desenvolvimento. Cada teste cria e remove somente seu schema `rentalops_test_<UUID>`. Nenhum banco é apagado.

Sessões recebem uma factory explícita. O chamador executa `session.commit()`; sair sem commit não persiste alterações. `session_scope` reverte exceções e fecha a sessão. Se o chamador capturar uma falha dentro do bloco e quiser continuar, precisa executar `session.rollback()` antes da próxima operação. Não mantenha transações durante espera por rede/modelo. Após atualização, `session.refresh(user)` recarrega `updated_at` gerado pelo banco. Não há repositório genérico nem container de dependências.

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
- [Evidências da fundação PostgreSQL](docs/engineering/rop-007-evidence.md)

## Desenvolvimento

Cada capacidade deve ser construída incrementalmente e manter regras de negócio testáveis sem depender do modelo. Antes de adotar uma solução entre alternativas razoáveis para uma parte central de AI Engineering, documente as opções e a recomendação em `docs/decisions/`.
