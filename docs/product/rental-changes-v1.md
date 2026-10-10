# Alterações da locação — rental-changes-v1

Implementa somente a revisão humana da issue13, updated_at2026-10-09T00:27:55Z,
SHA256 do body UTF-8 `90177b437c715aa82ba700a6e484bbd5865baff333b6499e4a3c38007d15126f`.
RN017/034/040/047/048/049 e decisões consolidadas são aplicadas pelos serviços,
independentemente da interface. Não aprova contratos, retirada/devolução ou IA.

| Ação | Efeito operacional | Efeito financeiro |
| --- | --- | --- |
| Prévia | Nenhuma gravação/alocação/hold | Mostra líquido, saldo projetado e excesso; não cria recebimento |
| Alterar confirmada | Nova revisão, motivo/autor/UTC; troca atômica do compromisso após validar capacidade e versões | Preserva sinal histórico; aplica apenas líquido ainda não devolvido, até o novo total |
| Solicitar cancelamento sem aprovação | Mantém estado/alocação; registra solicitação no histórico | Preserva financeiro |
| Cancelamento aprovado antes da saída | `cancelled`; libera somente a alocação própria, sob locks dos produtos | Não executa estorno, crédito, perdão ou transferência |
| Retomar cancelada/vencida | Mesma proposta e locação; nova revisão em `review`, sem alocação | Conferência explícita por origem/versão; zero recibos novos |
| Confirmar após retomada | Mesmo serviço #11, nova versão/checagem; conflito preserva revisão e dinheiro | Sinal de50% do acordo atual num único recebimento líquido suficiente |
| Correção/refund #12 | Preserva reserva/alocação e sinaliza pendência | Evento separado com histórico; valor devolvido reduz cobertura |
| Referência de concluída | Guard exige contexto completed de #14; nova proposta usa #10 e novo ID | Preços atuais/revisados, sem desconto ou pagamentos herdados |

R$400 com R$200 pagos, alterado para R$500 após confirmação: sinal histórico200,
saldo300. Reduzido para R$150: saldo0/excesso50 pendente de acordo humano. Não
exigir complemento de sinal por aumento de confirmada. A retomada é outro acordo:
aplica a regra do sinal vigente após conferência explícita. Recebimentos e refunds
continuam vinculados à proposta original, sem copiar dinheiro entre locações.
Cancelar não renegocia os termos financeiros: sinal histórico, saldo e aplicações
não se recalculam pela mudança de estado; snapshots históricos não são reescritos.
Somente a retomada explicitamente conferida aplica o novo acordo de50% na
conciliação e no respectivo snapshot/evento.

No detalhe de uma locação persistida, sinal e saldo são exibidos somente pelo
financeiro vigente retornado pelo servidor, não pelas parcelas genéricas da
proposta. Leituras pendentes/falhas e gravações desconhecidas não restauram uma
estimativa de50%. Orçamento sem locação mantém sua previsão; a prévia explícita
da retomada continua mostrando o novo acordo antes da conferência e gravação.

Serviços usam advisory de idempotência → orçamento → locação → conta/recebimentos
por UUID → kits → união de produtos anteriores/novos por UUID. A capacidade exclui
a alocação própria antiga e considera outras reservas simultâneas/manutenção.
Troca, revisão comercial, conciliação financeira, auditoria e resultado idempotente
compartilham a transação. Preview libera seus locks ao terminar, antes da decisão
humana. Não há janela de liberação entre excluir e inserir a alocação na transação.
O serviço comum #10 bloqueia revisão por atalho para qualquer proposta com locação.

Solicitação sem aprovação pode avançar a versão de auditoria, mas não muda estado,
itens, alocação ou dinheiro. Retomada de orçamento vencido sem cabeçalho de locação
tem alias técnico na mesma proposta, com versão de locação esperada0. O primeiro
cabeçalho nasce em review; nunca se fabrica confirmação para viabilizar a retomada.
Nova mudança comercial em review exige nova conciliação financeira explícita.

APIs autenticadas, Origin/CSRF, DTOs estritos e no-store seguem #21. Ator vem da
sessão. Replay é consultado antes das versões correntes; tentativa de estoque
recusada também preserva resultado409 para a mesma chave. Payload diferente retorna
409. Versão/estado/estoque409, regra422, vínculo404, dependência503, sessão401 e
Origin403 permanecem distintos. Dinheiro financeiro usa string decimal com duas
casas. Resultado desconhecido mantém rascunho/chave e bloqueia outra gravação até
reconciliação. Comparar conflito mostra versões correntes antes de refazer a prévia.

O contexto real de saída/conclusão continua pertencendo à #14. Esta migração só
habilita confirmed/cancelled/review. Guards unitários impedem cancelamento pós-saída,
remoção/substituição de produtos entregues ou encurtamento do período; preço/motivo
e extensão usam a mesma validação de capacidade. Complementos exigem nova locação.
Integração PostgreSQL real de out/completed deve ser exercitada adicionalmente na
#14. `signature_commercial_version` é a revisão que #15 terá de comparar; não é
assinatura nem emissão de contrato.
