# ROP-007 — Evidências da fundação PostgreSQL

Execução de `db-foundation-v1`, issue [#7](https://github.com/raphaelgarcia7/rentalops-agent/issues/7), corpo aprovado com `updatedAt=2026-10-03T12:26:15Z`; versão reconfirmada antes do commit em 2026-10-03. Executor GPT-6.1 Sol/high. Base: `2bbac480ae2e082099181b364cd1ab92e7914ffa` (`origin/develop`); branch `codex/7-postgres-foundation`. Os resultados locais abaixo correspondem ao código deste commit de implementação. Revisão independente, verificações remotas e integração são etapas posteriores do coordenador, vinculadas ao SHA final.

O checkout usado foi `C:/Users/Raphael/.codex/worktrees/rentalops-postgres/rmg-chatbot`. A raiz compartilhada suja foi somente lida para padrões, regras, delivery e ADR-001. Não houve cópia de mudanças acumuladas, alteração de journal/lock, publicação de workflow, alteração de GitHub, push ou merge pelo executor.

O coordenador confirmou por API autenticada somente de leitura, em 2026-10-03: develop `protected=false` no SHA da base acima; endpoint de proteção 404; regras aplicáveis da branch 200 com lista vazia; rulesets incluindo parents 200 com lista vazia; workflows 200 com `total_count=0`. Ausência confirmada, não CI aprovada; integração permitida pela autorização do responsável enquanto ROP-006 permanece pendente. O coordenador repetirá os checks aplicáveis ao head após publicar PR. O responsável também separou autenticação por senha em ROP-021 e Google em ROP-022, sem alterar o escopo de ROP-007.

## Relação entre critérios e evidências

| Critério | Evidência local | Estado |
| --- | --- | --- |
| AC-01 | `uv sync --project backend --locked`; PostgreSQL 17.10 real; configuração explícita e precedência de ambiente em `tests/unit/test_configuration.py`; Gitleaks; nenhuma credencial real usada | Atendido localmente |
| AC-02 | `test_migrations_idempotent_and_disposable_downgrade`: users/alembic_version, nenhuma conta inicial, segunda aplicação preserva UUID/dado e downgrade/upgrade somente no schema próprio. CLI upgrade duas vezes/current reproduzido em outro banco descartável | Atendido localmente |
| AC-03 | `test_identity_persists_uuid_utc_normalized_email_and_updated_time`, `test_database_normalizes_direct_sql_and_enforces_constraints`, `test_concurrent_duplicate_has_exactly_one_commit`: UUID preservado, timestamps com offset UTC, update no banco, ativo/inativo persistidos, trim/lowercase, vazio/nulo/321 recusados e 320 aceitos. Duas tentativas concorrentes: um commit e uma rejeição pelo PostgreSQL | Atendido localmente |
| AC-04 | Falha após escrita parcial não persiste o registro; método close verificado e pool sem conexões emprestadas; próxima sessão funciona. Recuperação na mesma sessão após rollback explícito e saída sem commit cobertas. Importação em subprocesso com conexão/engine/DDL proibidos | Atendido localmente |
| AC-05 | Health mantém contrato 200 sem banco; readiness 200 real, 503 por porta sem serviço, configuração ausente/malformada/SQLite e falha sintética. Resposta e logs capturados sem senha, URL, SQL ou traceback. Echo/echo_pool desativados e parâmetros ocultos | Atendido localmente |
| AC-06 | Onze casos de alvo inseguro recusados antes de conexão, incluindo remoto, SQLite, ausente, mesmo banco com alias/credencial diferente, nome não test e query redirecionadora. Endereço e porta explícitos resistem a PGHOSTADDR/PGPORT. Outro namespace sintético e lista de tabelas public preservados. Schema próprio UUID validado antes de cleanup. Zero schemas de teste ao fim | Atendido localmente |
| AC-07 | README, `.env.example`, `infra/database/README.md`; comandos locked sync, migração, suíte e recuperação reproduzidos; fronteira ROP-021 e próximos cadastros descrita | Atendido localmente |
| AC-08 | Pipeline abaixo, screenshots de regressão e Gitleaks; nenhum teste/asserção removido ou relaxado. Checks remotos atuais devem ser confirmados pelo coordenador antes da integração; ausência não será chamada de aprovação | Parte local atendida; gate remoto do coordenador |
| AC-09 | Base e código entregues para revisor GPT-6 Sol/high em contexto separado; PR mesmo repo/base develop e squash com precondição de SHA ainda não executados pelo executor | Pendente de revisão/integração; task não declarada Done |

## Resultados locais

Ambiente: Windows, Python 3.14.7, uv 0.12.12, Node 24.18.0, npm 11.16.0. PostgreSQL `17.10 on x86_64-windows, compiled by msvc-19.44.35227, 64-bit`; SQLAlchemy 2.0.54, Psycopg/Psycopg-binary 3.3.6, Alembic 1.20.0.

| Verificação | Resultado final |
| --- | --- |
| Locked sync backend | Exit 0; 83 pacotes resolvidos, 82 verificados no ambiente Windows |
| Ruff lint backend | Exit 0; All checks passed |
| Ruff format --check backend | Exit 0; 15 arquivos formatados |
| mypy estrito fontes | Exit 0; sem problemas em 5 fontes |
| pytest completo | Exit 0; 40 passed (30 unitários + 10 integrações PostgreSQL), zero skips; 2 warnings de dependências |
| pip-audit de export do lock, todos grupos, sem pacote local | Exit 0; No known vulnerabilities found |
| npm ci | Exit 0; 243 pacotes instalados, 244 auditados; zero vulnerabilidades |
| ESLint | Exit 0 |
| Prettier --check | Exit 0; todos os arquivos aprovados |
| Vitest | Exit 0; 1 arquivo, 9 passed |
| TypeScript + Vite produção | Exit 0; build concluído |
| npm audit --audit-level=high | Exit 0; zero vulnerabilidades, inclusive níveis inferiores |
| Playwright + axe contra produção | Exit 0; 40 passed, 4 projetos Chromium; nenhum retry/skip |
| Gitleaks 8.30.1 histórico Git e diff staged | Nenhum segredo encontrado; ferramenta oficial verificada contra SHA256 publicado |
| git diff --check | Exit 0 |

Uma verificação negativa adicional retirou `TEST_DATABASE_URL` e executou a integração de migrações: houve exatamente um erro de setup esperado (`TEST_DATABASE_URL is required for integration`), sem skip, conexão ou schema criado. Esse teste de recusa não substitui a execução completa aprovada acima.

Falhas iniciais corrigidas: configuração do módulo no uv_build, ausência de `__init__.py` nos pacotes de testes, tradução de URL malformada e formato antes da aplicação de Ruff. pip-audit identificou 3 avisos em urllib3 2.7.0, corrigidos por atualização transitiva do lock para 2.8.0, sem ignore/exceção. Prettier detectou finais CRLF do checkout Windows; o formatter normalizou arquivos sem diff de conteúdo do frontend. `.gitattributes` fixa LF somente em `frontend/**` para tornar checkouts futuros reproduzíveis; nenhum teste ou feature de UI foi alterado.

Warnings remanescentes: Starlette recomenda httpx2 em vez de httpx e emite aviso sobre alias AnyIO BlockingPortal; não afetam os testes aprovados. pip-audit informa aviso de uso de --no-deps embora o export inclua pins/hashes de todos os grupos. Playwright informa NO_COLOR/FORCE_COLOR. Nenhum warning foi convertido em skip ou usado para esconder falha.

## Regressão visual e limites

O frontend permanece estático. O navegador real Chromium acessou home, Catálogo, Clientes, Locações e 404 no build de produção servido em `127.0.0.1:4173`. A suíte existente verificou larguras 320, 390, 768 e 1440, teclado/skip link/foco/outline, histórico/refresh, links de recuperação, orçamento de scrollbar em 305 px, paisagem curta 844x390, reduced motion, ausência de overflow, alvos mínimos e axe WCAG 2 A/AA, 2.1 AA e 2.2 AA. Vinte auditorias de rota/viewport não apresentaram violações axe.

Capturas geradas em `frontend/test-results/evidence/`, relatório em `frontend/playwright-report/` (ignorados). O executor inspecionou visualmente `mobile-320-home.png`, `mobile-390-keyboard-focus.png`, `tablet-768-clientes.png` e `desktop-1440-home.png`: texto legível, navegação disponível, foco visível e conteúdo sem corte nessas capturas. A suíte também gerou imagens das demais rotas. Não houve comparação de pixels com baseline, teste de todos os dispositivos reais, zoom de navegador ou validação operacional pela locadora. Nenhum fluxo de negócio novo, loading/erro comercial, cadastro ou autenticação foi afirmado como testado.

## Instância, logs e reprodução pelo revisor

Diretório externo ao Git: `C:/Users/Raphael/.codex/tmp/rop007-postgres-20261003-5d9bf762`. Cluster: subdiretório `data`. Foi criado com ferramentas oficiais PostgreSQL já instaladas; nenhuma configuração/autenticação/database do serviço existente foi alterada e nenhuma senha foi tentada. Porta inicial 55437 recusada pelo Windows antes de abrir listener; porta 15437 validada e utilizada. Listener confirmado somente em `127.0.0.1:15437`; PID principal `10176` no momento da entrega. Esse é o único serviço de teste preservado deliberadamente para revisão. O preview Playwright é encerrado pela própria suíte.

`trust` existe somente neste cluster descartável local, sem dados pessoais ou segredos; `rentalops_test` é superuser sintético e qualquer processo local pode acessá-lo. Não representa configuração de produção nem conta padrão do produto. Bancos criados: `rentalops_test` para schemas exclusivos da suíte e `rentalops_migration_test` para reproduzir a CLI (users vazio, alembic_version no head). O cluster inteiro contém apenas dados sintéticos.

Na raiz do worktree, o revisor pode executar:

```powershell
$env:TEST_DATABASE_URL='postgresql+psycopg://rentalops_test@127.0.0.1:15437/rentalops_test'
uv sync --project backend --locked
uv run --project backend pytest backend/tests -q
```

Não definir `DATABASE_URL` para esse mesmo alvo. Se desejar reproduzir a CLI isolada, use o banco `rentalops_migration_test` para DATABASE_URL e rode os comandos Alembic do README. Nenhum downgrade manual foi executado: downgrade ocorre exclusivamente na suíte/schema próprio.

Logs sem dados reais, no diretório externo acima: `backend-quality.log`, `pytest-final.log`, `frontend-quality.log`, `playwright-final.log`, `missing-test-url.log`, `postgres.log`, `audit-requirements.txt`, `gitleaks-history.json` e `gitleaks-diff.json`. Arquivos da ferramenta Gitleaks também estão nesse diretório. Logs PostgreSQL podem conter SQL/dados sintéticos de testes; nunca utilizar esse padrão de retenção para dados pessoais. Nenhuma credencial real foi exportada para logs.

Após revisão, o coordenador pode parar exatamente este cluster, preservando os arquivos:

```powershell
& 'C:/Program Files/PostgreSQL/17/bin/pg_ctl.exe' -D C:/Users/Raphael/.codex/tmp/rop007-postgres-20261003-5d9bf762/data -m fast -w stop
```

Não foi solicitado apagar o diretório. Nenhuma limpeza abrangente foi executada. Zero namespaces `rentalops_test_<UUID>` permaneceram depois da suíte e da recusa sem configuração.

## Entrada de revisão

Revisar `config.py`, `database.py`, `models.py`, `main.py`, `migrations/env.py`, `0001_team_identity.py` e os testes de segurança/integração. README documenta que readiness é conectividade, não esquema atualizado, e que migrações são explícitas. Sessões síncronas e curtas seguem decisão aprovada; não há container DI, repositório genérico, aplicação de DDL em import/startup ou transação atravessando espera de modelo. E-mail tem normalização básica e limite; validação completa de endereço/login pertence à ROP-021.

Sem novo frontend, credenciais, Google, roles, contas semeadas/provisionadas, reservas, estoque, contratos, IA, checkpointing, deployment ou alterações de proteção/CI. ROP-021 permanece pendente. O estado remoto do PR/checks/base e merge confirmado serão registrados pelo coordenador; testes locais não comprovam esses gates.
