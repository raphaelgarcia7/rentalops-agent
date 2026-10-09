# Preparação operacional — operations-prep-v1

Este runbook prepara um host Linux dedicado com Docker Compose, PostgreSQL e
frontend estático/nginx. Não houve contratação, provisionamento, exposição pública
ou implantação. Os comandos abaixo são procedimentos para um operador autorizado;
nenhum comando de produção deve ser executado pelo harness sintético.

RPO **alvo** 24h; RTO **alvo** 4h. Backup diário cifrado, cópia fora do host e 30 dias
de pontos recuperáveis são requisitos antes de produção. Não há purge automático.
O ensaio pequeno mede somente seu próprio volume/duração, sem certificar esses
objetivos para a operação real. Evidências e limitações: [ROP-004](../../docs/engineering/rop-004-evidence.md).

## Configuração e gates de exposição

Responsável operacional: a pessoa designada pelo dono da locadora antes de ativar
a operação. Registrar contato, substituto, horários de verificação e destino de
alerta no inventário privado de operação; nenhum contato pessoal entra neste Git.

1. Escolher fornecedor/host, acesso administrativo individual com MFA quando
   disponível, domínio, certificados HTTPS e renovação/alerta. Manter firewall e
   acesso restrito à equipe; nunca desligar proteções existentes. O Compose publica
   somente `127.0.0.1:8080`; banco/API não têm portas externas. O TLS externo é gate
   separado: testar certificado, cadeia, renovação, redirects e cookies Secure no
   endereço real antes de exposição. Este nginx interno não certifica outro proxy.
2. Diretórios absolutos separados, fora do checkout/Git e de qualquer pasta pública:
   `/srv/rentalops/database`, `/srv/rentalops/photos`, `/srv/rentalops/operations`,
   `/srv/rentalops/backups`, `/srv/rentalops/scratch`; segredos em `/etc/rentalops`.
   Criar também os roots `/srv/rentalops` e `/etc/rentalops` com mode0700. Cada
   diretório de volume e seu root privado devem ter mode0700 e dono correto:
   fotos/operations UID10001 do backend; banco
   usuário do PostgreSQL da imagem. Arquivos privados mode0600. Rejeitamos links e
   junctions em qualquer ancestral, caminhos relativos e permissão pública. No
   Windows o ensaio verifica ACLs Everyone/Anonymous/AuthenticatedUsers/Users; o
   runner Linux verifica ausência de permissões de grupo/outros. Não usar volume
   de rede sem confirmar suporte real a locks e publicação atômica.
3. Criar arquivo privado `compose.env` com placeholders adaptados, sem imprimir
   `docker compose config` completo (pode expandir variáveis privadas):

   ```dotenv
   DATABASE_VOLUME=/srv/rentalops/database
   STORAGE_VOLUME=/srv/rentalops/photos
   OPERATIONS_VOLUME=/srv/rentalops/operations
   BACKEND_ENV_FILE=/etc/rentalops/backend.env
   POSTGRES_PASSWORD_FILE=/etc/rentalops/postgres-password
   LOCAL_PORT=8080
   ```

4. `backend.env` privado contém `DATABASE_URL` da conta de runtime, `AUTH_ORIGIN`
   exata HTTPS sem barra final e `AUTH_RATE_KEY` aleatória com pelo menos32bytes.
   Compose fixa APP_ENV=production e caminhos internos dos dois volumes. Não incluir
   URL/segredo em argv, captura, Git, monitoramento, logs ou shell com tracing.
   PostgreSQL usa senha por secret file. `rentalops_bootstrap` é somente bootstrap;
   criar conta de runtime separada sem superuser/CREATEDB/CREATEROLE, com privilégios
   necessários às tabelas/sequências e execução dos triggers. Conta de migração
   separada fica em terminal privado; usar `psql \password` para definir senha sem
   registrá-la. Nunca executar runtime como bootstrap em produção.
5. Verificar Docker/Compose, espaço, limites, versão do banco e ferramentas `age`,
   `pg_dump`/`pg_restore`17 (cliente não pode ser mais antigo que o servidor), uv e
   dependências locked. Os índices de imagens estão fixados por digest; pacotes APT
   de sistema ainda recebem patches do repositório Debian/PGDG, portanto não é uma
   certificação de build bit a bit. [PGDG oficial](https://www.postgresql.org/download/linux/debian/).
   `.dockerignore` exclui secrets, Git, caches e evidências. Rodar:

   ```sh
   uv run --project backend python -m infra.operations.runtime validate --env-file /etc/rentalops/compose.env --project rentalops-preparation
   uv run --project backend python -m infra.operations.runtime build --env-file /etc/rentalops/compose.env --project rentalops-preparation
   uv run --project backend python -m infra.operations.runtime up --env-file /etc/rentalops/compose.env --project rentalops-preparation
   ```

   **A entrada suportada para build/start é `infra.operations.runtime`, não o
   Compose direto.** O wrapper verifica valores brutos e os bind sources/secrets/
   env_file resolvidos pelo Compose no host, antes de qualquer mutação. Rejeita
   relativos, Git, links/junctions, roots públicos/ACL pública, volumes sobrepostos,
   secret/config dentro de dados e divergência dos mounts esperados. Revalida antes
   de build/up; não cria diretórios nem muda permissões automaticamente. Os três
   binds usam `create_host_path: false`. `config --quiet` sozinho apenas valida
   sintaxe e **não** comprova privacidade. O wrapper captura/descarta diagnostics
   potencialmente privados e emite somente JSON/status seguro. Operador autorizado
   continua responsável pelo controle de acesso ao Docker/host; Compose direto
   contorna o preflight e não é o procedimento validado. Não executar o wrapper
   como root para ocultar falhas de acesso, nem alterar proteções existentes.

   Repetir build/start/health no host de teste Linux antes de ativar; falha impede
   exposição. Nenhum deploy faz parte desta entrega. Manter ledger privado das
   imagens efetivamente construídas, versões e revisão do código.

## Contas, sessão e logs

Contas individuais autorizadas seguem #21: CLI create-user/issue-access-link,
link privado entregue diretamente, uso único30min; sem senha padrão/SMTP/cadastro
público/roles de produto. Recuperação administrativa revoga sessões; deactivate-user
revoga todas as sessões e links. Não capturar a saída do link/token. Remover acesso
administrativo ao host quando uma pessoa sair e rotacionar segredos afetados.

`/health` informa apenas liveness. `/ready` (alias legado `/health/ready`) testa
banco, migration head e storage, respondendo ready ou unavailable503 sem detalhes.
Uma instância saudável exige readiness; liveness200 não comprova capacidade.
Storage inválido/missing/corrompido recusa leitura/escrita com erro controlado.

O comando do container desativa access log padrão e traces de exceções. Telemetria
JSON allowlist contém request_id gerado no servidor, operação da rota, duração,
status e categoria. Nenhum body/query, URL privada, header, cookie, token, endereço
de cliente, DSN ou path é registrado. Auditoria de negócio é distinta e persistida.
nginx registra método/status/duração/request_id sem URI/Referer/IP/headers; error log
é descartado porque mensagens nativas podem conter URLs. Falhas de configuração
impedem start (exit não zero); verificar exit/status no supervisor. Não habilitar
debug, SQL echo ou tracing de payload para investigar incidentes. Revalidar logs
do proxy externo contratado com sentinelas sintéticas antes de exposição.

## Backup e cópia independente

O runner precisa acessar os mesmos volumes de fotos e operations da API, e o mesmo
PostgreSQL. Em container os paths são `/private/photos` e `/private/operations`;
no host são os bind sources. **Nunca apontar o backup para outra operations-root**:
isso não coordena escritores. Migrações/CLI administrativas deste app passam pela
barreira; SQL externo/manual deve ser suspenso durante backup. O operador controla
o acesso de escrita ao banco/storage e evita outros escritores não coordenados.

`age` é a ferramenta de cifra consolidada: [documentação oficial](https://github.com/FiloSottile/age).
Gerar identidade privada fora do Git, guardá-la em local separado/offline com acesso
restrito e teste de recuperação. O host precisa somente do recipient público; a
chave de decriptação não deve acompanhar os pacotes no destino externo.

```sh
umask 077
age-keygen -o /etc/rentalops/backup-identity.txt
age-keygen -y /etc/rentalops/backup-identity.txt > /etc/rentalops/backup-recipient.txt
uv run --project backend python -m infra.operations.backup backup --db-url-env DATABASE_URL --storage-root /srv/rentalops/photos --operations-root /srv/rentalops/operations --output-dir /srv/rentalops/backups --recipient-file /etc/rentalops/backup-recipient.txt
```

Carregar `DATABASE_URL` e `OPERATIONS_ROOT` de arquivo/env privado sem imprimir.
`OPERATIONS_ROOT` deve ser o mesmo path passado em `--operations-root` no runner;
divergência é recusada antes do dump. Esse bind deve ser o mesmo volume da API.
Comando emite somente
JSON seguro e nome do ponto, nunca DSN/chave. A barreira fecha entrada de novas
operações, drena operações/transações/uploads existentes até60s e mantém bloqueio
durante dump+arquivos. Escrita iniciada durante manutenção recebe503 para retry;
operação em andamento mantém sua proteção até completar, inclusive bytes/metadados
do upload. Timeout/erro impede publicação; arquivos temporários ficam em scratch
privado e são removidos, sem ponto recuperável incompleto.

Backup usa pg_dump custom, todos os arquivos históricos (inclusive detached) e
manifest interno cifrado com versão, contagem/digest das tabelas, metadados das
fotos e digest/tamanho de cada membro. O receipt externo contém apenas hora, digest
do ciphertext, tamanho e duração; não contém PII. Não substituir a verificação
criptográfica por checksum do receipt. Plaintext temporário exige disco privado,
espaço e política de criptografia do host; remoção não certifica apagamento físico.

```sh
uv run --project backend python -m infra.operations.backup verify --manifest /srv/rentalops/backups/point-PLACEHOLDER/manifest.json --identity-file /etc/rentalops/backup-identity.txt --scratch-root /srv/rentalops/scratch
uv run --project backend python -m infra.operations.backup copy --manifest /srv/rentalops/backups/point-PLACEHOLDER/manifest.json --copy-dir /srv/rentalops/offhost-mounted-destination
uv run --project backend python -m infra.operations.backup status --output-dir /srv/rentalops/backups
```

`verify` decripta/autentica tudo e rejeita duplicatas, traversal, links, membros
faltantes/extras, schema incompatível, tamanho/digest inválido e fotos sem bytes.
`copy` publica somente ciphertext+receipt de forma atômica em diretório independente,
sem sobrescrever ponto existente; transporte/autenticação/cópia física fora do host
depende do destino contratado. O ensaio é diretório local independente, explicitamente
**não** backup externo real. Depois da cópia, executar verify no lado de recuperação
com identidade privada autorizada e registrar confirmação segura.

`status`: exit0 recente≤24h com digest íntegro; exit2 ausente/atrasado; exit1 erro ou
corrupção. Retorno JSON mostra idade/quantidade; receipt é diagnóstico de transporte,
não prova criptográfica da idade. Agendar diariamente usando os templates service/timer
somente após adaptar runner e implementar alerta de falha/idade para o responsável.
`OnFailure` não é integração já existente; a unidade de alerta e destino são gate.
Verificar exit do backup/verify/copy e consultar status em monitor externo ao host.
Não aceitar apenas log de "timer disparado" como sucesso. Alertar falta de espaço,
indisponibilidade, timeout, verify/copy falho e último sucesso>24h. Manter pelo menos
30 dias de pontos completos verificados; nenhum comando desta entrega apaga backups.
Definir eliminação legal/operacional e testar recuperação periódica antes de produção.

## Restore e validação antes de abrir usuários

1. Declarar incidente, bloquear acesso de usuários e registrar hora segura/início
   da indisponibilidade. Confirmar o ponto escolhido e a idade para RPO observado.
2. Em PostgreSQL de recuperação isolado em loopback, escolher banco novo
   `rentalops_restore_test_<32hex>` e diretório privado novo vazio. Não apontar a CLI
   para produção: exige nome descartável, host local e `--discardable-target`;
   recusa query redirections, qualquer objeto/schema não padrão e storage não vazio.
   Restore cria somente esse banco novo se ausente; não faz DROP/overwrite. Erro
   deixa destino fechado e descartável para investigação, nunca announce sucesso.
3. Carregar `RESTORE_DATABASE_URL` privadamente e executar:

   ```sh
   uv run --project backend python -m infra.operations.backup restore --manifest /srv/recovery/point-PLACEHOLDER/manifest.json --identity-file /etc/recovery/backup-identity.txt --scratch-root /srv/recovery/scratch --target-db-url-env RESTORE_DATABASE_URL --target-storage-root /srv/recovery/photos --discardable-target
   ```

4. Antes de tocar destino, pacote inteiro deve passar verify. Pg_restore usa uma
   transação e exit-on-error. Comparar contagens/digests de todas22tabelas, FK/constraints,
   schema e bytes/digests de fotos, inclusive históricos. Revogar todas sessões e
   links de senha restaurados, mantendo registros de autoria/histórico. Testar novo
   login por senha, consulta de cliente/kit/orçamento/revisões e leitura de fotos.
   Sessão/token antigo deve falhar; não usá-lo como atalho de validação.
5. Registrar início/fim, bytes e duração do ensaio, RPO=idade do snapshot escolhido
   e RTO=tempo total real até validação/acesso reaberto (inclui provisão/cópia humana).
   Duração isolada da CLI não é RTO real. Se alvo não for atendido, manter gate fechado,
   investigar e repetir com volume representativo. Não extrapolar teste pequeno.
6. A promoção do banco de recuperação para runtime é operação humana separada,
   após validação/gates de segurança/TLS. Esta CLI não faz cutover nem deploy.
   Limpar apenas recursos sintéticos nomeados criados pelo ensaio, após conferir os
   identificadores; nunca apagar source, banco existente ou volume de produção.

## Migração e incidentes

Ensaiar migração do ponto recuperado com a mesma revisão do código; pacote de outra
migration head é recusado. Para código novo: restaurar com versão antiga compatível,
medir migration upgrade no destino de teste, validar dados e ensaiar downgrade apenas
quando a migration declara rollback compatível. Schema incompatível mantém `/ready`503.
Não executar downgrade destrutivo em produção; rollback seguro pode exigir restauração
em outro destino e cutover humano. Backup consistente antes da mudança é obrigatório.

Banco indisponível: readiness503/liveness200, rejeitar writes e reconciliar operações
com resultado desconhecido pela chave existente antes de repetir; verificar disco,
processo e conectividade em terminal privado. Storage indisponível: não usar pasta
pública/substituta vazia; bloquear leitura/upload, conferir mount/ACL/digests e manter
fotos históricas. Corrupção/missingasset exige restore de ponto consistente, não apagar
metadata para esconder falha. Falha de backup: exit/idade alertam, último ponto válido
é preservado; corrigir causa e verificar novo ponto+cópia antes de encerrar incidente.

Segredo comprometido: restringir acesso, rotacionar credencial afetada/secret files,
revogar contas/sessões/links conforme #21, revisar eventos sem payload e testar novo
acesso. Perda da identidade age impede decrypt: recorrer à cópia offline validada;
não há senha mestra/fallback nem compra de serviço automática. Guardar novos pontos
com novo recipient quando necessário, mantendo recuperação dos antigos sob política
aprovada. Nenhum teste autoriza exposição de cliente/documento/contrato/assinatura.
