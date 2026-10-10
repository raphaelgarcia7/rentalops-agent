# ROP-013 — rental-changes-v1

## Revisão e escopo

Plano humano: issue13 aberta, `updated_at=2026-10-09T00:27:55Z`, SHA-256 do body UTF-8
`90177b437c715aa82ba700a6e484bbd5865baff333b6499e4a3c38007d15126f`.
Base: `670ae385cb2b17a2bc42311dc3aa250cdeebf2ef`, branch
`codex/13-rental-changes`. SHA final fica no journal/handoff e na revisão
independente; não se inclui o hash autorreferencial deste documento.
Owner compartilhado: `rop013-rental-changes-20261010-90177b43-run1`.
Executor único gpt-6.1-sol/high, sem planner. #11/#12 e dependências transitivas
Done/merged foram reconciliadas pelo coordenador antes da execução.

Aplicadas as políticas humanas da raiz compartilhada sem copiá-las para ampliar o
checkout. Regras impactadas: [rental-changes-v1](../product/rental-changes-v1.md).
Não implementa #14/#15, roles, IA, contratos reais ou movimentação financeira real.

## Matriz de critérios

| AC original/consolidado | Implementação e prova determinística |
| --- | --- |
| Editar no aluguel do cliente, versões/autor/motivo | `RentalChanges`, editor existente com contrato revisionado; `test_chg01_increase_reduction_original_deposit_excess_immutable_replay`, histórico imutável, ator da sessão/UTC e motivos; browser `change diff, unknown replay...` termina navegando ao histórico do cliente |
| Datas/itens antes da troca; conflito/concorrência preservam compromisso e versão | `test_chg02_conflict_stale_replay_rollback_preserve_old_commitment`, `test_chg02_real_racing_edits_and_cancellation`, `test_chg02_custom_kit_dates_swap_excludes_self_preserves_other_and_maintenance`: kit/custom/avulso, união UUID, exclusão própria, outra reserva/manutenção, rollback injetado e corrida real PostgreSQL. `test_locked_context_refreshes_identity_after_concurrent_cancel` garante refresh da identidade ORM lida antes do lock, mesmo quando só a versão da locação mudou |
| Cancelamento registra decisão; estoque separado do financeiro | `test_chg03_requested_cancel_approved_only_own_allocation_and_finance` e browser: solicitação não muda estado/alocação; aprovação explícita libera somente própria alocação, mantém líquido/excesso/histórico; `test_cancel_preserves_revised_financial_terms_without_silent_reconciliation` exige financeiro e snapshot idênticos após cancelar500/150; guards pós-saída em unidade |
| Retomada preserva pagamentos/histórico; estornado não volta quitado | `test_chg04_cancelled_resume_same_id_without_allocating_then_fresh_confirm`, `test_chg04_refunded_money_cannot_reappear_two_small_sources_do_not_make_signal`, `test_chg04_expired_quotation_review_without_new_receipts`: mesma identidade, net após refund, revisão sem alocação e confirmação #11 com nova checagem; browser exige conferência e mostra review |
| Retomar vencida/cancelada apresenta revisão sem confirmar silenciosamente | Alias técnico na mesma proposta vencida sem rental: expected_rental_version0; primeiro cabeçalho review, nenhum recibo/alocação fictício. `test_upgrade_backfill_and_review_require_fresh_reconciliation` bloqueia nova mudança em review até conciliação explícita; browser fluxo vencida com zero recibos |
| Concluída não reabre; nova proposta/newID/preços atuais/sem pagamentos | Guard de `copy_preview` e builder unitários; `test_chg05_reference_saved_through_quotation_uses_current_prices_new_id_zero_money` exerce builder + serviço #10 real, preço de catálogo atualizado, novoID e zero dinheiro. Não fabrica estado completed no PostgreSQL; integração desse contexto depende de #14 conforme plano |
| CHG-01:400 recebido200→500 saldo300, sem extra sinal; →150 saldo0 excesso50 | Teste CHG01 e browser revisão/redução: sinal histórico200, sem recibos/refunds/crédito/perdão; valores projetados e atuais distintos, excesso pendente |
| CHG-02: troca atômica, todas composições, conflito/rollback/concurrency | Três testes CHG02 acima e browser capacidade/versão financeira concorrente; histórico comercial/financeiro e alocação na mesma transação |
| CHG-03: aprovação pré-saída vs solicitação/pós-saída | CHG03 e guards unitários, nenhuma ação de entrega fictícia; dinheiro mantém ciclo próprio |
| CHG-04: líquidos/revisão/sinal único/nova disponibilidade | CHG04, upgrade/reconciliação e regressões #11/#12; dois recibos insuficientes não viram sinal, devolvido não reaparece, confirmação posterior usa mesmo serviço e mesmo rentalID |
| CHG-05: futuro out protege entregues/extensão; complemento nova locação | `test_rental_change_contracts.py`: preço/motivo permitido; produto/composição/quantidade e saída congelados, encurtamento bloqueado inclusive horário; extensão passa pela validação comum. DB0009 habilita somente confirmed/cancelled/review; integração real out/completed adicional em #14 |
| CHG-06: correção preserva allocation/pending; assinatura vê version mismatch | `test_chg06_correction_preserves_commitment_signature_revision_and_history`, corrida conciliação/alteração; `current_financial` fresco sem reescrever snapshot anterior; `signature_commercial_version` a comparar em #15, sem alegar assinatura existente |
| APIs privadas/strict/Origin/version/idempotência/concurrency/history | `test_rental_change_api.py` todos endpoints sem sessão/Origin, rejeição ator/unknown fields, versões comerciais/financeiras, no-store/logs sem PII; replay original antes das versões novas, payload diferente409; mesma chave simultânea produz um registro. Dinheiro string decimal estrito; previews não gravam |
| UI estados dinheiro/estoque/assinatura, motivo, unknown/feedback | Vitest `RentalChanges.test.tsx`, integração de telas existentes, Playwright real: antes/depois, valores pt-BR, motivo obrigatório, confirmação de aprovação/conferência, lost-ACK após commit seguido de502 no replay e terceira tentativa com payload idêntico/uma única alteração, loading503 não vira empty, conflito mantém rascunho e compara versões |
| CHG-07: pipeline/evidência/revisão | Gates locais abaixo, capturas privadas preservadas. Revisão independente do SHA final e gates GitHub ainda pertencem ao coordenador, não são declarados passados por este executor |

## Ambiente e comandos

PostgreSQL17 real em fixture NOVA privada Linux/ext4, UID1000 Ubuntu-24.04,
`/home/rop004-rehearsal/rop013-sJH2mZbU`, loopback15444, dados sintéticos.
Helper privado Windows `C:/Users/Raphael/.codex/tmp/rop013-environment.py`;
credenciais aleatórias só config0600, nunca evidência pública.
`sync` copia checkout e, somente para testar coordenação, infraautomation/tests da
raiz humana para a fixture; esses inputs não são adicionados ao repositório.
Binários nginx/age já existentes são usados somente leitura, sem reiniciar #11.
Browser clone NOVO `C:/Users/Raphael/.codex/tmp/rop013-browser-source/frontend`.
Não reutiliza bases/capturas11/12, não toca serviço MinIO do usuário.
Após identificar o caso de identidade ORM, `source-final` foi criada dentro da
MESMA fixture privada sem trocar código sob o navegador intermediário em execução.
`source-verified` conserva a correção financeira final; `quality-verified` e
`browser-verified` usam essa cópia, o mesmo PostgreSQL próprio e schemas sintéticos
exclusivos. Nenhum serviço/banco/porta duplicado, nenhum dado anterior sobrescrito.

Logs/capturas/traces brutos PRIVADOS: raiz compartilhada
`.rentalops/rop013-evidence/run01` até a rodada final. Cada rerun tem diretório novo;
relatórios Playwright anteriores são copiados antes do rerun. Não publicar traces
com sessão/cookies nem fixtures pessoais. Conjuntos anteriores não foram apagados.

| Gate | Resultado registrado |
| --- | --- |
| `quality-verified pytest backend/tests infra/tests -q` em Linux/PG real | run20:477 passed, 2 warnings,117.19s; migrations upgrade/backfill/downgrade/refusal, rollback, races, replay e regressões. Nenhum skip |
| Ruff check / format check | run20 exit0, backend e infraoperations; coordenação humana como input privado validada em run08 |
| mypy | run20 exit0,38 source files, sem problemas; contagem histórica corrigida conforme log original |
| infraautomation Windows pytest | run08:10 passed,6.17s |
| ESLint / Prettier | run20 exit0, sem desabilitar regra |
| Vitest | run15:9 files/67 passed,14.45s |
| Produção `npm run build` | run15 exit0,126 módulos; JS `index-B6mTMe_h.js`, CSS `index-BpUQv-dt.css` |
| `npm audit --audit-level=low` | run08 exit0,0 vulnerabilidades |
| pip-audit Windows e Linux | run08 preservado, mas export veio da raiz compartilhada com lock distinto; não prova dependências deste checkout. Auditorias exatas substituídas em correction1 abaixo |
| Playwright/axe produção320/390/768/1440 | run21:128 passed,32 em cada largura, respectivamente2.1m/2.1m/2.2m/2.4m; exit0, axe sem violações nos estados capturados |
| Gitleaks histórico e diff completo base→head | run22: exit0/sem leaks em ambos; logs/JSON privados e SHA final no handoff, sem publicar diff/traces brutos |

run20/backend-source-fingerprints.log compara por SHA-256 os89 arquivos backend
versionados/adicionados do checkout com source-verified usado no PostgreSQL:
zero divergências. run21 compara74 fontes frontend e4 artefatos de produção com o
clone do browser: zero divergências. Os fontes de produção são os mesmos aprovados
por lint/Vitest/build; o diff tem captura própria para inspeção legível.

Warnings mantidos: Starlette depreca `httpx` no TestClient, anyio depreca o alias
BlockingPortal; pip-audit avisa genericamente sobre no-deps/hashes. Não houve
alteração de timeouts, retries, limites de autenticação ou assertions para ocultar
falhas. A matriz existente cria harness isolado por viewport, sem limpar budgets.

## Inspeção visual real da rodada0 — depois reprovada

Inspecionados os PNGs reais de run21, não somente a existência de arquivos.
Essa inspeção parcial não identificou a contradição do resumo comercial cancelado;
a revisão independente encontrou o bloqueador abaixo. Rodada0 não é aceite final.
Todos os quatro diffs mostram antes400/depois500, líquido200/saldo300, sinal
histórico200, nova checagem de estoque e assinatura futura sem alegar contrato.

| Largura | Capturas efetivamente abertas e observações |
| --- | --- |
| 320 | `mobile-320-change-diff.png`, `changes-read-error-viewport.png`, `changes-loading-viewport.png`: diff em coluna, datas/textos quebram sem corte horizontal; carregando e falha503 são mensagens distintas, não estado vazio |
| 390 | `mobile-390-change-diff.png`, `cancelled-money-pending-viewport.png`, `zoom-keyboard-viewport.png`: somente o painel financeiro mostrava sinal150/saldo0/líquido200/pendente50; o resumo contraditório foi identificado na revisão; fonte200% reflow em coluna, controles e identificadores quebram, exigindo scroll vertical |
| 768 | `tablet-768-change-diff.png`, `resumed-review-viewport.png`: diff legível, retomada mostra novo acordo75+75, líquido200 e excesso50 separado, sem criar recibo |
| 1440 | `desktop-1440-change-diff.png`, `change-unknown-http-502-viewport.png`, `expired-empty-viewport.png`: diff amplo, unknown em aviso destacado com ação da mesma gravação e campos desabilitados; heading recebe foco visível no orçamento vencido |

Nomes abreviados na coluna preservam o prefixo de largura; arquivos completos
estão em run21/captures. A matriz exige axe sem violações nos estados capturados,
sem overflow horizontal, teclado/foco, reduced-motion e fonte200%; não foi feito
teste de zoom nativo de todos os navegadores. Formulários/históricos longos
exigem rolagem vertical; capturas full-page reduzidas não provam legibilidade.

## Correção1 após revisão independente

Revisor gpt-6-sol/high formalFAIL/COMPLETED em
`59beeea3b058b731d67ce795bdd025886aa8955c`: a captura real
run21/captures/mobile-390-cancelled-money-pending.png mostrava total150 com resumo
sinal75/saldo75, enquanto o financeiro correto mantinha sinal150/saldo0. Cancelar
não autoriza a renegociação50% exclusiva de uma retomada explicitamente conferida.

Fix focado: `QuotationDetail` não mostra parcelas genéricas para nenhum aluguel
persistido; o financeiro servidor é a única autoridade, inclusive em loading,
erro e gravação unknown. Orçamento sem locação mantém sua estimativa. Editor e
prévia da retomada não foram alterados; após conferência mostram75+75 no financeiro.
Nenhuma mudança de backend/regra comercial/máquina de estados ou decisão nova.

RED real: `QuotationDetail.test.tsx`8 failed/7 passed,15 testes,exit1,7.74s ANTES
do fix; GREEN mesmos15 passed,4.04s. Casos cancelled500/150 × loaded/loading/error,
confirmed/review/out/completed e proposta sem locação. Browser reforçado exige
ausência de parcelas no resumo cancelado, financeiro150/0, retomada75/75 e
nenhum fallback nos estados unknown502/loading/error, em todas as quatro larguras.
Captura exclusiva `*-cancelled-commercial-summary.png` torna o achado legível.

Preservação ANTES dos reruns: cópias completas de run01–22, clone anterior com
fontes/dist/test-results/playwright-report e helper. Manifesto SHA256 confirmou
2976 arquivos originais e respectivos backups idênticos. Nenhum conjunto11/12 foi
alterado. Outputs novos exclusivamente em `.rentalops/rop013-evidence/correction1/`.
Helper ganhou sufixo correction1 para uma cópia separada de código na MESMA
fixture/PG17/porta15444; `source-verified` anterior continua intocada, sem reset.

Contagem: logs originais run12 e run20 registram38 arquivos mypy, não41 informado
anteriormente. Corrigido o relato, não os logs. A execução real desta correção
registrou41 arquivos; esse novo resultado é distinto e não altera o histórico.
Auditorias iniciais desta correção também identificaram export executado a partir
da raiz compartilhada, cujo lock difere do checkout. Outputs antigos retidos e
não utilizados como gate do HEAD. Export `--locked --project <checkout>/backend`
e pip-audit Windows/Linux foram repetidos com caminho explícito e inputs exatos.

| Gate correction1 | Resultado |
| --- | --- |
| Full PostgreSQL17/Linux pytest backend/tests infra/tests |477 passed,2 warnings,87.19s; nenhum skip |
| Ruff check/format backend+infra |exit0,93 arquivos já formatados, sem relaxar regras |
| mypy |exit0,41 source files observados nesta execução |
| Infra Windows com ambiente do checkout |10 passed,4.22s |
| ESLint/Prettier/Vitest |exit0;78 passed/9 files,12.69s |
| Build produção |exit0,126 módulos, JSindex-DF0eJ9TT.js/CSSindex-BpUQv-dt.css |
| npm audit --audit-level=low |exit0,0 vulnerabilidades |
| pip-audit Windows/Linux, export exato todos grupos/hashed |ambos exit0, No known vulnerabilities; locks inalterados |
| Gitleaks histórico e diff completo base→HEAD |exit0/sem leaks, reports correction1/security e SHA final no handoff privado |

Fingerprints correction1/quality:89 fontes backend contra fixture executada,
74 frontend contra clone e4 artefatos de produção, zero divergências.
Matriz final e evidência abaixo; revisão independente do novo SHA ainda obrigatória.

Primeira matriz correction1:127 passed/1 failed.320/390/1440 passaram32 cada;
tablet31 passaram e falhou o seed do teste de capacidade, antes das alterações:
GET rental/versions503 e ação Alterar indisponível, com feedback correto. O fluxo
de cancelamento/retomada reforçado passou em todas as larguras. Trace/relatórios
originais preservados antes do rerun. PostgreSQL registrou duas statement timeouts
em SELECT users FOR UPDATE no instante; a causa da duração do lock não foi
comprovada. Não se alteraram auth, limites, retries, timeouts ou assertions.
Uma nova matriz COMPLETA em browser-rerun1 usa fontes/build/config iguais e
observação PG somente leitura (PIDs/estado/wait/idade/bloqueadores, sem query,
parâmetros ou tokens), para não esconder a ocorrência nem atribuir causa sem prova.

Rerun final INALTERADO:128 passed/exit0,32 por320/390/768/1440, respectivamente
2.1m/2.1m/2.2m/2.4m, em correction1/browser-rerun1. O teste que falhou passou sem
mudar código/assertion/config. Axe sem violações nos estados capturados;
teclado/foco/fonte200%/reduced-motion/empty/loading/error/unknown/success mantidos.
Observador somente leitura capturou2 waits curtos (máximo0.009193s, amostragem1s),
não uma recorrência longa. Isso NÃO comprova a causa do timeout anterior nem
certifica desempenho. Falha127/1 permanece uma limitação documentada, não apagada.

Inspeção real dos QUATRO arquivos novos
`browser-rerun1/captures/{mobile-320,mobile-390,tablet-768,desktop-1440}-cancelled-commercial-summary.png`:
total150, nenhuma parcela75/75 ou50% indevida, orientação explícita de financeiro
vigente e que cancelar não renegocia.320/390 quebram o texto em coluna, sem corte
horizontal;768/1440 mantêm hierarquia e leitura amplas. Também aberto
`tablet-768-resumed-review-viewport.png`: financeiro revisado75+75/líquido200/
excesso50 separado, comprovando que o novo acordo explícito não foi suprimido.
Valores cancelados150/0 e retomados75/75 são assertions DOM reais nas4larguras.
Formulários longos ainda requerem scroll; limites de dispositivos/AT permanecem.

Cleanup correction1: observador16682 encerrou exit0; helperstopPG13PID400exit0;
sem processos próprios residuais, portas15444/8000/4173 livres Linux/Windows,
15442/15443 também livres e PG11parado. MinIO mantém ID/healthy/StartedAt originais.
Originais run01–22 e backups2976SHA256 novamente conferidos após todos os reruns.
Relatórios/capturas da falha e do PASS retidos; fixture/clone/source-correction1
preservados, replay usa helperstart e quality-correction1/browser-correction1 sem
prepare/reset. Gitleaks final do novo commit e SHA no handoff privado, sem
publicar traces/diff bruto. Owner retido, nenhum push/PR/merge/Done/release.

## Falhas originais preservadas

- run01:3 failed/47 passed; três expectativas de head0008 atualizadas para0009.
- run02:2 failed/57 passed; montagem de novos testes incluía objeto FieldInfo e
  chave409 reutilizada com payload distinto, corrigida sem reduzir checagens.
- run03:1 failed/15 passed revelou histórico ordenado por UUID quando UTC empata;
  corrigido ordenar por versão. Frontend7 failed/55 passed +2 erros por mocks sem
  novos exports/DTOstate, corrigidos mocks. Ruff inicial80 problemas de layout e
  imports antes de formatar; ESLint detectou efeito síncrono, corrigido sem exceção.
- run04:17 novos testesPG e62 frontend passaram. run05 fullpytest não executou
  testes por infra/tests ausente no checkout; não contado como PASS. Frontend
  run05:2 failed/63 passed por texto antigo e fixture sem estado, corrigidos inputs.
- run06:3 fluxos browser desktop passaram; depois aperfeiçoado diff financeiro e
  apresentação pt-BR, exigindo nova matriz. run07:472 fullpytest passaram antes de
  adicionar dois testes de backfill/reconciliação e cópia real.
- run09:124 passed/4 failed (31/1 em cada largura): feedback503 bruto no helper
  rentalRequest, divergente do
  teste anterior. Corrigido helper para orientação pública em português; assert
  original permanece. Logs/traces/capturas da falha retidos; nova rodada obrigatória.
- run11:474 pytest passaram antes da correção adicional de identidade ORM. O teste
  determinístico foi acrescentado por revisão própria, sem esperar uma falha
  intermitente: leitura locked usa populate_existing para observar cancelamento
  concorrente. A matriz intermediária não substitui a validação final desse código.
- Revisão própria também corrigiu o editor compartilhado para tratar qualquer5xx
  como resultado desconhecido, não somente503. O novo teste mantém a perda de ACK
  original e acrescenta502 após replay200 do servidor: três payloads iguais,
  campos congelados até reconciliar e uma única revisão. Não relaxa o teste anterior.
- run14 mantém provas intermediárias da correção ORM/5xx. A inspeção das mensagens
  herdadas encontrou afirmações incorretas de alocação preservada para cancelada
  com dinheiro pendente e de estoque comprometido para solicitação em review.
  Textos agora distinguem estado/alocação/financeiro; dois testes unitários novos e
  assert no browser impedem essas afirmações. Limite do motivo rental na UI foi
  alinhado a1000 do DTO (o editor normal #10 mantém4000). run15:67 frontend passaram.
  A rodada final seguinte usa exatamente esse build, com relatórios anteriores
  retidos antes de iniciar. Nenhuma falha foi escondida nem pipeline enfraquecido.
- Conferência dos arquivos identificou colisão de duas capturas genéricas
  (`loading`/`read-error`) com o teste de reservas na mesma rodada. Nessas rodadas
  intermediárias não se usa esses dois PNGs como prova visual da alteração:
  foram substituídos pelo teste posterior da própria rodada. Nenhum conjunto
  anterior #11/#12 foi alterado. Nomes exclusivos `changes-loading` e
  `changes-read-error` corrigem a evidência; a última matriz completa repete o
  mesmo build de produção e todas as assertions, sem alteração funcional.
- run18:128 browser passaram, ainda intermediários. A inspeção real390 após
  cancelamento descobriu uma regressão financeira:500/150 voltavam ao sinal
  estimado50% só por mudar para cancelled; no caso150, total restante0 aparecia
  junto de saldo parcial75. run19 reproduz as duas variantes:2 failed/14 deselected
  em filtro intencional de diagnóstico, não gate final. Log original retido.
  Cancelamento agora mantém todos os termos e snapshot financeiros anteriores;
  somente o contexto SERVIDOR da retomada explicitamente conferida usa o novo
  acordo50% na conciliação e no snapshot/evento, sem mudar a locação antes de
  terminar a transação. O browser exige cancelada sinal150/saldo0, seguida de
  retomada snapshot75/sinal validado. run20 full477passed substitui esses resultados
  intermediários; a última matriz usa source-verified. Nenhum dinheiro foi criado,
  devolvido ou transferido e nenhuma decisão comercial nova foi introduzida.

## Limitações e entrega

Capturas usam Chromium sintético em produção, não dispositivos físicos. Axe e
inspeção visual não certificam tecnologia assistiva, usabilidade operacional,
legalidade ou acessibilidade universal. Nenhum dado financeiro/cliente real.
Out/completed são somente guards/contrato futuro: PostgreSQL real de #14 não é
simulado para declarar cobertura. #15 compara revisão comercial; contratos e
assinaturas não foram implementados. Ausência de CI/proteção não é check passado;
verificação remota/revisão independente/PR/merge/ProjectDone ficam com coordenador.
Cleanup da rodada0: helper stop exit0; PostgreSQL13 sem servidor, PID398 inexistente,
nenhum browser_server/helperbrowser/vitepreview residual. Loopback15444/8000/4173
sem listeners Linux/Windows,15442/15443 também livres; PostgreSQL11 segue parado.
MinIO do usuário mantém IDf419de217de93134b0933add2efcf516f22a5fbf2565e23ac669b75eb45b50c6,
running/healthy e StartedAt2026-10-09T02:04:38.643313867Z inalterados.
Fixture13 e clone privados, logs/capturas/relatórios de todas as rodadas retidos.
Helper `start` permite revisar usando a MESMA fixture sem prepare/reset;
não houve shutdown global WSL/Docker, remoção de dados ou interrupção alheia.
Owner não é liberado pelo executor. SHA final e resultados finais Gitleaks no
handoff/checkpoint, revisão independente ainda obrigatória.
