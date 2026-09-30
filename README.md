# RentalOps Agent

Agente construído com FastAPI, LangGraph, OpenAI e React. A resposta chega ao navegador em tempo real por Server-Sent Events (SSE), mostrando a decisão do modelo, a execução da ferramenta e a resposta final em estados separados. A ferramenta de clima é, por enquanto, um stub de demonstração.

## O que o projeto faz

Ao receber uma pergunta como **“Qual o clima em São Paulo?”**, o agente:

1. executa o modelo com a ferramenta `get_weather`;
2. identifica a chamada solicitada pelo modelo;
3. executa o stub local, que aguarda aproximadamente dois segundos;
4. devolve `{ "city": "São Paulo", "temp_c": 22, "condition": "parcialmente nublado" }`;
5. chama o modelo novamente e transmite a resposta final token a token.

O endpoint HTTP apenas encaminha o fluxo produzido pelo agente. O grafo e os eventos do LangGraph ficam isolados no backend.


## Requisitos

- Python 3.14
- [uv](https://docs.astral.sh/uv/)
- Node.js 24 ou superior
- uma chave da OpenAI

## Configuração

Na raiz do projeto, instale as dependências:

```bash
uv sync
```

Copie `.env.example` para `.env` e informe a sua chave:

```dotenv
OPENAI_API_KEY=sua_chave_aqui
OPENAI_MODEL=gpt-5.6-luna
```

O arquivo `.env` está no `.gitignore` e não deve ser versionado.

Instale o frontend:

```bash
cd frontend
npm install
```

## Como executar

Abra dois terminais na raiz do projeto.

No primeiro, inicie a API:

```bash
uv run rentalops-agent --reload
```

A API ficará disponível em `http://127.0.0.1:8000`. A documentação interativa fica em `http://127.0.0.1:8000/docs`.

No segundo, inicie a interface:

```bash
cd frontend
npm run dev
```

Acesse `http://localhost:5173`. O Vite encaminha as chamadas de `/agent` para a API local.

## Smoke test

Com a API e o frontend em execução, envie:

> Qual o clima em São Paulo?

A interface deve mostrar, nesta ordem:

1. a chamada de `get_weather`;
2. a ferramenta em execução;
3. o JSON do stub com temperatura de 22 °C;
4. a frase final gerada pelo modelo.

Também é possível testar o endpoint diretamente:

```bash
curl -N -X POST http://127.0.0.1:8000/agent/execute \
  -H "Content-Type: application/json" \
  -d '{"message":"Qual o clima em São Paulo?"}'
```

## Contrato da API

### `POST /agent/execute`

Body:

```json
{ "message": "Qual o clima em São Paulo?" }
```

A resposta usa `text/event-stream`. Cada item contém o nome do evento do LangGraph e o `StreamEvent` completo:

```text
event: on_tool_start
data: {"event":"on_tool_start","name":"get_weather","data":{...}}
```

São transmitidos somente eventos dos tipos `chat_model` e `tool`, por meio de `astream_events(..., version="v2")`.

## Estrutura

```text
rentalops-agent/
├── src/rentalops_agent/
│   ├── main.py       # rota HTTP e configuração do FastAPI
│   ├── agent.py      # compilação do grafo e serialização SSE
│   ├── graph.py      # nós, arestas e ligação do modelo às tools
│   └── tools.py      # stub get_weather
├── frontend/
│   └── src/
│       ├── App.tsx
│       └── lib/      # parser SSE e renderização dos eventos
├── .env.example
└── pyproject.toml
```

## Verificação

```bash
uv run python -m compileall -q src
cd frontend
npm run lint
npm run build
```
