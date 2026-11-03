# Instruções para agentes

- **Requisitos do produto:** leia [docs/requisitos.md](docs/requisitos.md) antes de implementar ou alterar
  funcionalidades em `back/`, `front/` ou `mobile/`. Se um requisito ou decisão mudar, atualize esse arquivo
  na mesma mudança.
- **Contrato da API:** o back é a fonte da verdade. Após mudar rotas/schemas, rode `pnpm api:types` e
  commite `packages/api-client/openapi.json` e `src/schema.d.ts` junto.
- **Back:** `cd back && uv run pytest` deve passar. Detalhes em [back/README.md](back/README.md).
- Código em inglês; textos para o usuário e documentação em português.
