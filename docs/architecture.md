# Princípios de arquitetura

Este documento registra limites e princípios que já orientam o RentalOps. Decisões técnicas ainda em aberto devem ser documentadas como registros de decisão em [`decisions/`](decisions/).

## Limites entre as partes

```text
Frontend ──> API ──> serviços de aplicação ──> persistência de negócio
                         ▲
                         │
                  ferramentas do agente
```

O frontend comunica-se com o backend por contratos HTTP explícitos. A interface tradicional e o agente podem iniciar operações, mas as regras de negócio devem residir nos mesmos serviços de aplicação.

## Responsabilidades do agente

O modelo pode interpretar linguagem natural, extrair dados estruturados, identificar ambiguidades, pedir informações que faltam, escolher ferramentas permitidas e explicar resultados. Código determinístico e persistência devem decidir disponibilidade, preços, quantidades e estado das reservas.

O estado da conversa serve à continuidade do atendimento. Ele não é o registro definitivo de itens, estoque, clientes, valores ou reservas.

## Evolução do grafo

Quando o primeiro fluxo de locação exigir um agente, começar com um grafo pequeno de modelo e ferramentas é a opção de referência. Nós, ramificações, subgrafos, aprovação humana e mecanismos adicionais entram quando um requisito observável justificar a complexidade. A forma concreta do estado, o checkpoint e a política de retomada devem ser decididos e registrados antes da implementação.

## Decisões ainda abertas

- Banco de dados e estratégia de migrações.
- Contratos das primeiras operações de catálogo e reserva.
- Modelo, limites de custo e comportamento quando o provedor estiver indisponível.
- Formato do estado do grafo e contratos de ferramentas.
- Retomada de conversa, armazenamento de checkpoint, expiração e resumo de conversas longas.
- Confirmação humana para ações que alteram dados de negócio.
- Retentativas, idempotência, avaliação do agente, rastreamento e métricas.
- Alvo de implantação e estratégia de provisionamento.

Essas escolhas não precisam ser resolvidas todas de uma vez. Cada decisão deve acompanhar o fluxo vertical que a torna necessária.
