# Imagem do front: build estático (Vite) servido pelo Caddy, que também faz o proxy de /api para o back.
# Contexto de build = raiz do monorepo:  docker build -f front/Dockerfile .
FROM --platform=$BUILDPLATFORM node:22-alpine AS build
RUN corepack enable
WORKDIR /repo
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY front/package.json front/
COPY packages/api-client/package.json packages/api-client/
RUN pnpm install --frozen-lockfile --filter "@pilates/front..."
COPY front front
COPY packages/api-client packages/api-client
# VITE_API_URL vazio: o navegador chama a API na mesma origem (/api/...).
RUN pnpm --filter @pilates/front build

FROM caddy:2-alpine
COPY front/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /repo/front/dist /srv
