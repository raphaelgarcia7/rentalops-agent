# ROP-004 — operations-prep-v1: evidências locais

Plano humano: [issue4](https://github.com/raphaelgarcia7/rentalops-agent/issues/4),
updated_at `2026-10-09T00:27:44Z`, body UTF-8 SHA256
`70d2b4f705844b565bb02855b5a6c05b20bed68f79ac28532dbf0d534744e5e2`.
Reconsulta pelo conector antes da entrega confirmou issue aberta, mesma revisão e
body exatamente igual ao snapshot aprovado. O coordenador confirmou Project
In progress e dependência #7 Done/remotamente integrada antes do despacho.

Base `4184cb193a23abfe51a8f16f9f63aa39199a6d4b`, branch `codex/4-operations`, checkout
isolado `C:/Users/Raphael/.codex/worktrees/rentalops-customers/rmg-chatbot`. Nenhum código
do root sujo foi copiado. Processo/padrões/regras/ADR-001 foram lidos explicitamente
na raiz porque não existem completos no checkout limpo; essa lacuna não autorizou
publicar CI/configurações acumuladas. Executor `gpt-6.1-sol/high`, agente
`/root/rop004_executor`. Owner compartilhado `rop004-operations-20261009-70d2b4f7-run1`;
checkpoints preservam metadados da aprovação e SHA. Head exato da entrega é registrado
no journal/relatório do coordenador após o commit; revisão independente deve usar
esse head e esta base, sem substituir modelos.

## Matriz AC → implementação e evidência

| AC | Evidência local | Limite/gate restante |
| --- | --- | --- |
| OPS-01 configuração reproduzível, secrets, root privado, legado | `infra/operations/compose.yaml`, Dockerfiles com índices de imagens por digest, `.dockerignore`, env explícito e documentação; `docker compose ... config --quiet` exit0 com placeholders externos; AuthSettings existente e OPERATIONS_ROOT obrigatório em produção; `private_path` rejeita links/junctions/ACL pública/paths relativos/Git; suíte completa preserva fluxos legados | Docker Linux daemon ausente (pipe DockerDesktopLinuxEngine inexistente); build/start de containers Linux **não executado**, nenhum deploy. Pacotes APT recebem patches; não certificar build bit a bit. Ensaio no host Linux antes de exposição segue gate do runbook |
| OPS-02 backup/restore real, vínculos/bytes/histórico/login/contagens | `test_real_backup_restore_login_queries_photos_history_and_revocation`: PostgreSQL17 real, migrações0001–0006, usuário/cliente/produtos/kit/orçamento; foto original detached após orçamento e substituta; age real; copy em diretório independente; pg_restore real em banco novo; contagens/digests das22tabelas, FK/constraints e2fotos; consulta/revisões e login por senha após revogação | Ensaio sintético muito pequeno; copy é diretório local independente, **não off-host real**; não certifica RPO24h/RTO4h de produção |
| OPS-03 recusas, source preservado e autoridade revogada | chave age errada, ciphertext corrupto, foto ausente, manifest cifrado/autenticado incompleto, falha de pg_dump no meio, DB/storage não vazio e target sem nome/opção aprovada recusados; sem ponto incompleto publicado; source fingerprint igual após recusas; sessão e link antigos falham, login novo funciona; cópia não sobrescreve ponto | Destino falho fica descartável/fechado para investigação; sem overwrite/cleanup automático de produção. CLI restrita a `rentalops_restore_test_<32hex>` em loopback e opção explícita |
| OPS-04 readiness, manutenção, atraso e logs | `/health`liveness200 e `/ready`DB/schema/storage; outage DB/asset/migration gera503 controlado; backup ausente/>24h gera alert/exit2; `test_barrier_drains_existing_operations_and_refuses_new_writes` e `test_backup_drains_real_upload_before_database_and_file_snapshot`; backend uvicorn+nginx1.30.5 reais em portas isoladas usando config de logs do container/proxy, sentinelas privadas omitidas | Windows proxy substitui apenas paths/ports/upstream dos artefatos Linux para ensaio; não certifica TLS/proxy externo. Monitor contratado/alert unit ainda não implantados |
| OPS-05 runbook, retenção, recuperação/incidentes e gates honestos | `infra/operations/README.md`: config/secrets/contas/revogação/TLS/acessos; backup diário/copy/verify/idade/falha;30dias sem autopurge; restore/checks/cutover humano; migração compatível/rollback; incidentes DB/storage/chave/segredo; templates systemd adaptáveis | fornecedor/domínio/TLS/acessos reais, destino externo/monitor, retenção legal e treino com volume representativo permanecem gates de exposição, não fatos realizados |
| OPS-06 qualidade/head/base/revisão/PR | resultados exatos abaixo; Ruff/format/mypy/pytest realPG/pip-audit/npm gates/Gitleaks e Playwright+axe | revisão independente `gpt-6-sol/high` do head atual, PR develop e checks/proteções remotos são do coordenador e permanecem pendentes nesta entrega do executor |

## Ensaio de recuperação e segurança

PostgreSQL17.10 do cluster previamente autorizado de teste, somente loopback
`127.0.0.1:15437`, usuário/banco sintéticos `rentalops_test`. Cada fixture cria apenas
`rentalops_source_test_<UUID>` e `rentalops_restore_test_<UUID>`, aplica migrations no
public desses bancos novos e os elimina por nomes registrados. Não alterou serviço
PostgreSQL existente, credenciais, main ou dados reais. Os demais testes usam schemas
UUID no banco sintético já validado. API/proxy de teste usam portas loopback livres;
processos são encerrados no finally. Fixtures de recuperação removem seus diretórios
privados e identidades age; ferramentas externas podem permanecer para revisão.

Execução final OPS-02 no subset: **backup 0.862s, restore 1.042s**, pacote cifrado
**82136 bytes**, arquivos privados **164 bytes**, **22 tabelas e 2 fotos**. Medidas incluem
CLI/DB/arquivos, não aquisição de host, transporte externo, contato humano ou cutover.
Snapshot recente do próprio ensaio não demonstra manter24h de RPO por30dias. O RTO
real é todo o intervalo até recuperação validada/acesso reaberto, não apenas1.042s.

Barreira compartilha locks no volume privado: primeiro reserva intenção exclusiva,
recusa novas operações e aguarda as já iniciadas; DB connections/CLI e o serviço de
upload são protegidos. O teste real pausa upload depois de escrever bytes e antes de
persistir metadata; backup aguarda, novas operações são recusadas, upload conclui e
snapshot contém os3metadados/arquivos juntos. Nunca mantém lock esperando modelo.
Operador precisa impedir escritores SQL externos que não usam este app/barreira.
Backup recusa OPERATIONS_ROOT diferente do parâmetro do próprio runner.

Pacote age integra manifest interno e digests de todos os membros; receipt externo é
somente diagnóstico de transporte. Verify autentica/decripta antes de usar os dados;
restauração autentica tudo antes de tocar destino. Revoga sessões/links após conferir
contagens/digests e antes de declarar sucesso, preservando atribuição histórica.

Ferramentas de teste: age1.3.2 oficial; zip Windows SHA256
`f48d8f8f9ebe903ab5027ed067652f2cc1db94bc206976430133b905dcd8e8c7`, conferido com
digest do asset da release GitHub. nginx1.30.5 Windows obtido da página oficial;
SHA256 do zip observado `e5afe28b6a50bec92c478bfe1a4d3758206b80fb77159277bc5c4e88955c2a35`.
Esse hash local não é alegado como verificação de assinatura PGP. Os testes exercitam
binários reais; sem mocks de dump/restore/crypto nos caminhos de sucesso.

## Qualidade local

Comandos executados no checkout isolado (infra/automation e infra/tests referem a
raiz, lidos sem copiar seus arquivos para a branch):

| Verificação | Resultado |
| --- | --- |
| `uv sync --project backend --locked` |91packages resolvidos, ambiente locked instalado; portalocker3.2/pywin32 Windows condicional |
| `uv run --project backend ruff check backend infra/operations C:/Projects/praxis/rmg-chatbot/infra/automation C:/Projects/praxis/rmg-chatbot/infra/tests` |passou |
| `uv run --project backend ruff format --check backend infra/operations C:/Projects/praxis/rmg-chatbot/infra/automation C:/Projects/praxis/rmg-chatbot/infra/tests` |62arquivos formatados |
| `uv run --project backend mypy --config-file backend/pyproject.toml` |27fontes, sem problemas; inclui tooling operations |
| `uv run --project backend pytest backend/tests C:/Projects/praxis/rmg-chatbot/infra/tests -q --tb=short` com TEST_DATABASE_URL/age/PG/nginx sintéticos |**295passed,2warnings,164.94s**, sem skip |
| Subset final operations/unit/legacy-readiness após guard de configuração/cleanup |**13passed,2warnings,81.06s**; OPS-02 medidas acima |
| `uv export --project backend --locked --all-groups --no-emit-project ...` + `pip-audit --no-deps --disable-pip -r ...` |sem vulnerabilidades conhecidas; avisos de uso --no-deps foram explícitos, export inclui hashes/deps/dev |
| `npm ci` após encerrar o primeiro browser/harness |243packages instalados/244auditados; zero vulnerabilidades |
| `npm run lint`, `npm run format:check` |passaram |
| `npm test` |44tests em5files passaram,58.45s |
| `npm run build` |TypeScript/Vite passaram;120módulos;988ms de build Vite |
| `npm audit --audit-level=high` |zero vulnerabilidades após patch transitivo source-map-js1.2.2 |
| `npm run test:e2e` após install/build sequenciais |**100 passed (2.6m)**, sem retries/skips; quatro larguras 320/390/768/1440, axe, keyboard/focus/reduced motion e API/PG reais |
| `gitleaks git --redact --no-banner --log-opts=--all .` |23commits/~2.64MB, sem leaks antes do commit; scan final de diff/history registrado no journal |
| `docker compose -f infra/operations/compose.yaml config --quiet` com placeholders externos |exit0; cinco índices de imagem conferidos remotamente por digest; daemon Linux ausente, nenhum build/start anunciado |

Warnings conhecidos: deprecações upstream Starlette/httpx e anyio BlockingPortal;
não são skips nem falhas de segurança aprovadas por exceção. Backend/API/frontend
continuam funcionando pelos fluxos de regressão. Não houve alteração visual/funcional
de tela; capturas sintéticas finais ficam em `frontend/test-results/evidence/`, relatório
Playwright em `frontend/playwright-report/`, ignorados pelo Git. Capturas de quatro
larguras e testes automatizados não certificam todos os dispositivos ou usabilidade
operacional da equipe.

Inspeção das capturas reais finais: `mobile-320-quotations-error.png` mostra mensagem
de indisponibilidade/retry acessível e navegação inteira; `mobile-390-quotations-saved.png`
preserva composição/histórico e aviso de que orçamento não reserva estoque;
`tablet-768-quotations-keyboard.png` mostra foco visível na busca e formulário em duas
colunas legíveis; `desktop-1440-home.png` mostra navegação lateral e três cards sem
corte horizontal. Foram geradas **196 capturas sintéticas**, sem atualização de baseline
para ocultar diferença. Essa inspeção não afirma ter revisado visualmente todas elas.

Após as suítes: **0 bancos source/restore desta tarefa, 0 schemas rentalops_test_UUID
e 0 listeners nas portas 8000/4173**. O cluster sintético pré-existente permanece para
revisão por ser recurso anteriormente autorizado; nenhum serviço do usuário foi parado.

## Falhas iniciais preservadas

- Coleta inicial operations falhou sem import do namespace infra; pytest pythonpath
  foi declarado para a raiz. Nenhum teste foi marcado skip.
- Fixture tentou issue-access-link em conta já inicializada:4unitpass/5setup-errors;
  corrigida para criar segunda conta sintética com link pendente sem revogar a sessão
  da primeira antes do backup.
- Lint inicial identificou imports/format/linhas longas/asserção genérica; corrigidos
  com formatters e `pytest.raises(CatalogError)` tipado, sem relaxar comportamento.
- Proxy Windows inicialmente faltava diretório fastcgi_temp/default log; fixture
  passou a criar somente seus diretórios locais exigidos pelo binário. Config Linux
  não foi alterada para ocultar o erro.
- Corrida inicial de intent lock falhou em teste de drenagem; aquisição de manutenção
  agora espera a breve entrada em andamento antes de reservar intenção, enquanto
  novas operações continuam nonblocking. Teste de corrida e upload real passaram.
- Primeiro fullpytest: **1failed,293passed,148.55s**. Readiness antigo preparava
  conectividade mas não storage/schema no engine novo; fixture fornece namespace
  migrado real e diretório privado, mantendo asserts ready200/outage503.
- npm audit apontou **high GHSA-68fv-2mgg-jv7q** em source-map-js1.2.1. Somente o patch
  transitivo1.2.2/resolved/integrity foi atualizado no lock; sem suppress/exception.
- Primeira execução Playwright: **90passed/10workerfail,2.9m**. Executor iniciou npm ci
  antes de encerrar browser; Windows recusou unlink do binding carregado e modules
  ficaram incompletos. Resultado não foi aceito. Processos terminaram, npm ci separado
  passou, todos os gates foram repetidos sequencialmente. Sem retry/skip/assertweakening.

## Entrega e gates restantes

Esta entrega prepara operação, sem lançamento/merge/deploy/main. PR/publicação,
revisão independente exata, reconciliação remota/Project Done e liberação condicional
do owner são responsabilidades do coordenador. Confirmar estado remoto/checks
existentes; ausência de CI/proteção não é check aprovado. O Docker daemon Linux
indisponível é limitação explícita do ensaio local; não modificar serviços existentes
para simular aprovação. Runbook mantém teste de build/start no host Linux e todos os
gates comerciais/operacionais/TLS/off-host antes de exposição.
