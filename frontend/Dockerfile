FROM node:20-alpine AS base
WORKDIR /app
COPY package.json tsconfig.json tsconfig.base.json vite.config.ts vitest.config.ts .
RUN corepack enable && pnpm install
COPY src ./src
COPY public ./public
CMD ["pnpm", "dev", "--host", "0.0.0.0"]
