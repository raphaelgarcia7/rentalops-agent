# PostgreSQL local para ROP-007

PostgreSQL é a persistência do produto. Não se confunde com o journal SQLite da coordenação. Esta entrega não configura hospedagem, backup ou produção.

Use PostgreSQL 17, banco de desenvolvimento e banco de testes separados. A conta de testes precisa criar schemas apenas no banco dedicado. URLs de testes aceitam somente loopback e um nome como `rentalops_test`; query options são recusadas para impedir redirecionamento por libpq. A fixture fixa também `hostaddr`, evitando que `PGHOSTADDR`/`PGSERVICE` redirecionem a conexão. Ela valida o alvo antes de conectar e valida o nome de seu schema antes de limpar. A aplicação não recebe uma configuração de teste automaticamente.

O isolamento usa schemas exclusivos, em vez de recriar o banco compartilhado. Migrações e tabelas permanecem no schema de cada teste, definido por `search_path`; `public` e outros schemas são preservados. Um teste adicional preserva um sentinel sintético em outro namespace. Finalizadores fecham engines antes de remover somente o namespace criado. Interrupção abrupta pode deixar um schema de teste: investigar sua propriedade antes de qualquer remoção; não varrer nomes de schema ou apagar o banco como limpeza.

## Instância descartável em Windows

Se não houver credencial autorizada para o serviço instalado, as ferramentas oficiais permitem um novo cluster em diretório vazio escolhido explicitamente. Nunca altere `pg_hba.conf` do serviço existente ou tente senhas. Confira previamente que a porta escolhida está disponível e não pertence à faixa reservada do Windows.

Exemplo adaptável (diretório e porta sintéticos; comandos executados pelo proprietário local):

```powershell
New-Item -ItemType Directory -Path C:/Temp/rentalops-test-instance
& 'C:/Program Files/PostgreSQL/17/bin/initdb.exe' -D C:/Temp/rentalops-test-instance/data -U rentalops_test --auth-local=trust --auth-host=trust --encoding=UTF8 --locale=C
& 'C:/Program Files/PostgreSQL/17/bin/pg_ctl.exe' -D C:/Temp/rentalops-test-instance/data -l C:/Temp/rentalops-test-instance/postgres.log -o '-h 127.0.0.1 -p 15437 -c timezone=UTC' -w start
& 'C:/Program Files/PostgreSQL/17/bin/createdb.exe' -h 127.0.0.1 -p 15437 -U rentalops_test rentalops_test
$env:TEST_DATABASE_URL='postgresql+psycopg://rentalops_test@127.0.0.1:15437/rentalops_test'
uv sync --project backend --locked
uv run --project backend pytest backend/tests
& 'C:/Program Files/PostgreSQL/17/bin/pg_ctl.exe' -D C:/Temp/rentalops-test-instance/data -m fast -w stop
```

`trust` é restrito a este cluster descartável em loopback, sem dados ou credenciais reais. Qualquer processo local pode acessar esse banco, cujo usuário é superuser de teste; não reutilizar em desenvolvimento com dados reais nem produção e não expor a rede. O usuário Windows controla os arquivos. Esta configuração não fortalece nem enfraquece a autenticação de outra instância. Parar não apaga arquivos; qualquer descarte posterior precisa validar exatamente o diretório autorizado.

Para revisar ROP-007 no mesmo computador, reutilize a instância e os caminhos registrados nas [evidências](../../docs/engineering/rop-007-evidence.md). A suíte não exige migrar o schema `public` do banco de testes. Os comandos de migração do README usam `DATABASE_URL`; não defina essa variável com o mesmo alvo de `TEST_DATABASE_URL` durante a suíte.

## Limites

Identidades persistidas não equivalem a acesso autenticado. ROP-021 implementará e-mail/senha e provisionamento; Google foi adiado para ROP-022 pelo responsável. Não há usuários semeados, login, sessão de autenticação ou roles. E-mails sintéticos usam `example.invalid`; dados reais de clientes, contratos ou segredos não devem aparecer em testes ou traces. A migração normaliza e-mail também para SQL direto e mantém `updated_at` no PostgreSQL. A validação completa de endereço e os fluxos de autenticação ficam para ROP-021.

O pipeline desta entrega é local. Nenhum workflow GitHub ou proteção de branch foi publicado por ROP-007; ROP-006 continua responsável por isso. Ausência de CI não é check aprovado. Revisão independente e merge permanecem gates do coordenador.
