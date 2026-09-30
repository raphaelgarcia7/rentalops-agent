# RentalOps Agent

Sistema para organizar locações de decorações e itens para festas e eventos. O RentalOps reúne a operação tradicional de uma locadora com um assistente conversacional capaz de ajudar a consultar o catálogo, verificar disponibilidade e preparar reservas.

O projeto tem dois objetivos: resolver um fluxo real de locação e servir como estudo prático de engenharia de software e AI Engineering.

## O problema

Uma locação pode envolver vários itens, kits, quantidades, datas, estoque e informações que o cliente ainda precisa esclarecer. Fazer esse processo por conversas soltas ou planilhas dificulta saber o que está disponível, calcular uma proposta consistente e acompanhar a reserva.

O RentalOps pretende centralizar essas informações e permitir que a mesma operação seja feita por telas convencionais ou por conversa com o agente.

## O que o sistema deve oferecer

- Cadastro e consulta de produtos e itens avulsos.
- Criação de kits compostos por produtos do catálogo.
- Cadastro de clientes.
- Consulta de disponibilidade por período.
- Montagem de reservas com kits, itens avulsos ou ambos.
- Cálculo e apresentação de uma proposta antes da confirmação.
- Acompanhamento das reservas e, em etapas futuras, geração e gestão de contratos.
- Interface conversacional para realizar os mesmos fluxos disponíveis na operação tradicional.

### Exemplo de uso

Uma pessoa pede um kit Sonic para os dias 10 a 13 e acrescenta dois vasos. Se a cor dos vasos não estiver informada, o assistente pergunta. Depois da resposta, consulta o catálogo e a disponibilidade, calcula a proposta e apresenta os detalhes para confirmação.

## Princípios do agente

O agente interpreta a conversa, identifica a intenção, reúne dados que faltam e escolhe quais operações solicitar. Ele não é a fonte de verdade das regras comerciais.

Estoque, preços, disponibilidade e reservas devem ser determinados por dados persistidos e por regras explícitas da aplicação. A interface convencional e as ferramentas do agente devem usar os mesmos serviços de aplicação, para que uma reserva siga as mesmas validações independentemente de como foi iniciada.

A conversa pode guardar contexto temporário para continuar um atendimento, mas esse contexto não substitui os registros de negócio. O agente deve pedir esclarecimentos quando houver ambiguidade e apresentar o que será feito antes de confirmar uma operação importante.

## Escopo de evolução

O desenvolvimento deve avançar por fatias verticais: uma capacidade útil de ponta a ponta, da interface e conversa até a validação da operação. O primeiro fluxo deve exercitar catálogo, período, disponibilidade e composição de uma reserva, sem tentar construir todo o produto de uma vez.

Conforme o produto crescer, o projeto poderá explorar mecanismos usados em sistemas reais de AI Engineering, como estado de conversa, retomada de sessões, resumo de conversas longas, rastreamento das chamadas do modelo e avaliação de comportamento. Cada mecanismo deve entrar quando resolver uma necessidade concreta do fluxo.

## Arquitetura em alto nível

```text
Interface web ──┬──> API e serviços de aplicação ──> dados de negócio
                └──> agente ──> ferramentas ────────┘
```

A API e o agente são formas diferentes de iniciar operações. As regras de negócio ficam nos serviços da aplicação; as ferramentas do agente chamam esses serviços em vez de duplicar validações. O banco de dados será a fonte de verdade para os dados de negócio.

## Tecnologias

- **Backend:** Python, FastAPI e LangGraph.
- **Frontend:** React, TypeScript e Vite.
- **Modelo:** integração com OpenAI.
- **Comunicação em tempo real:** Server-Sent Events (SSE) para acompanhar o fluxo do agente.

As tecnologias de persistência e de continuidade das conversas serão definidas quando o fluxo vertical precisar delas, considerando os requisitos de retomada, concorrência e implantação.

## Estado atual

O repositório ainda contém a demonstração inicial de clima: um agente LangGraph, uma ferramenta simulada e uma interface que recebe eventos por SSE. Ela serve como base técnica para o streaming, mas ainda não implementa catálogo, estoque ou reservas do RentalOps.

As próximas entregas devem substituir esse fluxo demonstrativo gradualmente por operações de locação, mantendo o produto executável durante a evolução.

## Como executar a base atual

### Requisitos

- Python 3.14.
- [uv](https://docs.astral.sh/uv/).
- Node.js 24 ou superior.
- Uma chave de API da OpenAI.

### Configuração

Na raiz do projeto, instale as dependências do backend:

```bash
uv sync
```

Copie `.env.example` para `.env` e informe a chave da OpenAI:

```dotenv
OPENAI_API_KEY=sua_chave_aqui
OPENAI_MODEL=gpt-5.6-luna
```

O arquivo `.env` é ignorado pelo Git. Não coloque credenciais em arquivos versionados.

Instale as dependências do frontend:

```bash
cd frontend
npm install
```

### Inicialização

Abra dois terminais na raiz do projeto. No primeiro, inicie a API:

```bash
uv run rentalops-agent --reload
```

A API fica em `http://127.0.0.1:8000`, e a documentação interativa em `http://127.0.0.1:8000/docs`.

No segundo terminal, inicie a interface:

```bash
cd frontend
npm run dev
```

Acesse `http://localhost:5173`. Na base atual, a demonstração ainda responde à pergunta de clima; esse comportamento será substituído pelos fluxos de locação.

## Estrutura atual

```text
rentalops-agent/
├── src/rentalops_agent/  # API, agente, grafo e ferramentas Python
├── frontend/             # Interface React e cliente SSE
├── .env.example          # Exemplo de configuração local
├── pyproject.toml        # Dependências e configuração do backend
└── README.md
```

## Direção do projeto

O objetivo é construir um produto pequeno, demonstrável e confiável. A evolução deve priorizar regras de negócio explícitas, operações verificáveis, contratos claros entre frontend e backend e um agente que use ferramentas com limites bem definidos.
