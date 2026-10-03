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

O backend expõe `GET /health` para verificar o processo e `GET /health/ready` para verificar a conexão PostgreSQL. As migrações criam identidades individuais e autenticação por senha: Argon2id, sessões opacas, links administrativos de uso único, limites persistentes e auditoria por IDs. Nenhuma conta é criada automaticamente. O acesso é fechado e todos os usuários autorizados têm as mesmas permissões.

O frontend oferece uma visão geral e navegação responsiva para Catálogo (`/catalogo`), Clientes (`/clientes`) e Locações (`/locacoes`), com links ativos, acesso direto, histórico do navegador e recuperação de endereços inexistentes. Componentes e tokens visuais são compartilhados entre as telas.

O Catálogo permite cadastrar, buscar, editar e inativar produtos e kits, consultar histórico, ajustar estoque com motivo, registrar manutenção/liberação e adicionar fotos privadas. Produtos completos têm estoque próprio; kits têm preço comercial próprio e composição somente de produtos, sem estoque independente. Clientes permite cadastrar, buscar, consultar e editar pessoas físicas com nome/telefone e detalhes opcionais posteriores. Locações continua **Em construção**. Não há reservas, alocações, disponibilidade por período nem assistente funcional. Google permanece adiado para a ROP-022; não há cadastro público, SMTP, senha padrão, roles nem tela de gestão de usuários.

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
uv run --project backend uvicorn rentalops_api.main:app --reload --no-proxy-headers --no-access-log
```

A API fica em `http://127.0.0.1:8000`. A documentação interativa fica em `http://127.0.0.1:8000/docs`; a verificação de saúde fica em `http://127.0.0.1:8000/health`. Essa rota responde 200 sem banco. Readiness responde `200 {"status":"ready"}` com conexão acessível ou `503 {"status":"unavailable"}` em falha/configuração inválida, sem detalhes internos. Ela verifica conectividade, não versão da migração. Importar fontes e iniciar a API não aplica DDL.

### PostgreSQL e migrações

Crie um banco local de desenvolvimento e outro dedicado aos testes, usando uma conta PostgreSQL autorizada. Configure `DATABASE_URL` e `TEST_DATABASE_URL` no `.env` da raiz, conforme os exemplos sintéticos. Não copie credenciais reais para comandos compartilhados, logs ou arquivos versionados. Variáveis definidas no ambiente prevalecem sobre `.env`, inclusive quando vazias.

Na raiz, aplique a migração explicitamente ao banco escolhido em `DATABASE_URL`:

```bash
uv run --project backend alembic -c backend/alembic.ini upgrade head
uv run --project backend alembic -c backend/alembic.ini current
```

Repetir `upgrade head` preserva registros. As migrações `0004_catalog` e `0005_customers` acrescentam catálogo e clientes sem substituir autenticação. Não execute downgrade em banco existente: ele remove tabelas/dados da revisão revertida. A suíte verifica downgrade somente no namespace descartável que ela própria criou. Não use `create_all` para implantação. Migração offline não é suportada nesta entrega.

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

O Vite encaminha `/api` para a API local em `127.0.0.1:8000`. Configure `AUTH_ORIGIN` com o endereço exato utilizado no navegador (o exemplo é `http://localhost:5173`); `localhost` e `127.0.0.1` são origens diferentes. Produção requer `APP_ENV=production`, uma origem HTTPS sem caminho/barra final e encaminhamento de `/api` para a API na mesma origem. O backend recusa origem ausente/diferente nas mutações de autenticação, catálogo e clientes e na busca POST de clientes, sem confiar no Host ou em headers forwarded. Não há CORS com credenciais. Só habilite headers de proxy após configuração explícita de um proxy confiável; nesta entrega os comandos desabilitam essa confiança e os access logs.

### Catálogo e fotos privadas

Produto mínimo: nome, preço por locação e quantidade inicial (inclusive zero). Descrição, categoria, cor, medidas, reposição, observação e fotos são opcionais. Variações de cor/tamanho são cadastros separados. A quantidade inicial gera movimento auditado; depois, entrada/baixa/correção e manutenção/liberação exigem motivo, autoria da sessão e versão esperada. Total não pode ser negativo nem inferior à manutenção. A tela mostra quantidade apta **antes dos compromissos do período**, não uma promessa de disponibilidade para reserva.

Kits exigem composição não vazia com produtos existentes/ativos e quantidades inteiras positivas. Repetições são agregadas; kit aninhado é recusado. Alterar o preço do produto não recalcula o preço do kit. Inativar um componente conserva composição/histórico e sinaliza revisão; substitua/remova o inativo para salvar a revisão. Não há exclusão definitiva.

Defina `STORAGE_ROOT` no `.env` privado como caminho absoluto de uma pasta existente, fora de qualquer checkout Git e do diretório público do frontend. Crie essa pasta e conceda acesso somente ao processo/operador autorizado. Sem configuração válida, upload/leitura retornam 503 genérico; o restante do catálogo não depende dela. JPEG, PNG e WebP precisam ser decodificáveis e corresponder ao tipo declarado: máximo **10 MiB e 20 megapixels** por imagem. SVG/HTML/conteúdo disfarçado são recusados, EXIF/metadados são removidos na cópia normalizada e o nome interno é aleatório. Não há fotografia inventada ou reconhecimento de pessoas.

PostgreSQL guarda metadados/hash/ordem/principal, não bytes. IDs e bytes são imutáveis; substituição cria outro asset. Remover da galeria apenas desassocia e conserva acesso autenticado ao asset histórico. Não apague/mova arquivos manualmente: snapshots futuros poderão referenciá-los. Falha confirmada no banco compensa somente o arquivo novo; resultado incerto de commit conserva o asset para não quebrar referência persistida. Não existe coleta automática de órfãos. Volume, retenção e backup coordenado de banco/arquivos antes de produção pertencem à #4. Fotos continuam opcionais nesta entrega; a emissão ilustrada de contrato pertence à #15.

API (prefixo `/api` somente no proxy frontend): POST/GET `/products` e `/kits`, GET/PATCH `/{id}`, POST `/{id}/inactivate`; POST `/products/{id}/stock-adjustments`, `/maintenance` e `/maintenance/{entry_id}/release`. Fotos: POST multipart `/products/{id}/photos` com `file`/`expected_version`, PATCH `/products/{id}/photos/{photo_id}` para ordem/principal, POST `.../detach`, GET autenticado `/photos/{photo_id}` com tipo verificado e `nosniff`. Listas usam `search`, `page` e `page_size` (25 padrão/100 máximo), ordenação estável por nome/UUID. Valores monetários são strings decimais exatas (até 2 casas, não negativos, Numeric(12,2)); quantidades/versões são inteiros validados. Edições/comandos exigem `expected_version`; actor/IDs/timestamps internos não são aceitos do cliente.

Criação retorna 201; consulta/mutação bem-sucedida 200; sessão ausente 401, origem recusada 403, inexistente 404, conflito de versão/referência 409, imagem grande 413, entrada inválida 422 e falha interna/storage 503 genérico. A tela preserva rascunho em 409 e permite consultar a versão atual antes de tentar novamente explicitamente. Serviços de aplicação não dependem do canal web/IA. R08-INV (#11), R08-RET (#14) e R08-INACT (#10/#11) permanecem integrações futuras com reservas/recebimentos reais; nenhum hold ou reserva fictícia foi criado.

### Clientes e dados pessoais

No PATCH progressivo, membros de endereço omitidos são preservados; `address: {}` não limpa os dados existentes. Um membro explícito vazio/null limpa apenas esse membro, e `address: null` limpa o endereço inteiro.

Cadastre uma pessoa física somente com nome (1–200 caracteres) e telefone/WhatsApp. E-mail (até 320) e observações (até 4.000) são opcionais. CPF/RG e endereço podem ser completados depois, sem exigir endereço inteiro; a emissão do contrato terá seus critérios na #15. Não há CNPJ, fusão automática, exclusão definitiva nem mensagens enviadas ao cliente. O telefone é normalizado com [phonenumbers](https://pypi.org/project/phonenumbers/) em E.164, usando Brasil inicialmente e aceitando código internacional explícito. A validação não comprova que o contato tem WhatsApp.

Contato compartilhado retorna 409 `shared_contact` com UUIDs existentes. A tela oferece consulta em outra aba, preservando o formulário, e uma ação explícita para confirmar pessoa distinta. `acknowledged_shared_contact` é uma lista dos UUIDs observados, não um booleano: um novo cadastro concorrente exige novo aviso/consentimento. Um lock transacional curto por contato serializa consulta/escrita; o telefone não é único. CPF informado é normalizado/validado e protegido por UNIQUE PostgreSQL; duplicidade na criação/edição retorna 409 `duplicate_cpf` com ID existente. CPF ausente persiste NULL e permite pessoas distintas.

API autenticada: POST `/customers` cria (201, Location somente com UUID), GET `/customers/{id}` consulta, PATCH `/customers/{id}` altera somente campos fornecidos e exige `expected_version`. A atualização usa precondição atômica e conflito 409 `stale_version`; a tela conserva o rascunho, compara os dados atuais e permite manter o rascunho com a versão atual ou recarregar os dados por ação explícita. A autoria vem da sessão. ID/versão interna/atores/timestamps arbitrários são recusados. Auditoria guarda cliente/ator/sessão, instante, versão e nomes dos campos alterados, sem cópias dos dados pessoais. O UUID e o link `/clientes?cliente=<UUID>` permanecem estáveis depois da edição, prontos para vínculos futuros; o histórico de locações mostra um vazio verdadeiro até a #10.

POST `/customers/search` recebe `name` (texto), `phone` e `cpf` (normalizados, igualdade exata), `page` >= 1 e `page_size` 25 por padrão/100 máximo no corpo. Ordenação por nome/UUID; resultado contém somente ID/nome/telefone/versão, sem documentos/endereço. Query strings nas rotas de clientes são recusadas; nunca envie documento/contato no URL. Corpo de endereço opcional: `postal_code` (CEP de 8 dígitos, hífen aceito), `street`/`complement` até 200, `number` até 30, `neighborhood`/`city` até 100 e `state` como UF válida. Textos opcionais vazios viram null; RG é textual até 30. Não há geocodificação.

Sem sessão: 401; origem recusada: 403; inexistente: 404; validação: 422 com nomes de campos permitidos, sem eco do valor; indisponibilidade: 503 genérico. Respostas privadas usam no-store/nosniff. Não registrar corpos, query strings, dados pessoais ou SQL em logs/analytics/traces, nem enviar clientes ao LLM. Mantenha access logs desabilitados e qualquer proxy futuro com a mesma política. PostgreSQL guarda somente o cadastro necessário; retenção/backup operacional continua para a #4. Rascunhos permanecem somente em memória após expiração/login, sem promessa de recuperação ao fechar/recarregar a página.

### Contas e recuperação administrativa

Além de `DATABASE_URL`, defina `AUTH_RATE_KEY` no `.env` privado com chave aleatória de pelo menos 32 bytes; mantenha a mesma chave entre processos/reinícios para preservar os limites por pseudônimo. O exemplo deixa esse campo vazio e a API recusa autenticação sem configuração válida. Nunca publique a chave ou credenciais. Aplique `alembic upgrade head` antes dos comandos.

Execute em terminal privado, sem transcrição/compartilhamento de saída, substituindo somente o e-mail pela pessoa autorizada. Os exemplos são sintéticos:

```bash
uv run --project backend python -m rentalops_api.auth_cli create-user --email person@example.invalid
uv run --project backend python -m rentalops_api.auth_cli issue-access-link --email person@example.invalid
uv run --project backend python -m rentalops_api.auth_cli issue-reset-link --email person@example.invalid
uv run --project backend python -m rentalops_api.auth_cli deactivate-user --email person@example.invalid
```

`create-user` normaliza o e-mail, informa UUID/created ou existing e não troca senha, reativa nem duplica conta existente. Não há limite técnico de duas pessoas. `issue-access-link` exige conta ativa ainda sem senha. `issue-reset-link` exige conta ativa autorizada e revoga todas as sessões imediatamente ao gerar a recuperação. A emissão informa a URL privada apenas no terminal para entrega direta; não copie esse resultado para logs, issues, screenshots, chat ou journal. Entregar não comprova recebimento/uso. `deactivate-user` preserva identidade/histórico e revoga todos os links/sessões. Comandos que falham retornam exit 1, sem SQL/stack/credenciais.

Cada link tem 256 bits aleatórios, fica no fragmento do frontend (removido após leitura), dura 30 minutos e funciona uma única vez, inclusive sob concorrência. Apenas hash/finalidade/conta/instantes são persistidos; API recebe token no corpo. Novo link invalida anteriores da conta. Definir senha de 12–128 caracteres invalida links e sessões remanescentes e pede login; frases são permitidas. Link inválido/expirado/reutilizado orienta procurar o administrador. Recuperação é exclusivamente administrativa; nenhum envio de e-mail é implementado.

Definir senha verifica deterministicamente o link e a conta antes de Argon2. A migração incremental `0003_password_set_limits` acrescenta um orçamento persistente separado: em janela de 15 minutos, até 10 tentativas por pseudônimo do token e 30 por pseudônimo do peer direto, contando também tentativas válidas antes do trabalho caro. Tokens aleatórios diferentes não contornam o limite de origem, e reiniciar o processo não limpa o controle. Entrada elegível consome o orçamento mesmo se o hash ou a escrita posterior falharem; nenhuma senha/token/IP bruto é registrado. Excesso retorna 429 genérico. Argon2 roda fora de transação/locks; a transação final revalida link/conta sob lock antes do consumo atômico, protegendo contra emissão, desativação, expiração ou outro consumo durante o hash. Falha não consome silenciosamente o link nem troca a senha.

Sessão tem identificador novo aleatório de 256 bits por login, apenas hash no PostgreSQL, cookie HttpOnly/SameSite=Lax, Secure em produção, Path=/ e sem Domain, JWT ou localStorage. Backend verifica 12 horas absolutas e 1 hora sem atividade em toda ação protegida. GET `/auth/session` e polling de 30 segundos não renovam atividade. Somente teclado/pointer intencionais em página visível enviam POST `/auth/activity`, limitado a um envio por 30 segundos; nunca estende o máximo absoluto. Sair revoga só a sessão atual. Expiração/revogação oculta a operação e preserva componentes/rascunhos em memória; login permite continuar. Recarregar/fechar a página não garante preservação.

Contratos: POST `/auth/password/login` retorna 200 com identidade/instantes e cookie; GET `/auth/session` retorna 200/401; POST `/auth/logout` e `/auth/password/set` retornam 204; POST `/auth/activity` valida sessão existente. Os POST logout/activity recebem `{}`. Entrada inválida/campos extras retornam 422 sem ecoar o payload; credencial inválida 401 genérico, token inválido 400, origem recusada 403, limite 429 e falha interna 503 genérico. `current_identity` é a dependência backend obrigatória para futuras rotas comerciais; GET `/internal/identity` demonstra a fronteira retornando somente UUID autenticado. O cliente não determina autoria.

Falhas de login ficam persistidas em janela móvel de 15 minutos, até 10 por identificador e 30 por origem. Pseudônimos HMAC usam a chave privada; o controle não guarda IP/e-mail bruto. A origem de limite é o peer direto da conexão; atrás de proxy sem configuração confiável, usuários compartilham o limite do proxy (limitação conservadora, sem aceitar X-Forwarded-For arbitrário). Auditoria conserva IDs, instante e código, sem payload pessoal/token/senha. Retenção/backup de registros ainda exige planejamento operacional antes de produção.

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
# TEST_DATABASE_URL must target the same dedicated local test database used by pytest.
npm run test:e2e
```

Vitest e Testing Library verificam rotas, formulários e preservação de estado em memória. Playwright testa o build de produção na porta 4173 em 320, 390, 768 e 1440 px: teclado/foco, movimento reduzido, overflow e axe. Estados controlados de rede/tempo usam respostas sintéticas; `auth-live.spec.ts`, `catalog-live.spec.ts` e `customers-live.spec.ts` testam autenticação, catálogo e clientes com API e PostgreSQL reais, sem mock. Clientes inclui cadastro progressivo, busca/paginação, contato compartilhado, CPF duplicado, edição concorrente, vínculo estável e rascunho após nova autenticação. A suíte exige `TEST_DATABASE_URL` seguro e inicia somente o harness descartável `backend/tests/browser_server.py` em loopback 8000; nunca aponta o navegador a contas/bancos existentes. Ele reutiliza a validação/schema UUID da suíte e aplica migrações nesse schema exclusivo, com armazenamento temporário próprio e imagens sintéticas. Endpoints `__test` existem apenas no harness, ausentes do app de produção. O teardown remove somente esse armazenamento/namespace antes de parar o servidor; falha de cleanup falha a suíte. Não mantenha API/preview existentes nas portas 8000/4173 ao rodar essa suíte.

As capturas ficam em `frontend/test-results/evidence/` e o relatório em `frontend/playwright-report/`, ignorados pelo Git. Elas usam dados sintéticos e limpam campos sensíveis antes da captura de evidência. Traces de falha também contêm apenas contas descartáveis; jamais execute este harness com dados reais. Testes não certificam todos os dispositivos nem substituem validação operacional pela locadora.

## Configuração local

Copie `.env.example` para `.env` na raiz do repositório. A chave `OPENAI_API_KEY` será necessária quando o backend passar a chamar o modelo. O arquivo `.env` está no `.gitignore`; nunca versione credenciais.

## Documentação

- [Princípios de arquitetura](docs/architecture.md)
- [Infraestrutura e implantação](infra/README.md)
- [Evidências da fundação PostgreSQL](docs/engineering/rop-007-evidence.md)
- [Evidências do catálogo](docs/engineering/rop-008-evidence.md)
- [Evidências de clientes](docs/engineering/rop-009-evidence.md)

## Desenvolvimento

Cada capacidade deve ser construída incrementalmente e manter regras de negócio testáveis sem depender do modelo. Antes de adotar uma solução entre alternativas razoáveis para uma parte central de AI Engineering, documente as opções e a recomendação em `docs/decisions/`.
