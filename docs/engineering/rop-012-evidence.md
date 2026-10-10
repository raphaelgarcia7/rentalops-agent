# ROP-012 — payments-v1: evidências do executor

## Identidade e escopo

- Data local: 2026-10-09. Issue #12 aberta e plano vivo lido integralmente antes
  de editar, incluindo decisões históricas, Precisões executáveis e PAY-01–13.
- Plano: updated_at `2026-10-09T00:27:53Z`; SHA-256 UTF-8 do body
  `9b04436fa47de9b41421c7dcd6a00a89f382958281f108045fe2369fbcb20fda`.
- Executor: função fixa `rentalops_executor`, gpt-6.1-sol/high, contexto
  `/root/rop012_executor`. Sem planner, substituição de modelo ou executor paralelo.
- Base: `4ea4fc3b4736e890d1728221bdc8a73d5e17622f`; branch `codex/12-payments`.
  Commit de implementação: `b73639edf0e1e5270205f8684cd24b92ff2f8ff6`.
  O head final do relatório é registrado no checkpoint/journal e no handoff para
  revisão; não há SHA autorreferente inventado neste arquivo.
- Lock compartilhado: owner `rop012-payments-20261009-9b04436f-run1`, task12;
  checkpoints via script absoluto da raiz compartilhada, preservando todos campos.
- Políticas/standards/ADR001 lidos na raiz compartilhada, sem copiar drafts ou
  mudanças acumuladas para este checkout. Dependências/Project In progress e base
  integrada foram reconciliados pelo coordenador. Nenhuma entrega anterior foi
  reexecutada nem recurso histórico apagado.

Entrega: serviços determinísticos, migration incremental de oito tabelas, API
privada, conciliação completa substitutiva, histórico/correções/devoluções,
originais privados e UI real. Sem banco/provedor, transferências, crédito entre
locações, reserva, hold, cancelamento, retirada, roles, IA, main ou deploy.

## Ambiente reproduzível e isolamento

Checkout Windows `C:/Users/Raphael/.codex/worktrees/rentalops-customers/rmg-chatbot`.
Backend espelhado por rsync em diretório Linux ext4 privado novo
`/home/rop004-rehearsal/rop012-HHFcBtT1/source`, excluindo .git/.venv/node_modules e
resultados/caches. O espelho mantém venv próprio; não é fonte publicada.

Fixture próprio PostgreSQL17 nativo, loopback127.0.0.1:15442, database dedicada
`rentalops_payments_test`; schemas/bancos de teste exclusivos UUID. URL/senha em
config local mode0600, nunca neste documento. Root mode0700. NTFS com permissões
abertas e endereço NAT foram recusados pelos guards existentes, não afrouxados.
Não houve instalação global/serviço de sistema novo: age/nginx oficiais Ubuntu
foram extraídos somente no tools privado do fixture, com mime.types oficial e
tempdirs Nginx exclusivos. Docker Desktop/MinIO usuário, rootless Docker anterior,
fixture #4, capturas/arquivos anteriores e raiz Git suja foram preservados.

Runtime: Python3.14.7; PostgreSQL17; FastAPI0.141.1; SQLAlchemy2.0.54;
psycopg3.3.6; Alembic1.20.0; pypdf6.20.0; Pillow12.3.0; pytest9.1.1;
Ruff0.16.10; mypy2.4.0; pip-audit2.10.1. Host uv0.12.12, Node24.18.0,
npm11.16.0, Git2.55.0.windows.3; Gitleaks8.30.1 previamente obtido da release
oficial (zip verificado SHA-256
`d29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e`).

Helper local não versionado: `C:/Users/Raphael/.codex/tmp/rop012-environment.py`.
`quality` carrega URL privada internamente e executa uv no espelho; `browser`
inicia somente harness descartável em8000. `start`/`stop` validam e retomam/param
somente o cluster retido; prepare não deve ser repetido. Hold WSL foreground
sessão83301 impediu encerramento durante testes; após interrupção real de quota,
clientes próprios Windows12024/33864 e tail Linux431 foram reconciliados.
Status final dos recursos é registrado no checkpoint/handoff. Fixtures e capturas
são retidos, não dados reais; nenhuma quota foi comprada/resetada/contornada.

## Comandos e resultados da implementação inicial (históricos)

Os resultados desta seção correspondem a b73639e, antes da revisão round0.
A correção 1 e seus gates atuais estão registrados separadamente ao final.

Executados sem skips, relaxamento de assertions/guards, aumento de timeout ou
retries para ocultar falha. Testes pesados backend/browser rodaram sequencialmente.

| Gate                  | Comando / resultado                                                                                                                                                                                                                                                                                                                                                                                  |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Backend completo real | `wsl -d Ubuntu-24.04 -u rop004-rehearsal -- python3 /mnt/c/Users/Raphael/.codex/tmp/rop012-environment.py quality pytest backend/tests -q --tb=short`: **410 passed**, 115.70s, sessão88919, dois avisos upstream                                                                                                                                                                                    |
| Regressão coordenação | `uv run --project backend pytest C:/Projects/praxis/rmg-chatbot/infra/tests -q`: **10 passed**, 4.76s                                                                                                                                                                                                                                                                                                |
| Ruff                  | `uv run --project backend ruff check backend infra/operations C:/Projects/praxis/rmg-chatbot/infra/automation C:/Projects/praxis/rmg-chatbot/infra/tests`: PASS; `ruff format --check` nos mesmos paths: **76 files already formatted** (74 do checkout e dois da coordenação compartilhada, somente leitura)                                                                                        |
| Tipos                 | `uv run --project backend mypy --config-file backend/pyproject.toml backend/src infra/operations`: PASS, **34 source files**                                                                                                                                                                                                                                                                         |
| Python audit          | `uv export --project backend --locked --all-groups --no-emit-project --output-file <private>/rop012-audit-requirements-hashed.txt`; `pip-audit --strict --disable-pip --no-deps -r <export>` em Linux e Windows: **No known vulnerabilities found**, exit0. Export resolve92 pacotes; todos os transitivos pinned/hashes, markers avaliados em ambos ambientes, sem dependência ignorada manualmente |
| Frontend              | `npm run lint`, `npm run format:check`: PASS; `npm test`: **48 passed / 6 files**, 15.91s, sessão27895; `npm run build`: PASS                                                                                                                                                                                                                                                                        |
| npm audit             | `npm audit --audit-level=high`: **0 vulnerabilities**                                                                                                                                                                                                                                                                                                                                                |
| Browser completo      | `RENTALOPS_BROWSER_SERVER_COMMAND='wsl -d Ubuntu-24.04 -u rop004-rehearsal -- python3 /mnt/c/Users/Raphael/.codex/tmp/rop012-environment.py browser' npm run test:e2e`: **108 passed**, sessão41061, exit0; quatro harnesses/schemas novos, **27PASS** cada:320(1.9m),390(1.8m),768(1.9m),1440(2.1m). Build final B4Ydr-3x/BpUQv-dt; workers1/retries0/sem skips                                     |
| Gitleaks              | `gitleaks git . --redact --log-opts=--all --no-banner`: **32 commits / 3.09MB**, sem achados até o commit de código b73639e; `gitleaks protect --staged --redact --no-banner`: scans do diff160.74KB/163.54KB e incremental48.44KB sem achados. Scan após commit documental e diff completo base→head registrados no handoff/checkpoint                                                              |
| Diff                  | `git diff --cached --check`: PASS                                                                                                                                                                                                                                                                                                                                                                    |

Build final de produção usado no navegador:

- `index-B4Ydr-3x.js` SHA-256
  `b3379cb41204bd15a474077fc05384d93afc37f737173d297ab06d8c16f0c00e`.
- `index-BpUQv-dt.css` SHA-256
  `e2bbc1bf0b8219f60ef4ad2a019d4d6a8e7279fd3d3515e939811083d7f269ba`.
- backend/uv.lock SHA-256
  `a06a271b0ab64152492bdac42b9c7f9b8acede379bf4bc579830ba528da889e1`.
- frontend/package-lock.json SHA-256
  `eeeeb2b4ce011cf32424dc48c67e322715c37e8b0eca18fcc19dad7b1a2d917b`.
- Export auditado hashed SHA-256
  `83acaa703ffea42d8cb0020cb21af6c1fb2c676f225498b57573e31f7466f109`.

## Matriz de aceite

| ID     | Evidência concreta                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| PAY-01 | `test_commercial_calculation_remains_authoritative` parametrizado:400→200/200; desconto10%→360/180/180;100.01→50.01/50.00. Unit contratos testa limites/MAX/sem float/precisão; snapshots #10 permanecem autoridade                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| PAY-02 | Serviço/API/Playwright registram Pix/cash/card com ator/sessão/data, sem proof obrigatório; `test_proof_no_financial_validation_replay_isolation_and_commit_compensation` prova anexo sem quitação                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| PAY-03 | `test_single_250_is_pending_then_explicit_distribution_200_50` e browser:250pendente→200sinal/50saldo→150restante; nenhuma escrita em catálogo/estoque ou estado de reserva fictício                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| PAY-04 | `test_partial_receipts_never_accumulate_deposit_but_balance_can_have_parts`:100insuficiente, duas fontes100 não validam sinal; saldo em duas fontes/meios e sinal de fonte única separada                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| PAY-05 | `test_integral_excess_substitutive_distribution_and_separate_refund` + backup fixture integral400→200/200/quitado. Serviço não importa nem modifica módulo de alocação/saída                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| PAY-06 | Mesmo teste:450recebidos,50excedentes; refund separado altera líquido, preserva recebido/histórico; replay sem efeito duplicado, nenhum crédito/transferência                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| PAY-07 | `test_correction_preserves_original_reason_author_and_invalidates_overcoverage`, `test_history_paging_database_guards_and_correction_below_refunded` e UI:before/after/motivo/autor/sessão preservados, revisão original imutável, não simula devolução                                                                                                                                                                                                                                                                                                                                                                                                    |
| PAY-08 | `test_commercial_revision_requires_explicit_current_conference_and_no_old_write`: nova versão torna conferência anterior inefetiva, stale409 sem mutação; revalidar é explícito. Contratos #11/#13/#14 em payment-rules.md, sem afirmar entregues                                                                                                                                                                                                                                                                                                                                                                                                          |
| PAY-09 | `test_concurrent_replay_is_one_money_event_payload_conflict_and_rollback`, `test_two_users_reconciling_same_version_and_refund_correction_race`, `test_concurrent_commercial_revision_has_no_deadlock_or_old_validation`: PostgreSQL real, concorrência, uma gravação, payload conflitante, rollback sem história/idem parciais; ordem de locks consistente. `test_lost_commit_ack_retains_committed_proof_and_replays_original` efetua commit real e perde ACK: bytes/história/result ficam acessíveis, replay não duplica. `test_unverifiable_commit_compensation_retains_only_new_possible_orphan` protege dados quando a verificação fica indisponível |
| PAY-10 | Unit storage:PDF/JPEG/PNG originais, limite10M exato/+1,25MP inclusivo/>limite,100páginas inclusivo/101,PDF encrypted/JS/embedded/ilegível/MIME recusados; paths/links/perms/digest/falha. API3 testes cobrem auth/Origin/vínculo alien/download/privateheaders/limites/503/logs sem conteúdo. Commit compensado remove somente seu arquivo novo, replay não duplica bytes                                                                                                                                                                                                                                                                                 |
| PAY-11 | `payments-live.spec.ts` em320/390/768/1440 com auth/API/PG/build reais:receipt/reconcile/correct/refund/proof/history/clientlink; Enter/foco/200%zoom/reducedmotion; empty/loading/error/success/unknown/staleform. Unknown aborta resposta **após** route.fetch completar commit, repete corpo/chave exatos. Axe WCAG2A/AA/2.1AA/2.2AA em cada estado. Unit também cobreHTTP503 unknown; sem sucesso presumido                                                                                                                                                                                                                                            |
| PAY-12 | Gates acima incluem regressão auth/#8/#9/#10/#4; migração upgrade/downgrade/metadados, constraints/immutability, backup/restore real. Falhas originais abaixo, sem esconder execução                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| PAY-13 | **Pendente do coordenador**: executor deve parar, revisor independente gpt-6-sol/high no head/base finais; gates remotos existentes, PR develop, merge confirmado e Project Done. Não houve push/PR/merge/Done pelo executor; ausência confirmada de CI/proteção é limitação autorizada até #6, não check PASS                                                                                                                                                                                                                                                                                                                                             |

## Storage/backup e fronteiras operacionais

Namespace server-generated proof no STORAGE_ROOT privado já protegido, originais
exclusivos mode0600, sem nova pasta/volume público. Verificação de PDF não é
antivírus. Sem DELETE/purge/eliminação de prova histórica; compensação limitada a
bytes recém-criados identificados. Retenção jurídica/produção/backups requerem
política validada antes de ativar eliminação, sem promessa de conformidade.
Compensação consulta metadata em transação nova sob lock de quotation, esperando
o desfecho da transação original: não remove bytes de proof commitado se somente
o ACK se perdeu. Se não conseguir verificar, conserva o possível órfão exclusivo
da tentativa; não executa cleanup amplo nem presume rollback de commit incerto.

`test_real_encrypted_backup_restores_original_proofs_payments_and_history` usa
age+pg_dump/pg_restore reais, verifica referência/digest, pagamento integral,
histórico antes/depois e bytes PDF idênticos após restore em banco/storage novos.
Proof faltante recusa publicação, preservando último ponto. Suite operacional
existente também continua completa. Evidência vale para schema/head0007 corrente;
não declara restore de backup antigo, deploy, RPO/RTO empresarial ou acesso humano
de produção comprovado. Guard de restore só aceita nomes descartáveis existentes.

## Inspeção visual inicial e limitações (histórico)

Capturas sintéticas reais em `frontend/test-results/evidence/`, relatórios HTML em
`frontend/playwright-report/<project>/` e resultados em
`frontend/test-results/runs/<project>/` (ignorados). Inspeção direta do executor
abriu PNGs finais de320/390/768/1440: feedback/sinal validado, resultado desconhecido,
erro, histórico/proof, conflito e zoom. Marca/navegação/foco permanecem visíveis;
valores e aviso de não confirmação são legíveis, sem clipping horizontal. As
capturas fullPage incluem formulários/histórico; as viewport facilitam leitura.
Automação verifica36estados financeiros por axe (nove por largura), sem violações
nas tags declaradas, e gera **72 PNGs** (fullPage+viewport). Não foi uma certificação
manual de todos os estados/dispositivos, nem comparação automática de pixels.

Fingerprint do conjunto72, nomes ordenados e linhas UTF-8 sem BOM no formato
`<filename> <sha256-minúsculo>\n` (incluindo LF final):
`32df33d43d2d76dd8d9ac7d125cdf8f90a6a109a31b3a7bc6c8b3b83ceb7c151`.
Esse fingerprint é do conjunto histórico inicial, não das capturas de revisão
ou correção. Durante a revisão round0, 18 PNGs originais de320 foram sobrescritos
e **não foram recuperados**. Os outros54 originais estão preservados em
`frontend/test-results/reviewer-preserved-executor-20261009/`. O conjunto de72
novos PNGs do revisor está em `frontend/test-results/reviewer-run-20261009/`,
fingerprint `c17a0f096df7f3b3d0cbacdfa46444c3987eae0809fea00197b9145e3ae914c3`.
Assim, não é possível recomputar o fingerprint inicial a partir dos originais
restantes; não se atribui o hash histórico aos arquivos novos.
Exemplos finais inspecionados, prefixos relativos à pasta de evidência:

| Captura                                              | SHA-256                                                            |
| ---------------------------------------------------- | ------------------------------------------------------------------ |
| mobile-320-payments-deposit-validated-viewport.png   | `4e430d136cffcdc13bd82e8c46f347067a7a9f14dd4b0bcb1c3badf9d5a9e0f7` |
| mobile-390-payments-deposit-validated-viewport.png   | `b0ef62544e38cd94279defa2fb59980f71d084440f97a7bf09529cbc60bf2859` |
| tablet-768-payments-deposit-validated-viewport.png   | `f9a9e6f9a8697e2bc15ff2966b7a5c5b1a56075f94912a5de91bfe4c963cdc6c` |
| desktop-1440-payments-deposit-validated-viewport.png | `c2fde99b455974ffe52d8b1e782f44f10235be8051e2a6c944e0979c4225d579` |

Não há prova real/documento pessoal/cartão. Quatro larguras Chromium não certificam
todos browsers/dispositivos, tecnologia assistiva ou usabilidade operacional.
Zoom200% foi testado por CSS zoom no Chromium, com reflow/rolagem vertical; não é
certificação de todos os modos de zoom do sistema/browser. Histórico before/after
pode ser longo e exige expansão/rolagem, sem reduzir ou apagar dados para a captura.
Formulários ficam somente em memória; fechar/recarregar perde o draft.

## Encerramento escopado e retomada para revisão

Após os quatro projetos finais: teardown normal dos harnesses concluído;
last-run dos quatro registra passed/zero falhas. Portas8000/4173 sem listeners.
Helper `stop` encerrou somente o cluster próprio rop012/15442; root/config/database
e fixtures privados permanecem retidos. Tail431 foi verificado por UID1000 e
cmdline exata, encerrado via pidfd; clientes WSL12024/33864 encerraram. Nenhum
listener15442 remanescente. Não houve wsl shutdown, limpeza global ou Docker stop.
MinIO usuário permaneceu healthy, mesmo ID
`f419de217de93134b0933add2efcf516f22a5fbf2565e23ac669b75eb45b50c6` e StartedAt
`2026-10-09T02:04:38.643313867Z` antes/depois. Capturas/relatórios/fixture #4 preservados.

Revisor pode iniciar um hold foreground WSL próprio, depois executar
`wsl -d Ubuntu-24.04 -u rop004-rehearsal -- python3 /mnt/c/Users/Raphael/.codex/tmp/rop012-environment.py start`.
Não repetir prepare. `quality pytest backend/tests -q --tb=short` usa os mesmos
guards/config privados. Para navegador, aplicar o override explícito acima em
frontend e `npm run test:e2e`; o runner inicia/encerra harness novo por largura.
Se mudar fonte, sincronizar o checkout atual para source com as exclusões descritas
antes de repetir testes. Encerrar somente recursos próprios após a revisão.

Executor não libera o lock, não publica branch/PR nem move Project Done.
Coordenador recebe head final documental e base exatos para gpt-6-sol/high em
contexto independente; esse gate continua pendente, separado dos testes locais.

## Falhas/tentativas preservadas

1. Target financeiro inicial sessão15016: **3 failed / 52 passed**,9.94s.
   Dois fixtures de revisão sem motivo obrigatório e storage_key VARCHAR40 para
   chave42. Corrigidos fixtures/model/migration; repetição sessão1945 **55 passed**,
   8.21s. Depreciação do gerador sintético add_js removida sem mudar parser.
2. API+backup inicial: **3 passed / 1 failed**,5.74s. Nome de banco restore do
   fixture fora do padrão seguro; corrigido somente nome descartável, não guard.
3. Full backend sessão22028: **405 passed / 3 failed**,70.91s. Expectativas antigas
   de metadados0005/head0006 não listavam oito tabelas futuras; teste Nginx privado
   sem mime.types. Expectations exatas foram atualizadas, nunca removidas.
   Focal migrações+Nginx: **2 passed / 1 failed**,5.24s; mime.types solucionou leitura,
   mas defaults Debian de tempdirs ainda apontavam /var/lib/nginx. Config exclusiva
   do teste recebeu três tempdirs privados; focal Nginx **1 passed**,5.75s.
   Repetição full36535 **408 passed**,73.83s; avisos restantes upstream Starlette/httpx
   e anyio BlockingPortal, não suprimidos.
4. Browser financeiro inicial sessão99323: **4 passed / 4 failed**: selector do link
   histórico não correspondia ao texto real em três larguras, e zoom320 revelou
   overflow genuíno. Selector tornou-se nome real `Orçamento ...`; zoom permaneceu.
   Rodada26593 **7 passed / 1 failed**,1.7m; focais13969/29847/74745 ainda falharam
   no320. Diagnóstico de dimensões mostrou marca/nav e min-content de controles
   com espaço reduzido. CSS mínimo: marca pode quebrar; nav usa auto-fit conforme
   espaço real; controles/grids financeiros permitem minmax(0,1fr)/quebra. Sem
   esconder navegação/texto nem alterar assertion/zoom. Focal7966 **1 passed**,16.1s.
5. Full browser único sessão41266: **102 passed / 6 failed**,4.8m. Preparação de
   contas no mesmo peer excedeu corretamente o limite persistido de password/set
   30tentativas/15min; seis setups desktop receberam429. Capturas/traces/HTML dessa
   tentativa foram copiados para `<private>/rop012-browser-full41266`, sem apagar
   a origem. Runner `npm run test:e2e` agora executa TODOS projetos do config, cada
   um com harness/schema descartável novo e teardown normal, worker1, diretórios
   próprios. Nenhum contador foi resetado, limite aumentado, assert removido ou
   espera15min usada para esconder a causa. Mesmos108 casos, sem mocks novos.
   Matriz71457 intermediária:27PASS em cada largura (1.4m/1.4m/1.4m/1.6m),108total.
   Durante inspeção real, texto antigo de OfferSummary afirmava ausência de
   pagamentos mesmo após receipt: corrigido para separar previsão de registro.
   Autoinspeção adicionou proteção/regressões de commit-ACK perdido acima. Por isso
   os resultados finais foram repetidos sobre b73639e e novo bundle, não atribuídos
   retroativamente à matriz intermediária. Interrupção real de quota preservou
   código/checkpoint/fixtures; retomada usou o mesmo executor, modelo e owner.
6. Vitest após textos reais de escopo: **47 passed / 1 failed** em duas tentativas,
   expectativa antiga depois matcher incorreto. Assertion agora compara o texto
   completo real de pagamentos manuais e reservas futuras; **48 passed** depois.
7. Comando mypy sem config/target recusado (exit2); repetido com config explícita e
   34 arquivos, PASS. Primeiro pip-audit disable-pip sem no-deps recusado por CLI;
   export locked completo + no-deps auditou pins, exit0 emLinux/Windows. A CLI
   continua emitindo recomendação genérica de hashes apesar do export hashed;
   não é falha ignorada ou afirmação de ausência de risco.

Este relatório não fecha PAY-13 nem marca a issue Done. O revisor deve examinar o
diff completo e conferir resultado/head atuais independentemente.

## Correção 1 — revisão independente round0 (PAY-10 / RN-036)

Revisão independente no head13026fa/base4ea4fc3 identificou P1: a instalação de
filtros apenas nos loggers pypdf existentes no import não cobria `pypdf._reader`
criado depois. PDF estruturalmente inválido provocava diagnóstico com bytes do
documento antes da rejeição422. Parecer round0 FAIL preservado; o PASS de testes
anterior não comprovava esse caso. Não houve mudança do plano/comércio/parser.

PoC privada sintética `rop012-review-proof-log-poc.py`: antes, status422,
reader_filter_installedFalse e synthetic_document_token_loggedTrue. Duas novas
regressões reproduziram o problema antes do fix: **2 failed / 21 deselected**,
0.98s. Depois, PoC status422/filterTrue/tokenLoggedFalse, sem mudar validação.

Código corretivo: `8841e1a6bf1d2e7136bdbbeba5c209bc529281a9`,
`fix: protect private PDF diagnostics from late loggers`. A factory padrão de
LogRecord é encadeada com a previamente configurada e instala o filtro no logger
emissor antes de Logger.handle, incluindo logger tardio e handler direto.
O ContextVar limita o filtro à validação privada; outros namespaces/contextos
continuam emitindo normalmente. Mensagem/args/exception/stack do diagnóstico
privado são sanitizados **antes** de encaminhar à factory anterior, que pode
coletar registros. A factory customizada continua recebendo registros e pode
acrescentar seus atributos. Não se reduz nível global nem se ignora erro do parser.
Como qualquer hook de logging configurado no processo, futuras factories devem
encadear a existente, não substituí-la descartando as proteções da aplicação.

Regressões adicionais em `test_payment_storage.py`: PDF rejeitado real com
objeto inválido e logger recriado após import; novo descendente pypdf; factory
preexistente com atributo próprio/argumentos/exception/stack e logging paralelo
fora do ContextVar. Focal final **3 passed / 21 deselected**,0.61s. Ruff inicial
apontou uma linha longa e import fora de ordem; formatter/importfix corrigiram,
sem desativar regras. O backend intermediário sessão47195 teve **412 passed**,
2avisos,101.99s, mas precede o refinamento final da factory: não é o gate final.

Antes de qualquer rerun, cópia integral de test-results/playwright-report em
`C:/Users/Raphael/.codex/tmp/rop012-correction1-before-reruns-20261009/`.
Isso preserva54 originais sobreviventes,72 do revisor e relatórios disponíveis;
não recupera os18 originais já perdidos. As falhas antigas102PASS/6FAIL429 e
demais tentativas acima continuam registradas, sem sobrescrever sua atribuição.

### Gates finais da correção 1

Todos sobre código8841e1a; somente este relatório documental mudou depois.
Mesmos comandos/configuração acima, sem skips/retries/timeout maior ou guards
afrouxados. PostgreSQL e browser completos sequenciais, fixtures sintéticos.

| Gate                         | Resultado atual                                                                                                                                                                                                                                               |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Backend PostgreSQL real      | `quality pytest backend/tests -q --tb=short`, sessão62026: **413 passed / 2 warnings**,102.81s, exit0. Os dois avisos upstream Starlette/httpx e anyio permanecem visíveis                                                                                    |
| Coordenação                  | `uv run --project backend pytest C:/Projects/praxis/rmg-chatbot/infra/tests -q`: **10 passed**,4.00s                                                                                                                                                          |
| Ruff / format                | Check nos mesmos paths backend/infra: **PASS / 76 files already formatted**                                                                                                                                                                                   |
| mypy                         | Config explícita backend/pyproject.toml, backend/src + infra/operations: **34 source files, PASS**                                                                                                                                                            |
| Python audit                 | Export locked/all-groups/hashed,92 pacotes, `pip-audit --strict --disable-pip --no-deps -r <export>` Linux e Windows: **No known vulnerabilities found**,exit0. Recomendação genérica de hashes da CLI preservada                                             |
| Frontend                     | Sessão23785: ESLint/Prettier **PASS**, Vitest **48 passed / 6 files**,18.61s, build **PASS** e `npm audit --audit-level=high`: **0 vulnerabilities**,exit0                                                                                                    |
| Browser produção             | Sessão93670 **108 passed**,exit0: mobile320 **27/2.0m**, mobile390 **27/2.1m**, tablet768 **27/2.2m**, desktop1440 **27/2.2m**. Quatro last-run passed/zero failedTests,36 estados financeiros axe,72 PNG novos; mesmos108 casos/assertions/locks/rate limits |
| Segredos no commit corretivo | Gitleaks8.30.1 `git . --redact --log-opts=--all --no-banner`: **34 commits / 3,123,835 bytes, clean**; diff base→8841e1a via stdin redact: **229,367 bytes, clean**. Scan após commit documental registrado no handoff/checkpoint pelo coordenador            |
| Diff                         | `git diff --check`: **PASS**; handoff registra head documental e checkout limpo após commit                                                                                                                                                                   |

Export desta rodada (nome/comentário gerado diferentes do export histórico):
`C:/Users/Raphael/.codex/tmp/rop012-correction1-audit-requirements-hashed.txt`,
SHA-256 `606df90d85f8e87e732fbf1e94a65ac81c4498a8499c68ebb263e094949738cf`.
Lockfiles não mudaram, SHAs iguais aos acima. Rebuild final tem os mesmos bundles
`index-B4Ydr-3x.js` e `index-BpUQv-dt.css`, com os SHAs já registrados.

### Evidência visual própria e encerramento desta rodada

Cópia nova exclusiva: `frontend/test-results/executor-correction1-20261009/`,
subpastas evidence (72PNG financeiros entre268 PNGs totais), runs (quatro last-run),
playwright-report (quatro HTML). Fingerprint **novo** somente dos72 arquivos
`*-payments-*.png`, nomes ordenados ordinalmente, UTF-8 sem BOM, linhas
`<filename> <sha256-minúsculo>\n` com LF final:
`efe4cbfde85ede5c196751dd19e7a21976ff0f2ccc23923a19d1cd6714dedac9`.
Não é o conjunto32df nem o conjuntoc17a do revisor.

Inspeção direta das novas capturas:320 sucesso/foco/unknown/conflito/zoom;
390 histórico/sucesso/erro/conciliação;768 sucesso/foco/loading/unknown;
1440 sucesso/foco/unknown/zoom, incluindo marca/navegação lateral visíveis.
Feedback e valores são legíveis, distinguem dinheiro/reserva; nenhuma alteração
de UI nesta correção. O zoom estreito de320 continua quebrando palavras e produz
fullPage muito longo: a miniatura reduzida não permite ler todos os controles,
por isso também foram abertas as capturas viewport. Não se afirma inspeção manual
de todos os controles/estados, certificação assistiva ou validação operacional.
As limitações históricas de UI/usabilidade permanecem; nenhuma assertion mudou.

PAY-10/RN-036 agora incluem as três regressões de logger tardio/contexto/factory
e PoC final; PAY-12 inclui todos os gates atuais acima. PAY-13 continua pendente
de revisão independente do novo head/base e integração pelo coordenador.

Teardowns dos quatro harnesses terminaram normalmente; portas8000/4173 sem
listeners. Helper `stop` encerrou somente PG15442/PID398 desta retomada, preservou
o cluster/fixture privado. Hold sessão42665, LinuxPID291, foi verificado por
UID1000/cmdline exata `tail -f /dev/null` e encerrado por pidfd/SIGTERM; sessão
terminou com exit1 decorrente desse encerramento, não uma falha de teste. Sem
listener15442 remanescente. MinIO antes/depois permaneceu healthy, mesmo ID e
StartedAt acima. Nenhuma exclusão de fixtures/capturas nem cleanup global.

Retomada mantém os comandos acima: estabelecer novo hold próprio, helper start,
nunca prepare; sincronizar source apenas se houver nova mudança. Executor não
escreveu o lock nesta rodada para não perder campos de coordenação; owner continua
o mesmo. Após commit documental/scan final, executor para para nova revisão
gpt-6-sol/high. Sem push, PR, merge, Project Done, release ou deploy.
