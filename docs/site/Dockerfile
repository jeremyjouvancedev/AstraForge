ARG NODE_BASE_IMAGE=node:20-alpine
ARG NGINX_BASE_IMAGE=nginx:alpine

FROM ${NODE_BASE_IMAGE} AS builder

# Company-specific customization arguments
ARG HTTP_PROXY=""
ARG HTTPS_PROXY=""
ARG NO_PROXY=""
ARG NPM_REGISTRY=""
ARG EXTRA_CA_CERTS=""

ENV HTTP_PROXY=${HTTP_PROXY} HTTPS_PROXY=${HTTPS_PROXY} NO_PROXY=${NO_PROXY}

# Install extra CA certificates if provided (works for both Alpine and Debian)
RUN if [ -n "${EXTRA_CA_CERTS}" ]; then \
        if command -v apk > /dev/null 2>&1; then \
            apk add --no-cache ca-certificates; \
        elif command -v apt-get > /dev/null 2>&1; then \
            mkdir -p /var/lib/apt/lists/partial && \
            apt-get update && apt-get install -y ca-certificates && rm -rf /var/lib/apt/lists/*; \
        fi \
        && echo "${EXTRA_CA_CERTS}" > /usr/local/share/ca-certificates/company-certs.crt \
        && update-ca-certificates; \
    fi

WORKDIR /app

# Copy .npmrc first if it exists to configure registry before installing pnpm
COPY .npmrc* ./

# Configure npm registry if provided
RUN if [ -n "${NPM_REGISTRY}" ]; then \
        npm config set registry "${NPM_REGISTRY}"; \
    fi

# Enable pnpm
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN npm i -g pnpm

# Configure pnpm to use the same registry as npm if NPM_REGISTRY is set
RUN if [ -n "${NPM_REGISTRY}" ]; then \
        pnpm config set registry "${NPM_REGISTRY}"; \
    fi

# Copy package files
COPY package.json pnpm-lock.yaml ./

# Install dependencies
RUN --mount=type=cache,target=/pnpm/store \
    pnpm config set store-dir /pnpm/store && \
    pnpm install --frozen-lockfile

# Copy source
COPY . .

# Build static site
RUN pnpm build

# Serve with Nginx
FROM ${NGINX_BASE_IMAGE}

COPY --from=builder /app/out /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
