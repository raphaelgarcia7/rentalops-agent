# Confirmação de reserva — reservations-v1

Implementação da revisão humana aprovada da ROP-011, atualizada no GitHub em
2026-10-09T00:27:50Z. Este documento descreve somente seu escopo. As regras
RN-002/004/006/007/017/025/026/027/034/037/038/040/041/069 continuam aplicáveis.

Registrar dinheiro, conciliar sua distribuição e confirmar a reserva são três
ações explícitas distintas. Somente a confirmação da proposta vigente, ainda
válida e com retirada não passada, aloca estoque. O sinal completo deve vir de
um único recebimento líquido, conciliado nessa versão. Pagamento integral e
comprovante não dispensam nenhuma dessas verificações.

A consulta e cada tentativa de confirmação sincronizam o painel financeiro e seu
histórico por novas leituras do servidor. Durante loading/erro, o painel não afirma
recebimento zero ou sinal inválido a partir de uma consulta antiga. A reconsulta
explícita é somente leitura; preserva formulários e comandos de resultado desconhecido
com a mesma chave e versões originais. O snapshot financeiro da confirmação continua
histórico e imutável; o painel atual identifica sua própria versão, inclusive após
correções posteriores, sem confundir estado financeiro com confirmação de estoque.

A demanda soma os produtos dos kits, inclusive personalizados, multiplicados
pela quantidade de cada linha, e os avulsos. Kits mantêm preço próprio. A
capacidade considera estoque físico menos manutenção e o pico de compromissos
simultâneos em cada trecho do intervalo fechado retirada..devolução. O dia da
devolução permanece ocupado; o dia seguinte fica disponível também em fins de
semana e feriados. Datas comerciais usam America/Sao_Paulo; auditoria usa UTC.

Não há retenção antes de confirmar. A consulta é informativa e a confirmação
recalcula a capacidade sob locks de produto. Falta de capacidade preserva os
recebimentos, registra pendência de estoque e não grava alocação parcial. Uma
nova tentativa exige nova chave; repetir a mesma chave retorna o resultado
original, inclusive um conflito. Alterar o payload com a mesma chave é conflito.
O histórico do conflito fica preservado; uma confirmação posterior bem-sucedida
é o evento que resolve aquela tentativa de confirmação, sem apagar seu registro.

A locação confirmada é única por orçamento e preserva snapshots comercial e
financeiro, ator e instante da checagem. Revisão comercial comum é bloqueada após
confirmar; o fluxo de alterações pertence à ROP-013. Catálogo, preço, fotos e
inativação posteriores não reescrevem snapshots. Baixa/manutenção que comprometa
uma locação gera pendência identificável de estoque, sem cancelamento automático.
Correção ou devolução de dinheiro posterior gera pendência financeira separada,
mantendo locação e alocação. Essas pendências permanecem para tratamento humano;
não há endpoint que finja resolução, cancelamento ou devolução física nesta fase.

Retirada, devolução real/parcial, atraso e liberação operacional pertencem à
ROP-014 (R11-RET/R11-LATE). A presente entrega não certifica esses efeitos futuros.
