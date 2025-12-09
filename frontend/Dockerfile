FROM node:20-alpine AS build
WORKDIR /app

# Install pnpm via corepack and keep binaries in a predictable location
ENV PNPM_HOME="/pnpm"
ENV PATH="${PNPM_HOME}:${PATH}"
RUN corepack enable

# Install dependencies with a frozen lockfile for reproducible builds
COPY package.json pnpm-lock.yaml ./
COPY tsconfig.json tsconfig.base.json vite.config.ts vitest.config.ts tailwind.config.ts postcss.config.js components.json index.html ./
COPY src ./src
COPY public ./public
RUN pnpm install --frozen-lockfile
RUN pnpm build

FROM nginx:1.27-alpine AS runner
ENV BACKEND_ORIGIN="http://backend:8001"

# Nginx does envsubst on templates in /etc/nginx/templates by default
COPY docker/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
