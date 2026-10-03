# ROP-021 — Evidências de autenticação por senha

Plano humano `auth-password-v2`, [issue #21](https://github.com/raphaelgarcia7/rentalops-agent/issues/21), aprovação no Harness em 2026-10-03, `updated_at=2026-10-03T13:12:54Z`. O executor consultou o corpo completo pelo conector GitHub e reconfirmou essa revisão depois da implementação, antes do commit. Dependências #3/#7 Done e integração #7 foram verificadas pelo coordenador antes do despacho. O campo Status do Project é autoritativo; este documento não substitui o quadro.

Executor configurado `gpt-6.1-sol/high`, sem planner/substituição. Checkout `C:/Users/Raphael/.codex/worktrees/rentalops-auth/rmg-chatbot`, branch `codex/21-password-auth`. Base: `f7be6028ec2c88088f4385c9ecacc406ad16e62a`. Head do código implementado e validado: `0582a1d35885f230e4a55a29bec0022ec760a500`. Este registro é acrescentado em um commit somente documental posterior; o SHA exato desse head de entrega fica no journal compartilhado e no relatório de handoff, pois um arquivo não pode conter o SHA do próprio commit. O revisor deve usar o head completo da entrega, comparado à base acima.

Raiz compartilhada `C:/Projects/praxis/rmg-chatbot` somente lida para regras, padrões, delivery e ADR-001. Nenhum arquivo acumulado do usuário foi copiado/publicado. Owner do lock: `rop021-auth-20261003-3716784f`; checkpoints preservaram todos os campos anteriores. O executor não reivindicou/liberou o lock, não mudou Project/GitHub, não publicou branch/PR nem fez merge/deploy. Essas etapas pertencem ao coordenador após a revisão independente.

## Critérios e evidências

| AC | Evidência exata | Resultado local |
| --- | --- | --- |
| AC01 | `test_closed_access_argon2id_idempotent_normalization_and_equal_accounts`; quatro execuções de `auth-live.spec.ts`: conta previamente criada define sua senha, entra e tem cookie; inexistente/inativo/sem senha recebem 401 genérico. Sem endpoint de cadastro, senha padrão, Google ou roles | Atendido |
| AC02 | `test_cli_exact_target_idempotent_no_secret_and_failure`, normalização/idempotência, conta vizinha preservada; create-user retorna UUID/created ou existing, não sobrescreve hash nem reativa. CLI real usa o mesmo serviço, com exit 1 em falha | Atendido |
| AC03 | `test_link_boundaries_wrong_purpose_new_link_and_single_use`, `test_access_link_cannot_overwrite_initialized_account`, `test_two_concurrent_consumers_exactly_one_commits`; emissão invalida link anterior; 29min59s válido/30min inválido, finalidade recusada, consumo repetido recusado; dois consumidores = um commit/uma rejeição. Constraints PostgreSQL verificadas. Fragmento removido e token somente no corpo em Vitest/Playwright | Atendido |
| AC04 | `test_recovery_generation_reset_deactivation_and_restart_revocation`: logout só atual; gerar recuperação imediatamente revoga todas; definir senha revoga sessões abertas depois da emissão e links restantes; desativar preserva identidade e revoga tudo. Outra instância do serviço confirma persistência; fluxo real no navegador testa recuperação/desativação | Atendido |
| AC05 | `test_expiry_exact_boundaries_polling_activity_throttle_and_absolute`: relógio injetável, 59min59s/1h e 12h exatos, throttle 29s/30s, atividade não estende absoluta. Consultas não renovam. Browser simula polling/inatividade e não envia atividade de fundo; não existe Manter conectado | Atendido |
| AC06 | `test_http_contracts_csrf_protected_identity_cookie_no_secret_errors`, `test_production_cookie_secure_and_login_ignores_supplied_cookie`, testes de configuração e limites. API interna responde 401 sem sessão, UUID vem do backend, payloads extra/actor_id recusados, origem ausente/indevida 403. Cookie HttpOnly/Lax/Secure produção/sem Domain/identificador novo; hash apenas no banco. Erros/logs capturados sem payload/senha/token/SQL. Não há operação comercial ainda: `current_identity` é a fronteira reutilizável para as tasks seguintes | Atendido no escopo disponível |
| AC07 | Migração incremental `0002_password_auth` preserva users existente; aplicar duas vezes mantém identidade, downgrade para 0001 remove somente auth e preserva identidade, upgrade novamente funciona. Unicidade/finalidade, rollback de falha depois de escrita, consumo concorrente e limite concorrente em PostgreSQL 17.10. Reinício do serviço não limpa tentativas/revogação. Zero SQLite/skip/fallback | Atendido |
| AC08 | Vitest 23; Playwright 68 contra build produção, quatro larguras 320/390/768/1440. Entrar/definir/logout/loading/401/400/503/revogação/expiry, foco/teclado, reduced motion, 32 auditorias axe sem violações. Rascunho sintético montado preservado ao sair/reentrar; guarda mantém componentes em memória em expiração/revogação. Não existe formulário comercial nesta entrega; reload/fechamento não garante rascunho | Atendido com limites descritos |
| AC09 | Pipeline local abaixo e Gitleaks limpos. Revisão independente `gpt-6-sol/high` do head final e consulta a checks/proteções atuais ainda são gates do coordenador | Local aprovado; revisão/remoto pendentes |
| AC10 | README documenta comandos privados, primeiro acesso/recuperação, origem/proxy/cookie, tempo/limites e teste seguro; `.env.example` não contém chave funcional. PR não draft mesmo repo/develop, base/head atuais e squash confirmado ainda são gates do coordenador. Não declarar Done antes do merge | Documentação atendida; integração pendente |

## Pipeline local da entrega inicial (histórico)

Ambiente: Windows, Python 3.14.7, uv 0.12.12, Node 24.18.0/npm 11.16.0, PostgreSQL 17.10 real, Argon2-cffi 25.1.0 (Argon2id padrão da biblioteca consolidada). Nenhuma API de IA, credencial real, envio externo, conta do produto ou serviço de produção foi usado.

| Comando/verificação | Resultado exato |
| --- | --- |
| `uv sync --project backend --locked` | Exit 0; 87 pacotes resolvidos, 86 verificados |
| `uv run --project backend ruff check backend C:/Projects/praxis/rmg-chatbot/infra/automation C:/Projects/praxis/rmg-chatbot/infra/tests` | Exit 0, All checks passed |
| `uv run --project backend ruff format --check backend C:/Projects/praxis/rmg-chatbot/infra/automation C:/Projects/praxis/rmg-chatbot/infra/tests` | Exit 0, 24 arquivos formatados |
| `uv run --project backend mypy --config-file backend/pyproject.toml` | Exit 0, 8 fontes sem erros, strict |
| `uv run --project backend pytest backend/tests C:/Projects/praxis/rmg-chatbot/infra/tests -q` | Exit 0, **76 passed**, 2 warnings, 30.64s; backend 66 (43 unit + 23 PostgreSQL), infra compartilhada 10; zero skips |
| `uv export --project backend --locked --all-groups --no-emit-project --format requirements-txt -o <diretório externo>/rop021-audit-requirements.txt --quiet` + `uv run --project backend pip-audit -r <export> --disable-pip --no-deps` | Exit 0, No known vulnerabilities found, incluindo dev |
| `npm ci` em frontend | Exit 0; 243 instalados, 244 auditados, zero vulnerabilidades |
| `npm run lint` / `npm run format:check` | Exit 0 / Exit 0, nenhum ignore novo de regra |
| `npm test` | Exit 0, 2 arquivos/**23 passed**; 9 routing + 14 auth |
| `npm run build` | Exit 0; TypeScript e Vite produção; 103 módulos transformados |
| `npm audit --audit-level=high` | Exit 0, zero vulnerabilidades inclusive inferiores |
| `npm run test:e2e` com TEST_DATABASE_URL seguro | Exit 0, **68 passed**, 52.3s, zero retry/skip: 40 regressões workspace + 24 auth controlados + 4 auth com API/PostgreSQL reais |
| Axe WCAG 2 A/AA, 2.1 AA e 2.2 AA | 32 auditorias (workspace, login com erro, definição de senha e home autenticada real), zero violações |
| Gitleaks 8.30.1 `git --redact` / diff staged via `stdin --redact` | Exit 0, nenhum segredo; histórico antes da publicação continha 8 commits; scan staged incluiu todos os novos fontes/testes |
| `git diff --check` e `git diff --cached --check` | Exit 0 |

Infra compartilhada foi executada para regressão do journal, sem copiar/modificar seus arquivos no checkout. O clone de develop ainda não possui o workflow e essas fontes de automação não são parte desta PR. Não confundir a execução local com CI remota. O coordenador verifica os checks/proteções existentes antes de integrar e registra eventual ausência confirmada conforme delivery; o executor não afirmou checks remotos inexistentes como aprovados.

Falhas iniciais corrigidas, não escondidas: inferência `Literal[True]` da biblioteca Argon2 no mypy; adaptação explícita das expectativas da migração incremental; teste de input usava string com 13 caracteres como se fosse curta (corrigido para 5); ordem não especificada de nomes de tabela (comparação por conjunto exato); fixture da CLI sem configurar o banco (injeção corrigida); extração da UI e regras React/TypeScript; testes de browser precisavam aguardar autenticação assíncrona, medir somente controles visíveis e instalar relógio antes dos timers. Primeira rodada de browser: 12 falhas/52 passes; final: 68 passes. Nenhum teste convertido em skip nem asserção comercial removida/enfraquecida.

Warnings preservados: Starlette recomenda httpx2 e avisa alias AnyIO BlockingPortal; pip-audit alerta sobre --no-deps apesar do export locked incluindo pins/hashes de todos os grupos; Playwright informa NO_COLOR/FORCE_COLOR. Não representam testes omitidos ou auditoria incompleta.

## Segurança, banco e limpeza

Foi reutilizado somente o cluster descartável anteriormente verificado de ROP-007: `C:/Users/Raphael/.codex/tmp/rop007-postgres-20261003-5d9bf762/data`. Binários oficiais `C:/Program Files/PostgreSQL/17/bin`. Reinício exigiu parâmetros explícitos `-h 127.0.0.1 -p 15437 -c timezone=UTC`; uma primeira tentativa sem esses parâmetros não iniciou listener e foi corrigida. Listener confirmado apenas `127.0.0.1:15437`, PID principal `52696` nesta execução. Serviço existente `postgresql-x64-17` permaneceu Running; nenhum banco/configuração/senha desse serviço foi alterado.

Banco `rentalops_test`, usuário sintético local `rentalops_test`, trust somente no cluster descartável, sem dados pessoais reais. Cada pytest usa namespace UUID validado; browser harness reutiliza a mesma fixture/recusa de alvo inseguro e cria seu próprio namespace, nunca aplica DDL ao app principal em import/startup. O harness está em `backend/tests/browser_server.py`, só inicia por comando explícito, bind loopback 8000, proxy headers/access log desabilitados. Controles `__test` estão somente no wrapper de teste, nunca registrados em `rentalops_api.main:app`.

Na primeira rodada real de browser, terminar o processo Windows deixou um namespace descartável. Foi acrescentado teardown explícito antes de encerrar o servidor. O namespace antigo `rentalops_test_d4ac4f2027454c32be5bd7ee68685bcf` foi verificado por leitura: exatamente quatro contas sintéticas `browser-…@example.invalid`, revision 0002, sem outras identidades. Somente esse namespace foi removido, sem apagar banco/cluster/diretórios; dados descartáveis podem ser regenerados pelos testes. Rodada final usou teardown novo com sucesso. Consulta final `SELECT count(*) FROM pg_namespace WHERE nspname LIKE 'rentalops_test_%'` retornou **0**. Portas 8000/4173 encerradas ao fim. Cluster 15437 preservado para revisão; owner do lock continua ativo.

Export de auditoria e relatórios Gitleaks ficam no diretório externo acima: `rop021-audit-requirements.txt`, `rop021-gitleaks-history.json`, `rop021-gitleaks-diff.json`. Log PostgreSQL existente contém somente dados sintéticos de testes; não aplicar essa retenção a dados reais. Nenhum link/senha/token/chave real consta no documento/journal/capturas. CLI emite URL privada somente para o operador entregá-la manualmente; agente não criou contas reais nem imprimiu resultado privado.

## UI inspecionada e limites

Capturas ignoradas em `frontend/test-results/evidence/`, relatório `frontend/playwright-report/`. Inspeção visual explícita: `mobile-320-auth-login-error.png`, `mobile-390-auth-set-empty.png`, `tablet-768-auth-link-error.png`, `desktop-1440-auth-live-deactivated.png`. Texto legível, feedback próximo à ação, foco visível, campos/botões sem corte horizontal nessas imagens; em 320 px o conteúdo rola verticalmente. Todas as evidências limpam os campos de senha; a captura live limpa também e-mail. A suíte verifica cada largura, navegação/skip link/foco/teclado, alvos de pelo menos 44 px e reduced motion. Viewports Chromium não comprovam todos os dispositivos, pixel baseline, zoom de navegador, leitor de tela ou validação operacional pela equipe.

Componentes permanecem montados mas ocultos/inertes quando acesso termina, preservando estado em memória. Teste Vitest mantém rascunho sintético ao sair/reentrar; testes de timers verificam expiry/revogação. Uma resposta atrasada de polling depois de logout é ignorada por geração de estado, com regressão dedicada. Não há formulário comercial para simular dado real; recarregar/fechar a página perde estado em memória.

Limitações documentadas: atrás de proxy sem configuração explícita, o limite por origem usa peer direto e pode ser compartilhado pelos usuários, sem confiar em X-Forwarded-For arbitrário. Retenção de tentativas/auditoria, backup e configuração real de produção exigem tasks operacionais; nenhuma implantação foi feita. Futuras rotas comerciais precisam consumir `current_identity`; esta entrega demonstra proteção/autoria pela rota interna, sem implementar negócios excluídos.

## Reprodução e gates restantes

No checkout desta entrega:

```powershell
$env:TEST_DATABASE_URL='postgresql+psycopg://rentalops_test@127.0.0.1:15437/rentalops_test'
uv sync --project backend --locked
uv run --project backend pytest backend/tests -q
cd frontend
npm ci
npm run build
npm run test:e2e
```

Não definir DATABASE_URL para o mesmo alvo; não apontar o harness a um banco existente de desenvolvimento/produção. O revisor também deve ler regras/padrões/delivery/ADR aprovados na raiz compartilhada, preservando alterações do usuário. Ao finalizar revisão, somente o coordenador pode parar exatamente esse cluster com `pg_ctl -D <diretório explícito acima> -m fast -w stop`, preservando arquivos; não há autorização para limpeza abrangente.

Pendentes: revisão independente `gpt-6-sol/high` em contexto separado do head/base atuais, PR mesmo repo/base develop sem draft, verificações remotas aplicáveis e squash com precondição de head, confirmação de merge e atualização Done. Executor interrompe novas alterações após o handoff; correções somente se devolvidas pela revisão. Nada de main/deploy/bypass, Google/OAuth/OIDC, SMTP, gestão de roles/usuários por tela, cadastros/estoque/contratos ou IA foi implementado.

## Correção da revisão independente — rodada 1

Revisão independente identificou um bloqueio real: a entrega inicial calculava Argon2 antes de validar o link e não limitava tentativas em `/auth/password/set`. Um cliente não-browser pode forjar Origin, portanto a proteção de origem não era um limite de CPU. O coordenador devolveu exatamente esse ponto ao mesmo executor, sem novo plano, publicação ou substituição de modelo. Revisão aprovada da issue reconfirmada pelo conector em `2026-10-03T13:12:54Z` antes do commit de correção.

Head anterior: `8dd376bb737236694e6d9daefcbf595ae7efe15d`. **Head do código corrigido e validado: `580d6c42a8baf703fa0bae8c3123ad501c17ed63`**. Base permanece `f7be6028ec2c88088f4385c9ecacc406ad16e62a`. Este adendo fica em commit documental posterior; o head final completo será registrado no journal e no handoff. Os resultados seguintes substituem os totais históricos acima para a revisão atual.

### Abordagem e cobertura AC03/AC06/AC07/AC08

Migração incremental `0003_password_set_limits` adiciona apenas o registro persistente de tentativas de definição de senha, com identificador do token e peer direto pseudonimizados por HMAC em namespaces próprios, horário e UUID. Não armazena token bruto, IP, senha ou e-mail. A API determina o peer, não aceita esse valor no payload nem confia em X-Forwarded-For. Nenhuma configuração de força Argon2 foi reduzida.

Antes de Argon2, uma transação curta serializa os contadores PostgreSQL e admite no máximo **10 tentativas por token e 30 por peer em 15 minutos**, separadamente do limite de falhas de login. Toda tentativa admitida é persistida, inclusive link inválido, concorrente ou falha posterior. A mesma transação faz a verificação barata de existência, validade, finalidade, conta ativa, consumo/revogação e primeiro acesso ainda não inicializado. Link inelegível retorna 400 sem chamar o hasher; limite retorna 429. Hashing ocorre depois do commit, sem transação/conexão/lock de conta ou contador mantido. A transação final revalida o link sob lock da conta e mantém consumo único, alteração da senha, revogação e auditoria atômicos. Falha de hash retorna 503 genérico e não consome o link nem devolve o orçamento.

Regressões PostgreSQL novas (17 casos efetivamente executados, não mocks de persistência):

| Teste | Evidência |
| --- | --- |
| `test_ineligible_password_link_never_reaches_hasher` (7 parâmetros) | Desconhecido, expirado, consumido, revogado, inativo, finalidade inválida e acesso já inicializado: 400, zero chamadas ao hasher, tentativa persistida e credencial intacta. Finalidade inválida usa fault injection somente no schema UUID descartável; as constraints normais continuam testadas. |
| `test_password_set_invalid_http_attempts_persist_without_hash_or_secret` | POST anônimo com Origin autorizado forjado: 10 respostas 400 e próxima 429 após nova instância do serviço; sem hash, segredo nos logs ou confiança em forwarded peer. |
| `test_password_set_origin_budget_cannot_be_evaded_with_random_tokens` | Tokens aleatórios distintos não evitam 30/peer; nova instância preserva o limite; 14min59s ainda 429, exatamente 15min permite nova tentativa. |
| `test_concurrent_password_set_budget_bounds_invalid_tokens_without_hash` | 12 chamadas concorrentes inválidas: exatamente 10 respostas 400 e 2 respostas 429; zero hashes. |
| `test_concurrent_valid_password_attempts_bound_hashes_and_consume_once` | 12 chamadas concorrentes de link válido: 10 hashes admitidos, exatamente um commit, 9 recusas 400 e 2 recusas 429; tentativa posterior por outro peer também limitada por token. Enquanto hashes estão pausados, pool tem zero conexões ocupadas; nenhum lock longo mantém a conta indisponível. |
| `test_link_revalidated_when_state_changes_during_hash` (4 parâmetros) | Emissão de novo link, desativação, expiração exata e outro consumo durante hash recusam a escrita antiga; mutação concorrente não é bloqueada pelo hash e senha vencedora não é sobrescrita. |
| `test_hash_failure_does_not_consume_link_or_refund_persistent_budget` | Falha do hasher: 503, link/senha preservados, orçamento debitado; tentativa seguinte pode concluir uma vez. |
| `test_password_set_limit_migration_preserves_auth_and_downgrades_only_attempts` | Upgrade 0002→0003, repetição idempotente, downgrade 0003→0002 preservam identidade e tabelas de auth; somente tentativas removidas; reupgrade funcional. |

Frontend de produção permaneceu sem alteração. Adicionados um teste Vitest e quatro casos Playwright do estado 429 de definição de senha: feedback de aguardar 15 minutos, sem falsa confirmação/acesso, fragmento removido, foco/teclado, overflow e axe. Capturas novas `mobile-320-auth-set-limited.png`, `mobile-390-auth-set-limited.png`, `tablet-768-auth-set-limited.png`, `desktop-1440-auth-set-limited.png` foram inspecionadas visualmente nas quatro larguras; feedback legível, foco visível e controles sem corte horizontal. Campos foram limpos antes de capturar. Permanecem as limitações de dispositivos/leitores de tela da inspeção inicial.

### Pipeline completa repetida na correção

| Comando/verificação | Resultado exato |
| --- | --- |
| `uv sync --project backend --locked` | Exit 0, 87 resolvidos/86 verificados |
| `uv run --project backend ruff check backend C:/Projects/praxis/rmg-chatbot/infra/automation C:/Projects/praxis/rmg-chatbot/infra/tests` | Exit 0, All checks passed |
| `uv run --project backend ruff format --check backend C:/Projects/praxis/rmg-chatbot/infra/automation C:/Projects/praxis/rmg-chatbot/infra/tests` | Exit 0, 25 arquivos formatados |
| `uv run --project backend mypy --config-file backend/pyproject.toml` | Exit 0, 8 fontes, strict |
| `uv run --project backend pytest backend/tests/integration/test_auth.py -q` | Exit 0, **30 passed**, 2 warnings, 18.97s; 13 anteriores + 17 novos |
| `uv run --project backend pytest backend/tests C:/Projects/praxis/rmg-chatbot/infra/tests -q` | Exit 0, **93 passed**, 2 warnings, 39.15s; backend 83 (43 unit + 40 PostgreSQL reais) + infra 10; zero skips |
| `uv export --project backend --locked --all-groups --no-emit-project --format requirements-txt -o <diretório externo>/rop021-correction1-audit-requirements.txt --quiet` + `uv run --project backend pip-audit -r <export> --disable-pip --no-deps` | Exit 0, No known vulnerabilities found, incluindo dev |
| `npm ci` / `npm run lint` / `npm run format:check` | Exit 0 cada; 243 instalados/244 auditados, zero vulnerabilidades; lint/formatação aprovados |
| `npm test` | Exit 0, **24 passed**, 2 arquivos, 57.81s; 9 routing + 15 auth |
| `npm run build` | Exit 0, TypeScript/Vite produção, 103 módulos; mesmos assets de produção, sem alteração de UI funcional |
| `npm audit --audit-level=high` | Exit 0, zero vulnerabilidades |
| `npm run test:e2e` com TEST_DATABASE_URL seguro | Exit 0, **72 passed**, 55.8s; 40 workspace + 28 auth controlados + 4 fluxos auth reais com API/PostgreSQL; zero skip/retry |
| Axe nos quatro viewports | **36 auditorias, zero violações**; inclui os quatro novos estados 429 |
| Gitleaks 8.30.1 `git --redact` / diff staged `stdin --redact` | Exit 0, nenhum segredo; staged incluiu todos os novos fontes/testes/migração; histórico inicial da correção 10 commits; scan final do head completo registrado no handoff |
| `git diff --check` / `git diff --cached --check` | Exit 0 |

Falha preservada da primeira execução dirigida: **1 failed / 29 passed**. A observação de pool do teste concorrente ainda incluía transações curtas de outros threads porque a sincronização estava incompleta. Foram adicionadas barreiras/evento para pausar todos os dez hashes e esperar as duas recusas concluírem antes da leitura. A asserção exata de **zero conexões ocupadas** foi mantida; rodada seguinte 30/30 e pipeline completa 93/93. Não houve skip, redução de Argon2 ou relaxamento da asserção. Warnings permanecem Starlette/httpx/AnyIO, pip-audit --no-deps, Playwright NO_COLOR/FORCE_COLOR e avisos Git LF/CRLF, sem erros de pipeline.

Cluster descartável permanece exatamente no diretório explicitado acima, somente `127.0.0.1:15437`, PID `52696`. Serviço Windows existente `postgresql-x64-17` reconfirmado Running, sem mutação. Consulta de limpeza depois de toda a suíte browser retornou **0 schemas `rentalops_test_%`**; listeners 8000/4173 encerrados. Cluster preservado para revisão. Não foram criadas/alteradas contas reais nem enviados links ou e-mails. Relatórios adicionais externos: `rop021-correction1-audit-requirements.txt`, `rop021-correction1-gitleaks-history.json`, `rop021-correction1-gitleaks-diff.json`. Lock compartilhado continua com o mesmo owner, não liberado pelo executor.

Handoff da rodada 1 exige **nova revisão independente `gpt-6-sol/high` do head final exato** antes de qualquer publicação/PR/integração. Executor não alterou issue/Project, não fez push/merge/deploy e para após entregar commits limpos. Gates remotos/PR/squash/Done continuam exclusivamente com o coordenador.
