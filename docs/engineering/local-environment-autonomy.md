# Autonomia para preparação do ambiente local

Autorização direta do responsável no Harness em 2026-10-09: preparar WSL/Ubuntu e resolver bloqueios técnicos locais para o trabalho fluir, registrando a autorização na rotina e no fluxo de trabalho. Este registro complementa os gates de entrega, não aprova planos futuros.

## Aplicação no pipeline

Antes de implementar ou validar uma tarefa aprovada, o coordenador/executor inspeciona dependências e ambiente. Pode preparar dependências gratuitas de fontes oficiais, pastas nativas Linux privadas fora do Git, integração WSL/Docker suportada e serviços/fixtures sintéticos isolados, sem repetir pedidos de autorização para estes passos locais seguros. Usar a mesma entrega e owner ao retomar; preservar arquivos, dados, configurações e serviços existentes.

Registrar motivo, recursos criados, alterações, verificação e retomada no journal. Esgotar alternativas suportadas nesse escopo antes de declarar bloqueio. Não usar a distribuição interna docker-desktop como ambiente de desenvolvimento nem contornar seus mecanismos de acesso.

## Limites preservados

- Nenhum bypass de políticas, bloqueios de ferramentas, permissões, testes, ACs ou proteções.
- Nenhuma exclusão/sobrescrita de dados existentes, aceitação de termos pelo usuário, reinicialização automática da máquina, compra/crédito/API paga ou criação de credenciais reais.
- Nenhuma decisão comercial/arquitetural nova, aprovação de versões futuras, troca de modelos, execução simultânea, publicação em main ou deploy.
- Ready da versão exata, predecessoras Done e remotamente integradas, lock único, testes, revisão independente do SHA/base atuais e gates remotos continuam obrigatórios. Teste não executado nunca equivale a teste aprovado.

Pedir intervenção apenas diante de limite real de acesso/autoridade, decisão humana, gasto, efeito destrutivo/material fora desse escopo ou interação obrigatoriamente humana. Explicar o impedimento concreto e preservar o progresso. A rotina horária existente mantém a cadência e o silêncio quando não há mudança significativa.

## Aplicação inicial: ROP-004

Retomar operations-prep-v1 na execução existente. Docker Linux já funciona; NTFS com binds apresentados como 0777 não satisfaz os guards privados. Ubuntu/WSL com filesystem nativo foi autorizado para concluir o ensaio obrigatório, sem enfraquecer guards nem substituir evidência Linux por Windows. Não liberar o owner nem antecipar outra entrega enquanto os gates desta permanecem pendentes.
