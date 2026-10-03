# ROP-008 — Evidências do catálogo

Plano humano `catalog-v1`, [issue #8](https://github.com/raphaelgarcia7/rentalops-agent/issues/8), revisão aprovada `2026-10-03T14:02:35Z`, SHA256 do corpo UTF-8 `9ce4b34d465e21aa35843a1c0e1b670349983e1045a345d9ed1f3aa2bac6b72b`. O executor leu o corpo completo pelo conector GitHub antes de editar e reconfirmou revisão e igualdade integral do corpo antes dos commits. Dependências #3/#7/#21 Done e merges em develop foram verificadas pelo coordenador antes do despacho. Status do Project é autoritativo; este documento não declara Done.

Executor único `gpt-6.1-sol/high`, sem planner, outros executores, substituição de modelo ou API paga. Checkout `C:/Users/Raphael/.codex/worktrees/rentalops-catalog/rmg-chatbot`, branch `codex/8-catalog`. Base `31c6d7a37eaa02be6578aff77ba5748eed7d655c`; código/README da entrega inicial validados no commit `bfb0d51758b5434ac781efb35263048576364c96` (`feat: add authenticated product and kit catalog`), head documental inicial `0f263b4f5584ba513f307c05063938a0c40ce7cf`. A correção de revisão abaixo produz novo head exato registrado no journal/handoff, pois um arquivo não contém o SHA de seu próprio commit. Revisão independente deve comparar o head final completo à base.

Raiz compartilhada `C:/Projects/praxis/rmg-chatbot` somente lida para guidance/standards/business rules/delivery/ADR-001 e regressões de infra; mudanças acumuladas do usuário não foram copiadas. Lock `rop008-catalog-20261003-89a88b95` mantido, checkpoints completos preservam os campos anteriores. Nenhuma publicação, PR, mudança de issue/Project, merge, deploy, liberação/expiração de lock ou implementação da #9 pelo executor.

## Critérios de aceite aprovados

| AC (ordem da issue) | Evidência | Resultado local |
| --- | --- | --- |
| 1 — Produtos completos: criar/listar/editar/inativar | `test_minimum_optionals_initial_movement_exact_money_and_independent_variants`, `test_inactivation_edit_audit_no_loss_and_stale_409`; serviço, API e `catalog-live.spec.ts` consultam/editam/inativam cadastro completo, preço exato e quantidade válida | Atendido |
| 2 — Kit com preço próprio, quantidades e sem estoque | `test_kit_aggregation_own_price_missing_nested_and_review`; kit_items referencia products, composição agregada determinística; contrato/tela não oferecem saldo do kit | Atendido |
| 3 — Referência/quantidade inválida e história preservada | Contratos parametrizados, `test_postgres_constraints_references_and_no_hard_delete`, kit inexistente/quantidade zero recusados; inativação mantém IDs/composição/histórico | Atendido |
| 4 — API/telas/testes/estados | API tipada autenticada; 31 Vitest; 84 Playwright de produção, incluindo 12 casos de catálogo nas quatro larguras; loading/error/empty/success, busca/paginação e histórico | Atendido localmente |
| 5 — Produto mínimo e observação opcional | Contrato mínimo nome/preço/quantidade inclusive zero; `test_minimal_exact_zero_and_progressive_optional_fields`, integração observa todos opcionais; UI inicial progressiva não exige foto/detalhe | Atendido |
| 6 — Cor/tamanho com estoque independente | Teste PostgreSQL de variantes e fluxo real com mesa branca/preta em cada viewport; alteração de uma conserva saldo da outra | Atendido |
| 7 — Kit não contém kit | Contrato só aceita product_id; FK somente products; `test_api_kit_missing_nested_rejected_and_inactivation_history`; picker UI busca somente produtos ativos, agrega repetidos | Atendido |
| 8 — Produto não recalcula preço do kit | Integração e navegador editam preço do produto e verificam preço próprio do kit inalterado | Atendido |
| 9 — Ajuste auditado, saldo válido, impacto futuro rastreado | `test_stock_maintenance_partial_release_history_and_rollback`, `test_failed_movement_commit_restores_stock_history_and_next_operation`, `test_two_concurrent_adjustments_keep_one_version_and_one_movement`; actor/session/reason, movimento inicial, entry/withdrawal/correction atômicos, CHECKs e rollback. R08-INV permanece #11 | Catálogo atendido; integração de reserva explicitamente futura |
| 10 — Total/manutenção/aptos/liberação | Testes de serviço verificam 5 totais/1 manutenção/4 aptos, liberação parcial/manual com motivo/ator; navegador registra manutenção e liberação. UI rotula antes dos compromissos do período. R08-RET permanece #14 | Catálogo atendido; recebimento real futuro |
| 11 — Inativo conserva composição e exige revisão | Integração/API/navegador preservam componente inativo e sinalizam needs_review; tentativa de salvar com inativo recusada, substituição/remove resolve; snapshots comerciais não existem ainda. R08-INACT permanece #10/#11 | Catálogo atendido; proposta/reserva futura |

## Matriz de validação do plano

| Linha | Implementação e teste |
| --- | --- |
| 1 — Produtos/limites/opcionais/zero/exatidão | `test_catalog_contracts.py`: limites de nome/campos, strings Decimal sem float, Numeric(12,2), integer/versão, internos recusados; PostgreSQL mínimo/opcionais/observação/zero, variantes independentes e inativação sem perda |
| 2 — Kits/revisão/preço | Serviço/contratos/API/UI validam composição não vazia, qty >=1, agregação/overflow, produto inexistente e kit aninhado, preço próprio e revisão por inativo |
| 3 — Estoque/PostgreSQL real | Migração 0003→0004, upgrade repetido, downgrade→0003 preserva auth e upgrade novamente; metadata exata, CHECKs/FKs; total/manutenção/liberação, falha de commit rollback; dois threads com mesma versão produzem um commit/um 409, sem movimento extra |
| 4 — API/sessão/origem/autoria | `test_api_auth_origin_actor_validation_contracts_versions_and_status`: sessão real #21, 401/403/404/409/422/503, autoria obtida da sessão, extras recusados, version atômica, lista padrão25/máximo100, ordenação nome/UUID e busca literal; respostas tipadas sem SQL/caminho |
| 5 — Fotos privadas | `test_catalog_storage.py` e `test_catalog_api.py`: JPEG/PNG/WebP, EXIF removido, MIME/disfarce recusado, 10MiB/20MP, multipart inclusive chunked limitado antes de parser, traversal/URLs, root Git/público/relativo e junction real Windows/ancestor recusados. Fsync/DB/versão falhos compensam só arquivo novo, foto anterior preservada; commit confirmado seguido de perda de conexão mantém asset referenciado. Principal/ordem/desassociação, bytes/hash imutáveis, histórico acessível só autenticado, nosniff/no-store |
| 6 — UI/UX | Produtos/kits criar/buscar/editar/inativar, ajuste/manutenção/liberação, upload/principal/ordem/desassociação e revisão de kit; conflito real 409 preserva rascunho e exige consulta/retentativa explícita; estados controlados, teclado/foco, overflow e axe/reduced motion nas quatro larguras; inspeção visual abaixo |
| 7 — Pipeline/revisão/head/base | Pipeline local abaixo. Revisão independente `gpt-6-sol/high` do head final e gates remotos ainda pertencem ao coordenador, não são resultados locais aprovados |

Sem componentes internos de produto, kits aninhados, reservas, alocações/holds, pagamentos, proposta, retorno real ou abstrações futuras. Serviços determinísticos reutilizáveis não dependem de FastAPI/IA. Fotos opcionais não inventadas; contrato final ilustrado continua #15, volume/backup #4. Não declarar integrações R08-INV/RET/INACT futuras como testadas.

## Pipeline local

Ambiente Windows, Python 3.14.7, uv 0.12.12, Node 24.18.0/npm 11.16.0, PostgreSQL oficial 17.10; imagens e contas somente sintéticas. Comandos backend na raiz do checkout, frontend em `frontend/`; integração recebe `TEST_DATABASE_URL=postgresql+psycopg://rentalops_test@127.0.0.1:15437/rentalops_test`, distinto do desenvolvimento. Infra compartilhada é executada sem copiar seus fontes.

| Comando | Resultado observado |
| --- | --- |
| `uv sync --project backend --locked` | Exit 0; 88 pacotes resolvidos, 87 instalados; única nova dependência Pillow 12.3.0 locked |
| `uv run --project backend ruff check backend C:/Projects/praxis/rmg-chatbot/infra/automation C:/Projects/praxis/rmg-chatbot/infra/tests` | Exit 0, All checks passed |
| `uv run --project backend ruff format --check backend C:/Projects/praxis/rmg-chatbot/infra/automation C:/Projects/praxis/rmg-chatbot/infra/tests` | Exit 0, 36 files already formatted |
| `uv run --project backend mypy --config-file backend/pyproject.toml` | Exit 0, strict, 14 source files sem erros |
| `uv run --project backend pytest backend/tests C:/Projects/praxis/rmg-chatbot/infra/tests -q` | Exit 0, **167 passed**, 2 warnings, 45.34s, sem skips |
| `uv export --project backend --locked --all-groups --no-emit-project --format requirements-txt --output-file C:/Users/Raphael/.codex/tmp/rop008-audit-89a88b95/requirements.txt` | Exit 0, export locked de todos os grupos sem emitir projeto; acrescentar `--quiet` ao reproduzir evita saída extensa |
| `uv run --project backend pip-audit --requirement C:/Users/Raphael/.codex/tmp/rop008-audit-89a88b95/requirements.txt --no-deps --disable-pip --progress-spinner off` | Exit 0, No known vulnerabilities found |
| `npm ci` | Exit 0, 243 pacotes instalados/244 auditados, zero vulnerabilidades |
| `npm run lint` / `npm run format:check` | Exit 0 ambos; nenhum ignore novo de regra |
| `npm test` | Exit 0, **31 passed**, 3 arquivos, 11.76s no código final |
| `npm run build` | Exit 0, TypeScript e Vite produção, 108 módulos; asset final `index-qGuObfmP.js` |
| `npm audit --audit-level=high` | Exit 0, found 0 vulnerabilities |
| `npm run test:e2e -- --workers=2` | Exit 0, **84 passed (1.8m)**; 72 regressões existentes + 12 catálogo, sem retry/skip. Axe sem violações em todas as auditorias |
| `npm run test:e2e -- catalog-live.spec.ts catalog-states.spec.ts --workers=2` | Exit 0, **12 passed (56.4s)** no build final após correção apenas de ajuda textual específica produto/kit; quatro larguras, sem retry/skip |
| Gitleaks 8.30.1 `git --pre-commit --staged --redact --report-format json --report-path <audit>/gitleaks-staged.json` | Exit 0, ~212.92KB staged, no leaks found |
| Gitleaks `git --redact --report-format json --report-path <audit>/gitleaks-history.json` | Exit 0, 14 commits no código validado, no leaks found; repetido no head documental final |
| Gitleaks `git --redact --log-opts "31c6d7a37eaa02be6578aff77ba5748eed7d655c..HEAD" --report-format json --report-path <audit>/gitleaks-task.json` | Exit 0, 1 commit/~212.92KB, no leaks found; diff final e histórico novamente no handoff |
| `git diff --check` / `git diff --cached --check` | Exit 0; aviso Git LF→CRLF nos fontes backend/lock não alterou conteúdo lógico |

`<audit>` é `C:/Users/Raphael/.codex/tmp/rop008-audit-89a88b95`; executável Gitleaks reutilizado em `C:/Users/Raphael/.codex/tmp/rop007-postgres-20261003-5d9bf762/gitleaks/gitleaks.exe`. Relatórios e export fora do Git. Um scan adicional inadequado em modo directory incluiu a `.venv` ignorada inteira e reportou 211 achados em dependências de terceiros (200 no índice de licenças, 11 nos demais fontes instalados); só filenames agrupados foram inspecionados. Isso não foi confundido com scan tracked aprovado: scans obrigatórios staged/histórico/task acima passaram sem allowlist/ignore/bypass.

Falhas iniciais corrigidas com regressão, sem enfraquecer regra/assertion: Windows não permite symlink sem privilégio, portanto teste usa junction real via API Windows (sem skip); limitação de multipart inicialmente dentro do parser virava 400, corrigida para buffer/replay limitado antes dele e teste chunked413; expectativa antiga da migração auth agora mira exatamente 0003, enquanto catálogo verifica head; tratamento de descompressão preserva 413; compensação do arquivo protege resultado incerto de commit. Primeira rodada completa de browser: 76 passed/4 failed por link de retorno duplicado nos estados novos; StatePanel reutilizado recebeu opção de ocultar esse link, assert/regressão preservados; rodada completa final 84 passed.

Warnings preservados: Starlette recomenda httpx2 e avisa alias AnyIO BlockingPortal; pip-audit alerta sobre `--no-deps` apesar do export locked; Playwright informa NO_COLOR ignorado quando FORCE_COLOR está ativo. Não representam testes omitidos. Ausência de CI/proteções foi confirmada pelo coordenador antes do despacho, lacuna pendente #6; o executor não inventou workflow nem declarou checks ausentes como aprovados. Coordenador consulta novamente checks/proteções atuais e obtém revisão independente antes de integrar.

## Banco, arquivos e limpeza segura

Cluster descartável oficial `C:/Users/Raphael/.codex/tmp/rop007-postgres-20261003-5d9bf762/data`, binários `C:/Program Files/PostgreSQL/17/bin`, PID principal52696, listener verificado somente `127.0.0.1:15437`. Conta/banco sintéticos `rentalops_test`; nenhum serviço existente, senha, conta real ou configuração de produção alterados. Cada pytest e harness validam alvo seguro e usam schemas `rentalops_test_<UUID>` próprios; somente esses namespaces são removidos. Browser usa tempfile privado próprio fora do Git, imagens geradas sintéticas e teardown explícito dos seus arquivos/schema. Nenhuma foto real criada, copiada ou apagada.

Depois da suíte completa e novamente após o rerun final, consulta `SELECT count(*) FROM pg_namespace WHERE nspname LIKE 'rentalops_test_%'` retornou **0**, sem listeners8000/4173; só15437 em127.0.0.1/PID52696 permaneceu. Cluster15437 fica disponível para revisor; lock permanece. Nenhum banco/diretório do usuário foi limpo. Produção não importa endpoints `__test` nem aplica DDL em startup. Fotos de teste só existem em temporary directory própria durante o harness.

## Inspeção visual e limites

Capturas ignoradas em `frontend/test-results/evidence/`, relatório `frontend/playwright-report/`. Inspeção explícita pelo executor: `mobile-320-catalog-product.png`, `mobile-390-catalog-conflict.png`, `tablet-768-catalog-keyboard-form.png`, `desktop-1440-catalog-kit-form.png`. Evidências nas quatro larguras incluem também lista/cadastro, manutenção, foto, kit precisando de revisão, consulta de conflito e estados loading/error/empty. Capturas usam somente nomes/dados comerciais sintéticos; autenticação não aparece com senha/link privado preenchido.

Texto, hierarquia/feedback, margens e controles legíveis nessas imagens, foco visível na descrição via teclado, formulários progressivos responsivos, sem corte horizontal; em320px há rolagem vertical normal. Playwright verifica overflow, keyboard/focus, reduced motion e axe em Chromium de produção. Não foram testados aparelhos físicos, Safari/Firefox, leitores de tela, zoom do navegador, comparação pixel-baseline, todos os dispositivos ou operação real pela locadora. Auditoria automatizada não certifica acessibilidade/usabilidade integral. Não existe disponibilidade por período, integração de reservas/recebimento/contrato ou validação de volume/backup operacional nesta entrega.

## Handoff e gates restantes

README documenta setup/storage/limites/API e rastreio das integrações futuras; código permanece local. Após registrar resultado da última repetição e head final, executor interrompe implementação. Próximos gates: revisão independente `gpt-6-sol/high` do head final, correções se necessárias, verificação remota das dependências/base/checks/proteções e quota/modelo, publicação/PR não draft no mesmo repo/develop, squash remoto confirmado e Project Done pelo coordenador. Nenhum desses gates pendentes é rotulado como concluído aqui.

## Correção da revisão independente — ROUND1

Revisor separado `gpt-6-sol/high` avaliou exatamente `0f263b4f5584ba513f307c05063938a0c40ce7cf` e confirmou 167 pytest, 84 Playwright, linters/build/auditorias/scans, mas encontrou dois bloqueadores. A validação inicial acima permanece como histórico, não aprovação independente: (1) `PhotoStorage.checked_root` aceitava a pasta descartável `Frontend/Public` no Windows por comparar componentes com caixa exata; (2) primeira execução completa Vitest do revisor teve **30 passed/1 failed** na asserção de foco, seguida de **15 passed** isolados e **31 passed** completos, demonstrando sincronização não determinística do teste original.

Correções limitadas aos bloqueadores:

- Componentes de caminho agora são comparados por `casefold` em todos os hosts, impedindo configuração pública por variação de caixa inclusive após mudança de plataforma. Doze regressões combinam seis variações de `frontend/public` com root direto e ancestor de uma subpasta; retornam 503 genérico e não escrevem arquivos. Defesas Git/traversal/root e junction/symlink permanecem intactas, incluindo teste real Windows.
- O teste de foco controla a promessa do check de sessão, verifica primeiro o estado `Verificando acesso…`, conclui a microtask da requisição e resolve401 dentro de `act`, que completa os efeitos React; só então obtém o título final e aplica a mesma asserção `toHaveFocus`. Nenhuma alteração de runtime auth, sleep, test retry, skip ou relaxamento de assertion. Primeira tentativa desta correção esperava o título de login antes de resolver a promessa e teve **30 passed/1 failed**; corrigida a ordem conforme o contrato real. Esse resultado não foi omitido nem chamado de aprovado.

| Revalidação ROUND1 (mesmos comandos da tabela inicial) | Resultado observado no código corrigido |
| --- | --- |
| `pytest backend/tests/unit/test_catalog_storage.py -q` | **32 passed**, 0.75s |
| `uv sync --project backend --locked` | Exit0; 88 resolvidos/87 verificados, nenhum dependency change |
| Ruff check / format check / mypy strict | Exit0; 36 arquivos formatados, 14 fontes sem erros |
| Pytest backend + infra compartilhada com PostgreSQL real | Exit0, **179 passed**, 2 warnings preservados, 53.49s; incremento12 de regressões de caixa/ancestor |
| Export locked all-groups e pip-audit | Exit0 ambos; No known vulnerabilities found, avisos anteriores preservados |
| npm ci / lint / format:check | Exit0 todos; 243 instalados/244 auditados, zero vulnerabilidades |
| Três execuções completas independentes `npm test` no código final | Exit0 em cada, **31 passed**/3 arquivos, 60.05s, 60.19s e 11.63s; duas execuções concorrentes tiveram custo maior de inicialização do ambiente. Sem retries da ferramenta/teste |
| Build TypeScript/Vite e npm audit | Exit0 ambos; 108 módulos, mesmo asset de produção `index-qGuObfmP.js`; zero vulnerabilidades |
| Playwright completo contra produção/API/PostgreSQL reais | Exit0, **84 passed (1.8m)**, quatro larguras e axe sem violações; sem retry/skip |
| Gitleaks staged ROUND1 | Exit0, no leaks found; repetido após atualização final deste registro |
| Gitleaks histórico e task diff após commit ROUND1 | Executados no head final; resultado e SHA registrados no journal/handoff |

Revisão/correção não expandiu escopo nem alterou aprovação. Conector GitHub reconfirmou a revisão `2026-10-03T14:02:35Z` e igualdade integral do corpo aprovado nesta rodada. Mesmo owner/worktree/base; nenhum outro agente implementou. Após browser final, zero schemas próprios e nenhum listener8000/4173; somente PG descartável127.0.0.1:15437/PID52696 preservado. Scans tracked/staged/histórico, commit e novo head são registrados no handoff/journal após os gates. Continuam pendentes nova revisão independente exata e integração remota; não declarar Done.
