# ROP-003 — Evidências do espaço de trabalho responsivo

Implementação local de 2026-10-02, na branch `codex/3-responsive-workspace`, a partir de `origin/develop` (`9abc6d4039eb4d5525300d71d9c9e5597f7ec288`). Plano e três critérios aprovados pelo responsável nesta data. Este registro não confirma publicação, revisão independente ou merge; o coordenador deve associar os resultados ao SHA final.

## Escopo entregue

| Critério | Evidência |
| --- | --- |
| Navegação responsiva para catálogo, clientes e locações, com componentes/tokens reutilizáveis | `AppShell`, `ModuleCard`, `StatePanel`, `Icon`, páginas e metadados compartilhados; CSS com tokens e navegação disponível em 320, 390, 768 e 1440 px |
| Teclado, foco, contraste, estados aplicáveis e movimento reduzido | Link para pular ao conteúdo; foco no conteúdo após mudança de rota; links com área mínima de 44 px; testes de teclado e axe nas cinco páginas e quatro larguras; animação decorativa desativada com movimento reduzido; recuperação de endereço inexistente |
| Tela inicial funcional integrada às rotas, sem apresentar capacidades futuras como prontas | `/`, `/catalogo`, `/clientes`, `/locacoes` e fallback; links ativos, acesso direto, atualização, voltar/avançar e retorno à visão geral; módulos indicados como **Em construção** e assistente como **Planejado** |

Não há dados fictícios de negócio, métricas, CRUD, consultas à API, autenticação, persistência ou agente funcional. Como estas páginas são estáticas, não simulam carregamento nem falhas de operações ainda inexistentes. Os módulos descrevem seu estado atual e o próximo escopo; não representam um cadastro vazio consultado em um servidor.

## Verificação local

Executado em Windows com Node 24.18.0 e npm 11.16.0, em `frontend/`:

| Comando | Resultado final |
| --- | --- |
| `npm run lint` | Aprovado, saída sem erros |
| `npm run format:check` | Todos os arquivos correspondentes formatados |
| `npm test` | 1 arquivo, **9 testes aprovados**, 10,00 s |
| `npm run build` | TypeScript e build de produção aprovados, 101 módulos |
| `npm audit --audit-level=high` | **0 vulnerabilidades** |
| `npx playwright install chromium` | Chromium disponível, comando concluído |
| `npm run test:e2e` | **40 testes aprovados**, 36,3 s, contra o build de produção |
| `git diff --check` | Sem erros de whitespace |

O servidor de testes usa a porta 4173 e `reuseExistingServer: false`, evitando validar outro preview. Os testes exercitam navegação, histórico, refresh, recuperação, foco, teclado, movimento reduzido e layout. Axe não detectou violações nas cinco páginas em cada uma das quatro larguras. Há verificações adicionais em paisagem (844 × 390) e com largura útil de 305 px, para acomodar uma barra de rolagem de 15 px numa janela de 320 px.

A instalação inicial apontou vulnerabilidade alta transitiva em `brace-expansion`. Uma atualização compatível via `npm audit fix` corrigiu o lockfile; nenhuma exceção de segurança foi adicionada. Os avisos `NO_COLOR`/`FORCE_COLOR` do Playwright e LF/CRLF do Git são de ambiente; nenhum teste foi ignorado.

## Inspeção visual e arquivos

32 PNGs reais foram retidos em `frontend/test-results/evidence/`, ignorados pelo Git, junto ao relatório em `frontend/playwright-report/`. Para cada prefixo `mobile-320`, `mobile-390`, `tablet-768` e `desktop-1440`, os sufixos são `home`, `catalogo`, `clientes`, `locacoes`, `404`, `keyboard-focus`, `landscape` e `scrollbar-budget-305`.

O executor inspecionou capturas do início em 320/768/1440 px, do catálogo em 390 px, de foco por teclado em 320 px e da recuperação em 305 px. A paleta verde/creme e a arte original foram preservadas; texto, espaçamento e contraste foram ajustados. Fontes do sistema evitam carregamento externo.

Inspeção manual adicional pelo **coordenador**, no Chromium integrado ao Codex no Windows: após corrigir a largura mínima do corpo, a janela de 320 px apresentou `innerWidth=320`, `clientWidth=305` e `scrollWidth=305`, sem barra horizontal, com os quatro links disponíveis. O início em 390 px e os cards/navegação em 768 px estavam legíveis; a tela de locações em 1440 px mostrou o escopo em construção com clareza. Tab a partir do conteúdo alcançou o link de retorno com contorno visível, Enter retornou ao início e a recuperação da página não encontrada funcionou.

Essa inspeção não substitui a revisão independente do SHA final, validação com a equipe da locadora, leitores de tela, zoom real ou testes em dispositivos físicos e outros navegadores. Os testes automatizados não certificam usabilidade ou conformidade integral de acessibilidade.

## Limites de entrega

Nenhum arquivo acumulado de backend, infraestrutura ou automação foi incorporado. Alterações em configurações existentes e HTML, além do escopo funcional, são formatação necessária ao check Prettier. Publicação de branch/PR e estado do Project são responsabilidades do coordenador. A ausência de workflow remoto e proteção da branch, informada pelo coordenador, impede afirmar que exista validação remota ou autorização técnica para merge automático.
