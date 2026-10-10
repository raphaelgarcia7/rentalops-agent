# ROP-011 — reservations-v1: evidências do executor

## Identidade e limites

Plano humano #11, `updated_at=2026-10-09T00:27:50Z`, SHA-256 UTF-8 do body
`50c88df8b6e7b5ff04510d34a213f8da5ba433ad5b883566ca60e76d59ec9d0e`.
O plano completo, políticas, standards, regras e ADR001 foram lidos antes da
implementação. Rechecagem viva após a implementação: issue aberta, mesma revisão
e body exatamente igual ao original. O coordenador verificou Project/dependências
diretas #10/#12 e transitivas, integração remota e promoção Ready/In progress.

Executor fixo `rentalops_executor`, `gpt-6.1-sol/high`, `/root/rop011_executor`.
Owner `rop011-reservations-20261010-50c88df8-run1`, lock compartilhado na raiz
`C:/Projects/praxis/rmg-chatbot`. Sem planner, executor paralelo ou troca de modelo.
Checkout isolado `C:/Users/Raphael/.codex/worktrees/rentalops-customers/rmg-chatbot`,
branch `codex/11-reservations`, base `5916965a5592489ddce7087fe97967ffd83fe223`.

Commits de código validados:

- `6cbb6808a70b4260f6831befd8328ac5488405da`: implementação vertical.
- `dbec8ac1eb6257ee24726764d65e23f993d9af56`: leitura indisponível não é vazio;
  regressões explícitas de capacidade real no orçamento API/UI.
- `13f02ece628ccc75a0aff467860efa64aa1ce847`: resultado desconhecido não exibe
  ausência antiga; erro5xx também preserva comando/chave para reconciliação.
- `992712c6996949627f1920c1ea1e20f2a2e6a593`: histórico do cliente usa somente
  os resumos reais paginados; remove ausência estática contraditória herdada #9.
- `71c111595a7f27aaf7f5f65f8031068bde6ce0f5`: teste adicional de duplo clique
  mantém promessa de confirmação pendente, verifica botão ocupado/desabilitado,
  somente um POST e nenhum sucesso antecipado; depois resolve e verifica um
  callback. Mudança somente de teste, sem alterar aplicação/build validado run17.

O SHA final, incluindo este relatório, fica no checkpoint e handoff; não existe
SHA autorreferente neste documento. Mudanças acumuladas da raiz e resultados #12
foram preservados, não publicados nem reutilizados como evidência desta entrega.

Escopo: confirmação explícita, única por orçamento, snapshots/histórico,
alocação atômica, capacidade simultânea, pendências separadas e integração dos
comandos reais #8/#10/#12. Não há hold/TTL, cancelamento, retirada, devolução física,
estados operacionais fictícios, #13/#14/#15, roles, IA, main ou deploy.

## Matriz do plano aprovado

Nomes abaixo pertencem a `backend/tests/integration/test_rentals.py`, salvo indicação.
Todos os testes PostgreSQL usam conexões reais e schemas UUID descartáveis.

| AC | Evidência determinística |
| --- | --- |
| RES-01 / AC histórico 1 | `test_explicit_confirmation_snapshot_demand_unique_replay_and_history`: total400/sinal200 conciliado, snapshots/ator/instante, recebimento+conciliação+preview sem alocação. `test_money_without_explicit_valid_reconciliation_cannot_confirm`: nenhum recebimento,100,dois100 e200 não conciliado recusados; suite #12 mantém anexo sem autoridade financeira. `test_stale_financial_commercial_expiry_and_backdate_guards`: versões atuais, reconciliação antiga, vencimento e retirada passada. `test_capacity_conflict_preserves_money_pending_replay_and_no_partial_allocation`: integral não dispensa capacidade. |
| RES-02 / AC histórico 2 | Demanda2arcos/5vasos de dois kits+avulso; `test_real_simultaneous_overlap_closed_boundaries_and_quotation_regression`: customizados, manutenção, trechos simultâneos e reservas futuras não sobrepostas; dia13 ocupado/dia14 livre. `unit/test_rental_contracts.py`: segmentos fechados e dia seguinte inclusive domingo/feriado. |
| RES-03 / AC histórico 3 | `test_two_postgres_connections_last_capacity_and_replay_concurrency`, incluindo produto com literalmente uma unidade apta; no máximo uma confirmação. `test_same_request_concurrent_and_commit_failure_roll_back_all`: mesma chave e rollback. Replay original antes de versões e mismatch409, sem duplicação. `test_confirmation_races_payment_revision_and_stock`: seis operações concorrentes, conciliação/correção/refund/revisão/baixa/manutenção. |
| RES-04 / R08-INV / R08-INACT / AC histórico 5 | `test_confirmed_snapshot_guard_catalog_and_financial_issues_keep_allocation`: preço/foto/inativação não reescrevem snapshot; revisão comum bloqueada; correção/refund preservam estoque e criam pendência financeira. `test_inventory_pending_insert_never_locks_quotation_after_product`: produto deliberadamente retido enquanto confirmação segura quotation e espera produto; impacto completa sem lock inverso. `test_stock_impact_and_movement_roll_back_together`: rollback movimento+pendência. |
| AC histórico 4 | Conflito preserva dinheiro, grava resultado409 idempotente e pendência identificável, zero alocação parcial; nova chave após ajuste permite confirmar e mantém evento original. UI não representa consulta/pagamento como confirmação. |
| RES-05 / R10-OVERLAP | Teste de fronteiras acima e `integration/test_rental_api.py`: preview público interno #10 passa a refletir compromissos2/5, disponível0. `frontend/e2e/reservations-live.spec.ts`: segunda proposta sobreposta exibe disponível0/pico1, dinheiro não desaparece, histórico do cliente distingue orçamento/reserva. `CustomersPage.test.tsx` verifica resumo confirmado com pendências e ausência de falso vazio; e2e verifica o mesmo após pagamento/confirmação reais. R11-RET/R11-LATE continuam na #14 e NÃO estão certificados aqui. |
| RES-06 | `integration/test_rental_api.py`: todas as rotas privadas, sessão401, Origin403, validação422, versões409, inexistência404, paginação/no-store, payload sem ator autorizado e conflito sem identidade de outro cliente. Proteção CSRF é o protocolo Origin/sessão existente #21, não um novo mecanismo. Frontend unitário/e2e: erros/loading/vazio/sucesso/desconhecido, duplo clique, replay da mesma chave, seleção preservada. Matriz visual abaixo. |
| RES-07 | Pipeline local registrado abaixo. Revisão independente do head/base, publicação/PR, checks remotos, squash develop e Project Done são gates posteriores do coordenador; NÃO são certificados por este relatório do executor. |

O protocolo de escrita permanece READ COMMITTED: advisory idempotência → quotation
→ rental existente → conta/receipts UUID → kits UUID → produtos UUID. Produto
persistido protege também a lacuna sem allocation. A capacidade é recalculada
depois do lock, não autorizada pelo preview. Pendência de impacto referencia
versão imutável, sem adquirir quotation/rental após produto. Estoque físico não
é reduzido pelo compromisso. A documentação de regras está em
[reservations-v1.md](../product/reservations-v1.md), sem copiar rascunhos da raiz.

## Ambiente, comandos e resultados

Artefatos privados, fora do Git: raiz compartilhada
`.rentalops/rop011-evidence/`. Diretórios run00..run18 são tentativas exclusivas;
nenhum rerun sobrescreve os originais. Comandos backend Windows partem do checkout;
comandos frontend partem de `frontend/`. Saídas completas ficam nos arquivos
indicados. Sem skips, retries ou relaxamento de assertions/timeouts/rate limits.

| Comando | Resultado / artefato |
| --- | --- |
| `uv run --project backend ruff check backend C:/Projects/praxis/rmg-chatbot/infra/automation C:/Projects/praxis/rmg-chatbot/infra/tests` | PASS, run17/ruff.txt |
| `uv run --project backend ruff format --check backend C:/Projects/praxis/rmg-chatbot/infra/automation C:/Projects/praxis/rmg-chatbot/infra/tests` | PASS,82 arquivos formatados, run17/ruff-format.txt |
| `uv run --project backend mypy --config-file backend/pyproject.toml` | PASS,40 fontes, run17/mypy.txt |
| `uv run --project backend pytest C:/Projects/praxis/rmg-chatbot/infra/tests -q` | FINAL Windows10 PASS,4.28s, run18/infra-windows.txt |
| Helper Linux `quality pytest backend/tests infra/tests -q` | FINAL453 PASS,2warnings,78.48s, run16/pytest.txt; unidade/integração/PG real/migrations/rollback/concorrência/idempotência e infra da raiz. |
| `pip-audit --requirement <export-all-groups-hashed> --no-deps --disable-pip --strict` | Windows+Linux: No known vulnerabilities found; run04/pip-audit-{windows,linux}.txt; export do lock uv/all-groups com92 pacotes/versões/hashes. Locks não mudaram depois. Aviso genérico da CLI sobre recomendar hashes retido, não escondido. |
| `npm run lint`, `npm run format:check` | FINAL PASS, run18/eslint.txt,prettier.txt |
| `npm test` (`vitest run`) | FINAL55/55,7 arquivos,53.92s, run18/vitest.txt |
| `npm run build` | FINAL PASS, TypeScript+Vite produção125 módulos1.39s, run18/build.txt; JS/CSS idênticos ao run17. |
| `npm audit --audit-level=low` | zero vulnerabilidades, run17/npm-audit.txt |
| `npx playwright test --project=<largura> --workers=1 --output=<run17/largura-results>` | Matriz FINAL: resultados/capturas registrados abaixo; Chromium sobre build de produção, harness novo por largura, retries0. |
| Gitleaks8.30.1 `git . --redact --log-opts=--all --no-banner` e stdin diff completo base..head | Resultados finais registrados no handoff/checkpoint, logs run18/gitleaks-{history,diff}-final.txt; nenhuma credencial publicada. |
| `git diff --check` / status / head / base | Validação final no handoff/checkpoint; relatório sozinho não substitui head exato. |

Warnings pytest: Starlette/httpx TestClient e alias BlockingPortal anyio depreciados
nas dependências existentes. Não foram suprimidos, nem dependências substituídas
fora do escopo para eliminar avisos.

Reprodução Linux (helper privado retido, sem imprimir URL/senha):

```powershell
wsl -d Ubuntu-24.04 -u rop004-rehearsal -- python3 /mnt/c/Users/Raphael/.codex/tmp/rop011-environment.py start
wsl -d Ubuntu-24.04 -u rop004-rehearsal -- python3 /mnt/c/Users/Raphael/.codex/tmp/rop011-environment.py quality pytest backend/tests infra/tests -q
```

Fixture nova ext4 `/home/rop004-rehearsal/rop011-BmdeGIrS`, UID1000/mode700,
PostgreSQL17 loopback15443, DB sintética dedicada. Arquivos de config600; venv e
backend/infra próprios em `source/`. Ferramentas oficiais gratuitas já existentes
foram reutilizadas por cópia, sem alterar a fixture #12. Não executar `prepare`
novamente; ele recusa database existente. Reiniciar só o recurso #11 com `start`.
Se necessário, manter uma chamada WSL própria ativa durante a revisão/testes;
o hold do executor será encerrado, não transferido silenciosamente ao revisor.

Browser: clone exclusivo fora do Git
`C:/Users/Raphael/.codex/tmp/rop011-browser-source/frontend`, node_modules junction
somente para dependências. `RENTALOPS_BROWSER_SERVER_COMMAND` usa helper `browser`;
`RENTALOPS_EVIDENCE_DIR` aponta run17/reservations-captures e cada largura tem
`PLAYWRIGHT_HTML_OUTPUT_DIR` próprio. Capturas legadas do clone também preservadas
antes de rerun. O harness aplica migrations reais em schema UUID novo; fresh server
por largura preserva proteção de30 tentativas de senha/peer/15min. Nenhum reset de
proteção, alteração de retry/timeout ou reutilização de resultados #12.

`run17/backend-fixture-fingerprints.json`: os84 arquivos backend versionados do
fixture Linux coincidem byte a byte com o checkout final. O manifesto
`run17/clone-fingerprints.json` confirma sete arquivos relevantes de fonte/testes/
index/build entre checkout e clone de navegador, sem divergência.
O teste unitário de duplo clique acrescentado depois da matriz não pertence ao
runtime do clone; o rebuild final run18 preserva os mesmos hashes JS/CSS abaixo.

Fingerprints SHA-256:

- backend/uv.lock: `a06a271b0ab64152492bdac42b9c7f9b8acede379bf4bc579830ba528da889e1`.
- frontend/package-lock.json: `eeeeb2b4ce011cf32424dc48c67e322715c37e8b0eca18fcc19dad7b1a2d917b`.
- export audit: `36d3d4dde29ae10e8f5e47313eb8e191944ad0cbfbb7cf02ac7335f4daaa138f`.
- produção JS index-CbBDqUJN.js: `294b241e99cb647c29b6199218d8ea7b1d9b90f052eec484417f0c717b3ce0a7`.
- produção CSS index-BpUQv-dt.css: `e2bbc1bf0b8219f60ef4ad2a019d4d6a8e7279fd3d3515e939811083d7f269ba`.

## UI real e limitações

Matriz final run17 no build CbBDqUJN,116/116 PASS:

| Viewport | Testes | Duração |
| --- | --- | --- |
| 320×740 | 29 PASS | 2.2m |
| 390×844 | 29 PASS | 2.0m |
| 768×1024 | 29 PASS | 2.3m |
| 1440×1000 | 29 PASS | 2.6m |

São92 capturas de reservas e268 regressões legadas, todas posteriores ao início
run17 (`2026-10-10T01:49:20.6658053Z`), zero arquivos antigos. Manifesto privado
`run17/captures-sha256.json`, SHA-256
`98b91e6b44e4fd6ce3abf58548e7892dd5be01a0a1191568e0b7c8c45ca6b87a`.
As capturas incluem loading/empty/read-error/deposit-required/preview-focus/unknown/success,
zoom200%, capacity-conflict, allocation-aware-quotation, separate-issues-history e
customer-summary. A resposta desconhecida é simulada DEPOIS do commit201 real:
a tela não afirma sucesso, reconcilia o mesmo payload/request_id e recebe replay.
Capturas de página inteira e viewport distinguem conteúdo abaixo da dobra.

Inspeção manual das imagens reais finais com view_image, por amostragem:
320 fluxo loading(fullpage)/vazio/sinal insuficiente/foco/unknown/sucesso/conflito/
zoom/cliente;390 foco/unknown/pendências/cliente;768 foco/unknown/conflito/cliente;
1440 unknown/conflito/pendências/zoom/cliente. Listas e referências de auditoria
quebram linhas em telas pequenas; rolagem vertical e conteúdo abaixo da dobra são
esperados, sem perda horizontal nos cenários verificados. Resumo de cliente agora
mostra a proposta não confirmada separada da reserva real, sem placeholder falso.
Assertions de overflow e axe passaram em cada estado capturado; teclado, foco,
reduced motion, navegação, zoom200% e regressões históricas passaram no navegador.

Playwright/axe e inspeção visual não certificam todos os dispositivos nem usabilidade
com atendentes. São Chromium desktop em quatro viewports, não hardware móvel real.
Validação operacional com a equipe, funcionalidades futuras e checks remotos não
executados permanecem fora da afirmação de PASS local.

## Falhas originais preservadas

`run00-original-tool-results.md` registra saídas iniciais disponíveis somente no
histórico das ferramentas, sem fingir recuperação de arquivos inexistentes.
Ruff87/mypy3 iniciais corrigidos sem supressão; assertion migration0007→0008 e
listas explícitas de tabelas incrementadas, metadata completa permanece verificada.

- run01:23 PASS/1FAIL, fixture de validade posterior à retirada corretamente
  recusada; fixture corrigida para testar backdate, não regra enfraquecida.
- run02:3 erros de collection, infra.operations ausente no espelho; fonte infra
  do checkout e testes/automation da raiz copiados ao fixture próprio.
- run03:446 PASS/2FAIL, expectativas antigas de tabelas; run04:448 PASS.
- run05:1 PASS/1FAIL browser320, Route already handled no controle de loading;
  sincronizado término de continue/resposta antes de unroute. Report/trace/falha e
  sete capturas sobreviventes preservados; run06:452 PG PASS e browser2/2 PASS.
- run08:453 PG PASS; run07:116 browser PASS no build anterior,84 capturas reservas
  e regressões legadas retidas. Não apresentado como validação do build final.
- Inspeção revelou503 acompanhado indevidamente de texto vazio; corrigida leitura
  confiável e acrescentadas regressões, sem perder seleção. Histórico404 não é
  interpretado como ausência de locação.
- run09:452 PG PASS/1FAIL/2warnings144.59s: replay concorrente payments aguardando
  advisory atingiu statement_timeout3000 durante browser desktop simultâneo.
  PostgreSQL registrou cancelamento, não deadlock. Contenção local é hipótese,
  não causalidade provada. Resultado original completo preservado; run10 sozinho
  passou453 em93.58s, sem alterar proteção/limites/código backend.
- run11:116/116 PASS,29 por largura (1.6m/1.7m/1.8m/1.9m), build intermediário
  Dlg73FPo e92 capturas reservas preservados. Inspeção real de unknown
  mostrou ausência lida ANTES da tentativa ainda visível depois de commit com
  resposta perdida. Condição corrigida e assertions unitária/e2e fortalecidas;
  erro5xx também mantém a chave. run12:52 unitários PASS/build intermediário;
  run13:53 PASS incluindo503, build intermediário BKZIGQS2. Nada foi sobrescrito.
- run14:116/116 PASS (29 por largura,1.6m/1.6m/1.7m/2.3m),360 capturas
  preservadas com manifesto SHA-256 e nenhuma anterior ao início da rodada.
  A inspeção do customer-summary revelou bloco estático herdado #9 afirmando
  ausência abaixo de reserva confirmada real. Removido esse placeholder;
  resumos reais/paginação e link estável mantidos. Expectativa antiga de vazio
  passa a consultar resposta real de orçamentos; nova regressão unitária com
  reserva confirmada e e2e asseguram ausência da contradição. run15:54 PASS.
  run14 não certifica o build final CbBDqUJN. Seu cleanup foi concluído; somente
  fixture próprio15443 foi retomado, com novo hold próprio para a revalidação.

Traces brutos sintéticos permanecem privados: não publicar tokens, senhas de teste
ou dados de contato como evidência pública. Não há CPF/RG/endereço/contrato/assinatura
real, dados financeiros reais ou traces de modelo nesta entrega.

## Recursos e handoff

Cleanup final concluído em run17/cleanup.txt: somente PostgreSQL15443 e novo hold
WSL próprio PID327/UID1000 parados, depois de validar comm/cmdline exatos. Fixture,
helper, fontes, clone e artefatos retidos para revisão/retomada. Portas15443/8000/
4173 sem listeners Windows/WSL;15442 anterior também ausente. MinIO permanece
healthy, mesmo ID `f419de217de93134b0933add2efcf516f22a5fbf2565e23ac669b75eb45b50c6`
e StartedAt `2026-10-09T02:04:38.643313867Z`. Não houve shutdown global, prune,
restart Desktop ou exclusão de dados. Fixture #12, rootless Docker retido, raiz
dirty e capturas históricas permaneceram como encontrados.

O cleanup intermediário run14 teve erro de quoting em `tr` no guard: não matou
processo algum. Original retido; guard corrigido com xargs -0 confirmou UID/comando
antes de parar hold506. A retomada final criou hold327 separado, também parado.

Após interrupção real por cota, a mesma execução/owner foi retomada com cota
fresca autorizada, sem reset, gasto ou fallback. Head/resultados/cleanup foram
reconciliados sem duplicar processos ou repetir suites completas. A revisão viva
final ainda está aberta, com mesmo updated_at e body exatamente igual ao snapshot
aprovado cujo SHA-256 consta no início deste relatório.

Executor para antes da revisão independente `gpt-6-sol/high`. Lock continua com
mesmo owner e coordenação; executor não libera, publica PR, aprova revisão, faz
merge nem marca Done. RES-07 só termina após os gates externos correspondentes.
