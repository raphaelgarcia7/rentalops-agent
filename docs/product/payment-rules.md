# Pagamentos manuais — payments-v1

Escopo da issue #12, revisão aprovada `2026-10-09T00:27:53Z`, body UTF-8 SHA-256
`9b04436fa47de9b41421c7dcd6a00a89f382958281f108045fe2369fbcb20fda`.
Estas regras não implementam reserva, saída, banco, cobrança ou transferência.

## Receber, conferir e quitar são operações distintas

Uma conta financeira pertence ao UUID do orçamento, não a uma revisão histórica
isolada. A revisão comercial vigente da #10 fornece total, sinal e saldo previstos.
Dinheiro usa Decimal/Numeric, sem float: API exige string decimal de duas casas,
positiva em recebimentos/devoluções e até o MAX_MONEY existente. Sinal é metade do
total final arredondada para cima ao centavo; saldo é a diferença exata.

A equipe registra somente recebimento já ocorrido: valor, Pix/dinheiro/cartão,
data ISO não futura em America/Sao_Paulo, observação opcional até 2000 caracteres.
Autoria, sessão e instante UTC vêm do servidor. Não coletar dados de cartão.
Comprovante é opcional. Receber ou anexar nunca aplica valores automaticamente.

Conciliação é comando explícito com motivo de 1–1000 caracteres e confirmação na
tela. Seu payload contém a distribuição **completa substitutiva** por receipt_id:
origem omitida deixa de estar aplicada, e a nova revisão não incrementa a anterior.
Cada origem aparece uma única vez. Valores aplicados são não negativos, limitados
ao líquido da origem, ao sinal/saldo e ao total comercial vigente.

Somente um recebimento líquido pode cobrir o sinal inteiro. Dois recebimentos de
100 não quitam sinal de 200, mas podem ser aplicados ao saldo sem quitar o sinal.
Um recebimento de 250 em total 400 fica pendente até a equipe aplicar 200 ao sinal
e 50 ao saldo; então restam 150. Integral único 400 também exige conciliação 200+200.
Saldo admite várias origens/meios. Excedente permanece identificado para decisão
humana, sem crédito automático a outro orçamento.

Resumo separa total/sinal/saldo previstos, recebido, devolvido, líquido, aplicado,
restante, pendente e excedente. Sinal validado/financeiro quitado não são estado de
reserva. Não há booleano operacional fictício nem escrita em estoque nesta entrega.

## Correções, devoluções e versões

Correção cria revisão imutável dos dados do recebimento, com motivo e autoria;
preserva original e antes/depois. Não representa dinheiro devolvido. Não pode
reduzir o recebido abaixo do valor já devolvido registrado.

Devolução registra dinheiro **já efetivamente devolvido**, com valor, data, forma,
motivo e origem; seu evento separado não executa transferência. Soma devolvida
não supera o líquido disponível da origem. Correção/devolução que torna a
distribuição daquela origem superior ao líquido retira essa origem da aplicação
efetiva e exige nova conciliação. Antes/depois e distribuição anterior permanecem
no histórico; não há realocação automática nem saldo negativo.

Nova revisão comercial exige nova conferência explícita. A distribuição histórica
permanece preservada, mas não valida a nova revisão; o resumo vigente mostra a
pendência e os valores disponíveis não conferidos. Comandos stale retornam 409
sem mutação. Mesmo ao consultar oferta histórica, a seção financeira identifica a
versão **comercial vigente**, sem reescrever o snapshot exibido da oferta.

Todas as mutações exigem request_id UUID e expected_financial_version /
expected_quotation_version. Replay por ator/operação/chave com payload canônico
igual devolve a resposta original; conteúdo diferente retorna 409. Upload inclui
digest no payload canônico, não nome de arquivo. Ordem de locks PostgreSQL:
idempotência → quotation → conta → recebimentos em UUID crescente. Dados,
histórico, aplicações normalizadas e resposta idempotente fazem um único commit.
Resultado desconhecido na tela bloqueia edição e conserva a mesma chave/corpo
para repetição, inclusive em falha HTTP 5xx. Conflito conserva o formulário e exige
nova prévia explícita com versões atuais, não uma repetição automática modificada.

## Comprovantes privados

Aceitar PDF, JPEG ou PNG original, máximo **10.000.000 bytes**, com validação de
conteúdo/MIME. Imagens precisam verificar/decodificar e ter no máximo 25 milhões
de pixels. PDF passa parser estrutural estrito, no máximo 100 páginas, sem
criptografia, JavaScript, ações executáveis ou arquivos embutidos. Isso não é
antivírus nem certificação de arquivo seguro.

O STORAGE_ROOT privado absoluto existente é reutilizado com namespace de chaves
geradas `proof-<UUID>.<ext>`; não é pasta de assets públicos. Guard de permissões,
ancestrais e links/junctions permanece obrigatório. Escrita exclusiva imutável,
size/SHA-256 e vínculo no PostgreSQL; download autenticado valida integridade e
vínculo da conta, usa attachment/no-store/nosniff e não expõe path. Falha de storage
não impede registrar recebimento sem comprovante. Falha de commit compensa apenas
bytes novos identificados da própria tentativa; nenhum histórico é removido.
Se o ACK de commit se perde, uma consulta nova sob lock de quotation verifica
metadados persistidos antes de compensar. Proof já commitado permanece acessível;
se não for possível verificar o resultado, reter o possível órfão daquela tentativa
é mais seguro do que apagar bytes que podem pertencer ao histórico. Replay da mesma
chave resolve o resultado persistido, sem nova escrita nem limpeza ampla.

Sem DELETE ou expiração/purge automático. Validar política de retenção/eliminação
de produção e backups antes de ativá-la; nenhuma conformidade jurídica é atestada.
O backup cifrado operacional inclui proofs referenciados e verifica digest/size;
restore repõe originais e dados no destino privado novo. Evidência real cobre o
formato/schema corrente, não compatibilidade com backups de heads anteriores.

## Fronteiras futuras obrigatórias

- #11: consultar fatos financeiros persistidos e validar sinal vigente junto da
  confirmação explícita com checagem fresca de estoque. Nunca permitir exceção de
  sinal insuficiente. Receber/quitar isoladamente não confirma nem aloca.
- #13: receber contexto operacional persistido, preservar sinal já validado após
  confirmação e tratar diferenças no saldo; validar novamente estoque para itens
  e datas. Redução/excedente e alterações reais são responsabilidade daquela task.
- #14: preservar saída real, dívida e autoria; exceção aprovada de retirada com
  saldo pendente não dispensa sinal. Correção financeira não cancela/libera
  estoque, desfaz saída ou presume devolução.

Essas integrações não estão entregues: não há contexto operacional persistido na
base atual. Nenhum estado de confirmação informado pelo navegador é autoridade.
