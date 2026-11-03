# Pilates

Sistema de gestão de estúdios de pilates (multitenant: um banco por estúdio).

| Pasta | Conteúdo | Stack |
|-------|----------|-------|
| [back/](back/) | API REST | Python 3.12+, FastAPI, SQLAlchemy, Alembic (uv) |
| [front/](front/) | Painel web do estúdio | React + TypeScript |
| [mobile/](mobile/) | App mobile | React Native (Expo) + TypeScript |
| [packages/api-client/](packages/api-client/) | Tipos e cliente HTTP da API, usados por front e mobile | TypeScript (gerado do OpenAPI) |

## Pré-requisitos

- [uv](https://docs.astral.sh/uv/) — back (instala o Python automaticamente)
- [Node.js 20+](https://nodejs.org/) e [pnpm](https://pnpm.io/) (`corepack enable`) — front, mobile e api-client

## Começando

```bash
# Back
cd back
uv sync
cp .env.example .env
uv run python -m app.cli init
uv run fastapi dev app/main.py          # http://localhost:8000/docs

# Parte JS (na raiz)
pnpm install
```

Detalhes do back: [back/README.md](back/README.md).

## Contrato da API (back → front/mobile)

O back é a fonte da verdade. Sempre que mudar rotas ou schemas da API:

```bash
pnpm api:types
```

Isso exporta `packages/api-client/openapi.json` a partir do FastAPI e regenera
`packages/api-client/src/schema.d.ts`. Front e mobile importam de `@pilates/api-client`:

```ts
import { createApiClient, type Schemas } from "@pilates/api-client";

const api = createApiClient({ baseUrl: "http://localhost:8000", getToken: () => token });
const { data } = await api.GET("/api/v1/calendar", { params: { query: { date_from: "2026-11-09" } } });
```

Commite `openapi.json` e `schema.d.ts` junto com a mudança do back — assim o diff mostra
exatamente o que mudou no contrato, e o TypeScript aponta o que quebrou no front/mobile.
