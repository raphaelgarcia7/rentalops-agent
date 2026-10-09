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
| OPS-01 configuração reproduzível, secrets, root privado, legado | Compose/Dockerfiles por digest, `.dockerignore`; wrapper valida paths brutos/sources resolvidos no host;62 regressões; binds sem autocreate; retomada autorizada em ext4/rootless passou validate/build/up, migração, readiness, login/upload/bytes e guard real UID10001; legado na suíte359pytest | Falha NTFS0777 e bloqueio anterior preservados abaixo, resolvidos somente pelo preparo nativo autorizado. Ensaio final do SHA/base e revisão exata registrados no checkpoint/journal; não certifica implantação real |
| OPS-02 backup/restore real, vínculos/bytes/histórico/login/contagens | `test_real_backup_restore_login_queries_photos_history_and_revocation`: PostgreSQL17 real, migrações0001–0006, usuário/cliente/produtos/kit/orçamento; foto original detached após orçamento e substituta; age real; copy em diretório independente; pg_restore real em banco novo; contagens/digests das22tabelas, FK/constraints e2fotos; consulta/revisões e login por senha após revogação | Ensaio sintético muito pequeno; copy é diretório local independente, **não off-host real**; não certifica RPO24h/RTO4h de produção |
| OPS-03 recusas, source preservado e autoridade revogada | chave age errada, ciphertext corrupto, foto ausente, manifest cifrado/autenticado incompleto, falha de pg_dump no meio, DB/storage não vazio e target sem nome/opção aprovada recusados; sem ponto incompleto publicado; source fingerprint igual após recusas; sessão e link antigos falham, login novo funciona; cópia não sobrescreve ponto | Destino falho fica descartável/fechado para investigação; sem overwrite/cleanup automático de produção. CLI restrita a `rentalops_restore_test_<32hex>` em loopback e opção explícita |
| OPS-04 readiness, manutenção, atraso e logs | Retomada ext4: nginx/backend reais health/ready200, storage0000 e DB próprio indisponível→ready503/liveness200→recuperação200;22JSON backend+34proxy sem body/query/headers/token/DSN/paths/chaves. Rodada2 corrige acesso efetivo do storage com regressões unit/PG, além do ensaio UID10001 | Falha original readiness200/storage inacessível preservada abaixo; TLS externo/monitor/alert unit não implantados; prova Windows anterior continua distinta |
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

Os resultados desta seção são da entrega inicial `ea8ed9d1f89675bef7cd49284fe597950cc275e5`,
que recebeu **FAIL** na revisão independente. Não são aprovação de OPS-01 nem
resultados do novo head. A rodada de correção e suas verificações estão abaixo.

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

## Correção rodada1 — mesmo owner, plano e modelo

Revisão independente `gpt-6-sol/high` do head inicial: **FAIL**. Reprodução real
`docker compose config --quiet` com `./relative-data`/photos/operations retornou0,
sources resolvidos dentro do Git. Interpolação `:?` só exigia texto não vazio;
a API via `/private` não enxergava a origem host. Build/start/health Linux ausentes
tornaram OPS-01 incompleto. Nenhuma PR/integração ocorreu.

`infra/operations/runtime.py` é a entrada de operação documentada. Valores do arquivo
compose.env privado e overrides do ambiente são verificados antes de chamar Docker;
não são normalizados para disfarçar path relativo/link. O modelo JSON resolvido pelo
Compose real (sem expandir conteúdo backend.env) é capturado, validado e descartado:
somente os três binds nos destinos esperados, env_file e secret externos esperados.
Rejeita Git, diretórios públicos convencionais, permissões públicas, links/junctions,
paths inexistentes/tipo errado/roots/overlap/config dentro dos volumes. O root privado
imediato também deve ser privado para impedir substituição do entry. Não faz chmod,
mkdir ou reparo automático. Build/up revalidam antes de mutação; stdout/stderr do
Compose não são publicados. Up aguarda readiness via `--wait` e falha fechada.
Compose direto contorna esse guard de host e não é o procedimento suportado.

`test_operations_runtime.py`: 62 novas regressões passaram em6.09s, sem skip,
incluindo paths relativos/vazios de todos os cinco inputs recusados para cada ação,
ACL pública real, junction/symlink real, paths Git/públicos/overlap, configuração
resolvida divergente bloqueando build/up, parser Compose real sem engine e erro CLI
redigido. Primeira passagem Ruff apontou imports/linhas longas/catch amplo; formatter
e exceções explícitas corrigiram; Ruff64files/mypy28 passaram posteriormente.

Pipeline da rodada1 (mesmos comandos da qualidade acima, sem instalações concorrentes):

| Verificação | Resultado rodada1 |
| --- | --- |
| Ruff/lint/format, incluindo automation/tests da raiz lidos sem copiar |passou;64files formatados |
| mypy backend/src + infra/operations |28fontes, sem problemas |
| pytest completo backend + automation, PostgreSQL17/age/nginx reais |**357passed,2warnings,153.25s**, sem skip (295originais+62novos) |
| uv export locked/all-groups/hashes + pip-audit |sem vulnerabilidades conhecidas; warning --no-deps explícito |
| ESLint/Prettier |passaram |
| Vitest |**44passed/5files,16.39s** |
| TypeScript/Vite build |passou;120módulos;399ms Vite |
| npm audit --audit-level=high |zero vulnerabilidades |
| Playwright/axe produção/PG/320–390–768–1440 |**100passed,2.6m**, sem retry/skip |
| Gitleaks staged diff / história |28.46KB/24commits2.74MB,0leaks; scan final pós-commit registrado no checkpoint |
| Plano por conector GitHub vs snapshot aprovado |body igual, SHA25670d2b4f7…, updated_at preservado, issue aberta |

Head exato será registrado no checkpoint/relatório após commit.

As196capturas sintéticas foram regeneradas; as mesmas quatro capturas detalhadas
na inspeção anterior foram novamente abertas/inspecionadas nesta rodada:320error
com retry visível,390saved com histórico/composição,768keyboard com foco claro e
formulário em duas colunas,1440home com navegação e cards sem corte. Não houve
mudança de tela nem atualização de baseline. Não certificar todas as capturas/dispositivos.
Cleanup confirmou0bancos source/restore,0schemas descartáveis,0listeners8000/4173
e nenhum nginx do ensaio. PostgreSQL sintético existente15437/PID52696 preservado.

Runtime externo: contexto desktop-linux usa pipe DockerDesktopLinuxEngine ausente;
`docker info` falha, somente WSL docker-desktop Stopped e nenhum processo Docker no
inventário. Coordenador tentou uma única vez `docker desktop start --detach`, sem
termos/settings/segurança alterados; `docker desktop status` terminou exit1
"Could not retrieve status" e engine continuou indisponível. Executor não repetiu
start nem substituiu Windows proxy por prova Linux. Nenhum container/volume/stack
foi criado, alterado ou removido nesta rodada.

O responsável informou não conseguir disponibilizar o engine agora; a coordenação
confirmou Project **Blocked** na interface. Não houve investigação/inicialização/
configuração adicional após essa resposta. Owner preservado para retomada;#12 não
foi despachada, nenhuma publicação/PR/merge/deploy foi realizada.

Ação humana necessária para OPS-01: abrir o Docker Desktop instalado, resolver sua
inicialização/engine Linux sob controle humano (incluindo qualquer escolha/termo
solicitado pelo aplicativo) e confirmar `docker info` com servidor Linux funcionando.
Depois, retomar **mesma** task/owner para build/start/health/readiness/logs/autenticação/
storage em stack sintético isolado do exact head, e revisão independente. Não usar
essa ação como autorização para deploy, alterar serviços existentes ou avançar #12.

## Retomada Linux — engine disponível, binds privados incompatíveis

O responsável iniciou Docker e autorizou continuar a mesma entrega. Coordenador
reconciliou aprovação/body/revisão/base/owner, Project In progress e cota normal.
Docker CLI Windows + engine Linux29.6.1 foi usado no caminho suportado; nenhuma
distro foi instalada/integrada, nenhum shim interno foi contornado, nenhum socket/
root montado, nenhum termo/settings/firewall/segurança alterado. MinIO preexistente
`minio-minio-1` (ID prefixo f419de217de9, portas9000–9001) e PG15437 preservados.

Fixture exclusiva fora do Git, dirs database/photos/operations/config com ACLs
privadas verificadas pelo wrapper, envs e credenciais **somente sintéticos**, sem
imprimir conteúdos. Projeto único `rentalops-rop004-linux-1dc2485`, frontend somente
loopback18084; nenhum serviço/banco/volume do usuário usado como destino. O Docker
Compose parser real e wrapper `validate` passaram; wrapper `build` passou com os
Dockerfiles exatos do head `1dc2485ea2047faff06e9175bcac2e2b33d94241`:

| Imagem construída | Evidência |
| --- | --- |
| backend Linuxamd64, USER rentalops |`sha256:36eab4bc13632a8f1da1169b7320acd78bcfd2b2f7b08288cce742c68bf88444` |
| frontend Linuxamd64/nginx |`sha256:800b642a6d02d993107f57d0a85e56fc00125fe94f95ede09c69f5789a5c9ece` |

Primeiro wrapper `up --wait --wait-timeout120` retornou exit1 genérico antes do
backend/frontend iniciarem; DB ficou healthy posteriormente. Probe inicial não
encontrou backend running e falhou; não foi aceito como teste passado. Retry pelo
mesmo wrapper iniciou os três serviços, mas terminou novamente exit1. DB healthy,
backend unhealthy, frontend running **não** equivale a OPS-01 aprovado.

Probe real via `docker exec` exclusivamente no backend próprio, sem trocar seu
usuário/volumes/guards: UID10001; `/private/photos` e `/private/operations` vistos
como mode0777. `private_path` recusou ambos corretamente. A ACL privada do source
Windows não produz permissão POSIX privada nesse bind do Docker Desktop. Não houve
chmod/chown para contornar, nem mudança no código de segurança ou no Compose.

HTTP real pelo nginx do container: `/`200, `/api/health`200, `/api/ready`503,
`/api/products`401 sem sessão, `/api/auth/login`503 durante recusa de operations-root.
Respostas não revelaram paths privados. Sentinela sintética em query/body/Cookie/
Authorization/Referer/request-id não apareceu nos logs reais;4records backend JSON
com as seis chaves allowlist e5records proxy. Verificou também ausência dos valores
privados de DSN/rate-key/senha bootstrap e paths em stdout/stderr capturados; nenhum
deles foi impresso como evidência. Logs descartados depois da verificação, sem
guardar payload privado em Git/model trace. Isso prova redaction/fail-closed nesse
stack, **não** login bem-sucedido, schema migrado, upload ou readiness saudável.

Bloqueio atual específico: disponibilizar host/runtime Linux de teste **com
filesystem nativo que preserve os binds POSIX privados**, sob controle humano.
O engine não está ausente. Não instalar/configurar outro ambiente nesta entrega,
não substituir por permissões públicas nem marcar AC completo. Retomar a mesma
task/owner para migração/schema, startup saudável, autenticação/upload/storage e
outages de DB/storage do stack Linux quando esse ambiente existir. Sem re-review,
PR ou merge enquanto esse AC obrigatório estiver incompleto.

Cleanup validou os labels/names exatos dos três containers próprios e configuração
privada antes de `compose down` **somente desse projeto**. Removeu backend/frontend/
database e network próprios; inventário confirmou0containers/networks do projeto e
nenhum listener18084. MinIO f419de217de9 continuou running/healthy, sem tocar suas
portas/volumes. Não houve prune, down global ou remoção de imagem/dado do usuário.

O comando de remoção recursiva do diretório privado sintético foi rejeitado pela
ferramenta antes de executar. Não foi contornado com outra shell, programa ou
permissão. A fixture privada Windows (database/photos/operations/config, helpers e
credenciais **sintéticas**) permanece retida/inativa foraGit, com localização exata
no checkpoint privado; não afirmar que foi apagada. As duas imagens próprias e cache
das bases oficiais também permanecem inativos para diagnóstico/retomada. Sem tokens
ou conteúdos desses arquivos na evidência pública.

Regressão operacional adicional encontrou PostgreSQL de teste15437 indisponível;
inventário read-only não encontrou listener nem PID anteriormente registrado52696.
Nenhuma causa foi inferida e nenhum serviço foi reiniciado/alterado. Não atribuir
esse estado ao Docker ou ao cleanup escopado sem prova. Falhas de setup da integração
são preservadas; sem skip, assertion weakening ou declaração de aprovação atual.
Foram observados66dots e3setup errors, **sem conclusão formal da suíte**. Após
confirmação do coordenador, somente o processo pytest próprio identificado pelos
argumentos exatos foi interrompido, evitando continuar espera por dependência
externa ausente. Resultado é **parcial/interrompido**, integração não concluída;
não converter os dots em total aprovado nem declarar0falhas. Nenhum processo de
outro trabalho foi encerrado. Ruff/lint/format64 e mypy28 passaram novamente; diff
e scan de segredos são verificados na entrega documental.

Mudanças desta retomada são somente evidência; Dockerfiles/backend/frontend/
preflight não mudaram. Checks proporcionais e resumo da suíte adicional são
registrados no checkpoint final com novo SHA documental. Resultados357pytest/
100Playwright/qualidade da rodada1 continuam evidência **histórica** do mesmo conteúdo
de código, não testes executados agora nem substitutos dos gates Linux pendentes.

## Retomada autorizada em filesystem nativo e correção2

Em2026-10-09 o responsável autorizou preparar WSL/Ubuntu e resolver dependências
locais gratuitas/oficiais, com registro na rotina e pipeline. Não autoriza bypass,
termos, gasto/API, serviço/dado existente, reboot, main/deploy ou mudança de produto.
O coordenador registrou a política em `ee91515` e seu link README em `f30172a`;
código anterior permanecia `1dc2485`. A falha NTFS e a suíte parcial interrompida
acima continuam históricas; não foram renomeadas para PASS.

Ubuntu24.04.5/WSL2.7.10 usa ext4. Como a integração Desktop estava desativada e a
GUI não confirmou mudança, instalou-se **Docker Rootless oficial separado** na
distro nova, com usuário sintético UID1000, user namespace/slirp4netns e socket Unix
privado. [Docker Rootless](https://docs.docker.com/engine/security/rootless/) e
[apt Ubuntu oficial](https://docs.docker.com/engine/install/ubuntu/) foram as fontes;
apt com chave/repositório assinado, sem convenience curl|sh. Docker29.9.0,
Compose5.6.0, containerd2.4.1, RootlessKit3.2.0, slirp4netns1.2.1; security options
confirmam rootless/seccomp/cgroupns. Units **novas** rootful docker/socket/containerd
foram masked antes da instalação e permaneceram inativas; nenhum daemon rootful,
bridge/iptables do host ou configuração Desktop foi iniciado/alterado. Registro
iptables-save vazio e rota host inalterada. MinIO preexistente permanece saudável,
mesmo container e StartedAt, portas9000–9001 intactas.

Fonte Linux veio de `git archive HEAD` do checkout isolado, não root sujo. O clone
local direto falhou porque o gitdir do worktree usa path absoluto Windows; archive
resolveu sem editar o worktree. Archive inicial `f30172a` SHA256
`0f26c141203d3f0824c7fb6b058ca6c434b2f25e9a1cd05f697e8e40390e6422`.
uv0.12.12 Linux SHA256 oficial
`ab9b309d4586403f024e100abaceb396616e178a553e2500c36087d180f09509` verificado
antes de executar; Python3.14.7 e dependências locked. Snapshot do SHA final é
reconstruído após commit e seu build/up/probe registrado no checkpoint/journal.

Volumes nativos próprios separados0700 e configs0600 foraGit, com ownership mapeado
para UID10001 do backend/UID999 do PostgreSQL, sem chmod amplo nem socket/root mount.
Operador administrativo autorizado validou owners distintos no host; app real
UID10001 confirmou guard e uso dos volumes. Wrapper validate/build/up passaram;
DB/backend healthy e nginx real acessível somente por loopback. Bootstrap/migração/
runtime são contas sintéticas separadas; runtime sem superuser/CREATEDB/CREATEROLE.
Migração0001–0006 executou no banco novo. A primeira chamada do helper privado
omitiu `-c backend/alembic.ini` e falhou; corrigiu-se somente o harness e repetiu-se
up, sem esconder erro ou alterar artefato/readiness.

Probe real exercitou health/ready200, acesso privado401 sem sessão, login/session,
produto/upload PNG/consulta de pixels+digest, logout/revogação e cookie Secure/
HttpOnly. Transporte do ensaio é HTTP loopback com Cookie reenviado explicitamente
pelo cliente de teste: **não demonstra TLS real nem transporte de cookie Secure
por navegador HTTP**. Nenhum proxy externo/certificado é certificado por isso.

O ensaio encontrou bug concreto: mode0000 no bind privado recusava leitura de foto,
mas readiness ainda200 porque `checked_root` só verificava metadata. **Correção2**
adiciona acesso efetivo R/W/X ao guard existente; nenhuma permissão é relaxada.
Regressão unitária verifica chamada/erro503 sem path e recuperação; regressão PG
exige ready200→503/body genérico→200 e liveness200. O mock limita-se ao path de foto,
pois sua primeira versão global afetou também dotenv; assertion não foi reduzida.
Prova Linux após rebuild: UID10001, roots0700; próprio storage restringido0000
somente durante teste→ready503/foto503/health200; restore exato0700→ready200/mesmo
digest. Apenas DB próprio label-verificado foi parado→ready503/health200 e
reiniciado→ready200/consulta200. Finally recupera os próprios recursos.

Logs stdout **e stderr** reais do backend/nginx foram coletados privadamente e
conferidos por allowlist/ausência de sentinela em query/body/Cookie/Authorization/
Referer/request-id, email/senha/sessão sintéticos, DSN, rate key, segredo bootstrap
e paths. Resultado: **22 registros JSON backend/34 proxy, redaction PASS**; logs
brutos/valores privados não são publicados. Sem tracing/debug/access log padrão.

### Pipeline atual da correção2

Primeira suíte completa preservada: **2failed,308passed,49setup-errors,2warnings,
245.22s**. WSL encerrou a distro sem sessão foreground; PG próprio em container
ficou Exited0, causando49timeouts. [Microsoft](https://learn.microsoft.com/en-us/windows/wsl/systemd)
documenta que systemd não mantém a instância WSL viva. Uma sessão foreground própria
permanece aberta durante o ensaio, sem alterar settings/reiniciar WSL/Desktop.
O teste anti-libpq também recusou `inet_server_addr=172.17.0.2` do NAT Docker: sua
asserção loopback ficou **intacta**. Preparou-se PostgreSQL17.11 nativo oficial
[PGDG](https://www.postgresql.org/download/linux/ubuntu/), cluster novo privado
loopback15439, sem cluster padrão/serviço de sistema; serviço novo masked e
`create_main_cluster=false` antes de instalar o servidor. Antigo PG15437 não foi
reiniciado, alterado ou teve causa de ausência atribuída. O outro failure foi o
mock global descrito acima, corrigido por delimitação sem enfraquecer o contrato.

| Verificação atual no conteúdo da correção2 | Resultado |
| --- | --- |
| Ruff backend/operations + tooling raiz lido sem copiar |PASS;64arquivos formatados |
| mypy estrito |PASS;28fontes |
| pytest backend + tooling raiz, PostgreSQL nativo real |**359passed,2warnings,88.61s**, sem skip |
| subset operacional real após fullsuite |**9passed,2warnings,33.78s** |
| OPS-02 atual: age/PG dump/restore,22tabelas/2fotos |backup0.472s/restore0.588s;82136bytes cifrados/164bytes privados; sessão/link revogados, login/consulta/bytes/históricos conferidos |
| pip-audit de export locked/allgroups/hashes |PASS;zero vulnerabilidades conhecidas |
| ESLint/Prettier |PASS |
| Vitest |**44passed/5files,40.57s** |
| TypeScript/Vite production build |PASS;120módulos;Vite1.31s |
| npm audit |PASS;zero vulnerabilidades |
| Playwright/axe contra build de produção + API/PG reais |**100passed/2.1m**,4workers, sem retries/skips,320/390/768/1440 |

Foram regeneradas196capturas sintéticas; inspecionadas novamente as quatro capturas
nomeadas na seção visual acima:320 erro/retry sem corte de navegação,390 acordo/
histórico/aviso sem reserva,768 foco visível e formulário legível,1440 cards/navegação
sem overflow. Não houve mudança de UI nem baseline atualizada; não certifica todos
os dispositivos ou validação operacional humana.

Gitleaks, repetição no SHA final e cleanup são registrados após seus resultados no
checkpoint/journal; não inferir aprovação de operação pendente. Os2warnings Python são deprecações upstream já
descritas, não skip. Medidas RPO/RTO continuam sintéticas e pequenas; copy somente
diretório independente local, sem comprovar off-host real/30dias de operação.

### Verificação do commit de código2505615

Commit `2505615151a8259dff0c6a76079c73a0fb5fe059`, base4184cb1: snapshot final
SHA256 `dec64dc833cd5f5235b1f4eeae371323c288738be2cb5d314e5b052212ba3897`.
Wrapper validate/build/up e probe Linux do SHA exato passaram: UID10001/0700,
login/upload/bytes/logout, outages e recuperação,22backend/56proxy redaction.
Ruff64/mypy28,44Vitest12.74s, build120módulos305ms, lint/format/auditorias0 passaram.
Gitleaks staged/histórico29commits/range6commits sem leaks.

A primeira repetição fullpytest desse SHA terminou **1failed,358passed,2warnings,
99.69s**: `test_origin_limit_and_concurrent_failures_cannot_bypass` recebeu
`QueryCanceled` no advisory lock por statement timeout, enquanto o build Linux e
Vitest também estavam em execução. Nenhum timeout, proteção, teste de autenticação
ou assertion foi alterado. Após concluir essas cargas auxiliares, repetiu-se a
**suíte inteira sequencialmente:359passed,2warnings,86.76s**. A simultaneidade é
contexto observado, não certificação de causa única ou teste de capacidade.
Essa falha fica explícita; aprovação local não significa ausência de flakiness sob
carga nem certifica capacidade de produção. SHA documental final, repetição final
sequencial, imagens/resultados/cleanup constam no checkpoint/journal da entrega.
Nenhuma mudança adicional de código/rodada3 foi feita.

Recursos nativos do ensaio têm inventário privado por nomes/labels e são parados
somente após validação final. Pacotes oficiais/usuário/dados sintéticos privados e
imagens inativas podem permanecer para reprodução; não são recursos de produção.
Fixture Windows cuja remoção foi rejeitada continua retida, **sem nova tentativa ou
contorno**. Cleanup final informa separadamente processos/containers/ports parados
e artefatos retidos; não usar prune/down global nem atribuir remoção não executada.

## Entrega e gates restantes

Esta entrega prepara operação, sem lançamento/merge/deploy/main. PR/publicação,
revisão independente exata, reconciliação remota/Project Done e liberação condicional
do owner são responsabilidades do coordenador. Confirmar estado remoto/checks
existentes; ausência de CI/proteção não é check aprovado. A retomada autorizada
resolveu o bloqueio POSIX anterior sem relaxar guards; ainda exige fechamento dos
gates locais no SHA final e revisão independente exata antes de qualquer integração.
Runbook mantém os demais gates comerciais/operacionais/TLS/off-host antes de exposição.
