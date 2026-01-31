# Docker Customization Guide

This guide explains how to customize Docker builds for company-specific requirements without modifying files tracked by Git.

## Overview

AstraForge supports Docker build customization through `docker-compose.override.yml`, which allows you to:
- Use custom base images from private registries
- Configure corporate proxies
- Add custom CA certificates
- Use internal package mirrors (PyPI, npm)

**All company-specific Docker configuration is managed in `docker-compose.override.yml`** (which is gitignored).

## Quick Start

### For First-Time Setup

1. **Use the example template as reference:**
   ```bash
   # View the example to see all available options
   cat docker-compose.override.yml.example
   ```

2. **Create your own `docker-compose.override.yml`:**
   ```bash
   # Start with a minimal version or copy from the example
   cp docker-compose.override.yml.example docker-compose.override.yml
   ```

3. **Edit `docker-compose.override.yml` with your settings:**
   The file is automatically gitignored, so your changes stay local.

4. **Build and run as normal:**
   ```bash
   # Build everything (services + workspace images) and start
   make up-all

   # Or do it in steps:
   make build-all    # Build all services + workspace images
   make up           # Start all services
   ```
   Docker Compose automatically merges the override file with `docker-compose.yml`.

### If You Have BASE_IMAGE Variables in .env

The old approach used `.env` variables like `BACKEND_BASE_IMAGE`, `FRONTEND_BASE_IMAGE`, etc.

**Migration steps:**
1. Copy your base image values from `.env` to `docker-compose.override.yml`
2. Remove the `BASE_IMAGE` variables from your `.env` file
3. The new approach consolidates all Docker customization in one place

## Configuration Options

### Workspace Images

AstraForge uses isolated workspace images for executing user code. These images need to be built with the same customizations as your main services:

```yaml
services:
  computer-use-image:
    build:
      args:
        BASE_IMAGE: company-registry.example.com/python:3.11-slim
        HTTP_PROXY: http://proxy.company.com:8080
        HTTPS_PROXY: http://proxy.company.com:8080
        NO_PROXY: localhost,127.0.0.1,.company.com
        PIP_INDEX_URL: https://pypi.company.com/simple
        PIP_TRUSTED_HOST: pypi.company.com
        EXTRA_CA_CERTS: |
          -----BEGIN CERTIFICATE-----
          [Your company's root CA certificate]
          -----END CERTIFICATE-----

  astra-control-image:
    build:
      args:
        # Same customization options as computer-use-image
        BASE_IMAGE: company-registry.example.com/python:3.11-slim
        PIP_INDEX_URL: https://pypi.company.com/simple
        PIP_TRUSTED_HOST: pypi.company.com

  sandbox-image:
    build:
      args:
        # Same customization options as computer-use-image
        BASE_IMAGE: company-registry.example.com/python:3.11-slim
        PIP_INDEX_URL: https://pypi.company.com/simple
        PIP_TRUSTED_HOST: pypi.company.com
```

**Building workspace images:**
```bash
# Build all workspace images
make workspace-images

# Or build individually
make computer-use-image
make astra-control-image
make sandbox-image

# Build with docker-compose directly
docker-compose build computer-use-image astra-control-image sandbox-image
```

**Important:** Workspace images now support persistent pip configuration. When you configure `PIP_INDEX_URL` and `PIP_TRUSTED_HOST`, these settings will apply to all `pip install` commands run inside the sandboxes, not just during the initial build.

### Base Images

Change the base image for any service:

```yaml
services:
  backend:
    build:
      args:
        BASE_IMAGE: company-registry.example.com/python:3.11-slim
```

Available base image arguments:
- `BASE_IMAGE` - Python services (backend, llm-proxy)
- `NODE_BASE_IMAGE` - Frontend build stage
- `NGINX_BASE_IMAGE` - Frontend runtime stage

### Corporate Proxy

Configure HTTP/HTTPS proxy for build-time network access:

```yaml
services:
  backend:
    build:
      args:
        HTTP_PROXY: http://proxy.company.com:8080
        HTTPS_PROXY: http://proxy.company.com:8080
        NO_PROXY: localhost,127.0.0.1,.company.com,postgres,redis,minio
```

### Python Package Index (PyPI)

Use an internal PyPI mirror:

```yaml
services:
  backend:
    build:
      args:
        PIP_INDEX_URL: https://pypi.company.com/simple
        PIP_TRUSTED_HOST: pypi.company.com
```

### NPM Registry

Use an internal npm registry for frontend builds:

```yaml
services:
  frontend:
    build:
      args:
        NPM_REGISTRY: https://npm.company.com
```

### CA Certificates

Add custom root CA certificates for SSL verification:

```yaml
services:
  backend:
    build:
      args:
        EXTRA_CA_CERTS: |
          -----BEGIN CERTIFICATE-----
          MIIDXTCCAkWgAwIBAgIJAKJ...
          -----END CERTIFICATE-----
```

You can also load from a file:

```yaml
services:
  backend:
    build:
      args:
        EXTRA_CA_CERTS: ${COMPANY_CA_CERT}
```

Then export the variable:
```bash
export COMPANY_CA_CERT="$(cat /path/to/company-ca.crt)"
```

### Pre-built Images

If you need to pull from a private registry for services like PostgreSQL, Redis, etc.:

```yaml
services:
  postgres:
    image: company-registry.example.com/pgvector/pgvector:pg16

  redis:
    image: company-registry.example.com/redis:7
```

## Complete Example

Here's a full example with all customization options:

```yaml
services:
  # Workspace images (used for code execution sandboxes)
  computer-use-image:
    build:
      args:
        BASE_IMAGE: company-registry.example.com/python:3.11-slim
        HTTP_PROXY: http://proxy.company.com:8080
        HTTPS_PROXY: http://proxy.company.com:8080
        NO_PROXY: localhost,127.0.0.1,.company.com
        PIP_INDEX_URL: https://pypi.company.com/simple
        PIP_TRUSTED_HOST: pypi.company.com
        EXTRA_CA_CERTS: |
          -----BEGIN CERTIFICATE-----
          [Your company's root CA certificate]
          -----END CERTIFICATE-----

  astra-control-image:
    build:
      args:
        BASE_IMAGE: company-registry.example.com/python:3.11-slim
        HTTP_PROXY: http://proxy.company.com:8080
        HTTPS_PROXY: http://proxy.company.com:8080
        NO_PROXY: localhost,127.0.0.1,.company.com
        PIP_INDEX_URL: https://pypi.company.com/simple
        PIP_TRUSTED_HOST: pypi.company.com

  sandbox-image:
    build:
      args:
        BASE_IMAGE: company-registry.example.com/python:3.11-slim
        HTTP_PROXY: http://proxy.company.com:8080
        HTTPS_PROXY: http://proxy.company.com:8080
        NO_PROXY: localhost,127.0.0.1,.company.com
        PIP_INDEX_URL: https://pypi.company.com/simple
        PIP_TRUSTED_HOST: pypi.company.com

  backend:
    build:
      args:
        BASE_IMAGE: company-registry.example.com/python:3.11-slim
        HTTP_PROXY: http://proxy.company.com:8080
        HTTPS_PROXY: http://proxy.company.com:8080
        NO_PROXY: localhost,127.0.0.1,.company.com,postgres,redis,minio
        PIP_INDEX_URL: https://pypi.company.com/simple
        PIP_TRUSTED_HOST: pypi.company.com
        EXTRA_CA_CERTS: |
          -----BEGIN CERTIFICATE-----
          [Your company's root CA certificate]
          -----END CERTIFICATE-----

  backend-migrate:
    build:
      args:
        BASE_IMAGE: company-registry.example.com/python:3.11-slim
        HTTP_PROXY: http://proxy.company.com:8080
        HTTPS_PROXY: http://proxy.company.com:8080
        NO_PROXY: localhost,127.0.0.1,.company.com,postgres,redis,minio
        PIP_INDEX_URL: https://pypi.company.com/simple
        PIP_TRUSTED_HOST: pypi.company.com

  backend-worker:
    build:
      args:
        BASE_IMAGE: company-registry.example.com/python:3.11-slim
        HTTP_PROXY: http://proxy.company.com:8080
        HTTPS_PROXY: http://proxy.company.com:8080
        NO_PROXY: localhost,127.0.0.1,.company.com,postgres,redis,minio
        PIP_INDEX_URL: https://pypi.company.com/simple
        PIP_TRUSTED_HOST: pypi.company.com

  computer-use-worker:
    build:
      args:
        BASE_IMAGE: company-registry.example.com/python:3.11-slim
        HTTP_PROXY: http://proxy.company.com:8080
        HTTPS_PROXY: http://proxy.company.com:8080
        NO_PROXY: localhost,127.0.0.1,.company.com,postgres,redis,minio
        PIP_INDEX_URL: https://pypi.company.com/simple
        PIP_TRUSTED_HOST: pypi.company.com

  astra-control-worker:
    build:
      args:
        BASE_IMAGE: company-registry.example.com/python:3.11-slim
        HTTP_PROXY: http://proxy.company.com:8080
        HTTPS_PROXY: http://proxy.company.com:8080
        NO_PROXY: localhost,127.0.0.1,.company.com,postgres,redis,minio
        PIP_INDEX_URL: https://pypi.company.com/simple
        PIP_TRUSTED_HOST: pypi.company.com

  llm-proxy:
    build:
      args:
        BASE_IMAGE: company-registry.example.com/python:3.11-slim
        HTTP_PROXY: http://proxy.company.com:8080
        HTTPS_PROXY: http://proxy.company.com:8080
        NO_PROXY: localhost,127.0.0.1,.company.com,postgres,redis,minio
        PIP_INDEX_URL: https://pypi.company.com/simple
        PIP_TRUSTED_HOST: pypi.company.com

  frontend:
    build:
      args:
        NODE_BASE_IMAGE: company-registry.example.com/node:20-alpine
        HTTP_PROXY: http://proxy.company.com:8080
        HTTPS_PROXY: http://proxy.company.com:8080
        NO_PROXY: localhost,127.0.0.1,.company.com
        NPM_REGISTRY: https://npm.company.com

  docs:
    build:
      args:
        BASE_IMAGE: company-registry.example.com/node:20-alpine
        HTTP_PROXY: http://proxy.company.com:8080
        HTTPS_PROXY: http://proxy.company.com:8080
        NO_PROXY: localhost,127.0.0.1,.company.com
        NPM_REGISTRY: https://npm.company.com

  postgres:
    image: company-registry.example.com/pgvector/pgvector:pg16

  redis:
    image: company-registry.example.com/redis:7

  minio:
    image: company-registry.example.com/minio/minio:latest

  minio-setup:
    image: company-registry.example.com/minio/mc:latest
```

## Troubleshooting

### Proxy Issues

If you're behind a corporate proxy:
1. Ensure `NO_PROXY` includes all internal service names
2. Check that your proxy allows Docker registry access
3. Verify proxy credentials if required

### Certificate Issues

If you see SSL certificate errors:
1. Export your company's root CA certificate in PEM format
2. Add it to `EXTRA_CA_CERTS` in docker-compose.override.yml
3. Rebuild the images: `docker-compose build --no-cache`

### Registry Authentication

For private registries requiring authentication:

```bash
docker login company-registry.example.com
```

Docker Compose will use your stored credentials automatically.

### Build Cache

If changes don't take effect:

```bash
docker-compose build --no-cache
```

## Best Practices

1. **Version Control**: Never commit `docker-compose.override.yml` (it's gitignored)
2. **Team Sharing**: Share `docker-compose.override.yml.example` updates with the team
3. **Documentation**: Document company-specific setup in internal wikis
4. **Security**: Keep credentials out of override files; use environment variables or Docker secrets
5. **Testing**: Test with `--no-cache` to ensure builds work from scratch

## Why Not Use .env for BASE_IMAGE Variables?

Previous versions of this guide suggested using `.env` variables like `BACKEND_BASE_IMAGE`. We've moved away from this approach because:

1. **Consolidation**: All Docker build customization is now in one place (`docker-compose.override.yml`)
2. **Clarity**: The override file explicitly shows which services use which images
3. **Flexibility**: Easier to add proxy, certificate, and registry configs alongside base images
4. **Best Practice**: Docker Compose override files are the standard way to customize compose configurations

The `.env` file should be used for runtime environment variables, not build-time configuration.

## Getting Updates

When pulling updates from the open-source repository:

1. Your `docker-compose.override.yml` stays intact (it's gitignored)
2. Check `docker-compose.override.yml.example` for new services or options
3. Merge any new configuration into your local override file

## Quick Reference: Common Commands

### One-Command Workflows

```bash
# Build everything and start (most common)
make up-all

# Build all services + workspace images
make build-all

# Build only workspace images
make workspace-images
```

### Individual Commands

```bash
# Build specific workspace image
make computer-use-image
make astra-control-image
make sandbox-image

# Build specific service
make build-backend
make build-frontend

# Start services (without rebuilding)
make up

# View logs
make logs

# Stop everything
make down
```

### Debugging

```bash
# Verify override is applied
make config

# Build with verbose output
docker-compose build --progress=plain

# Build without cache
make build-clean
```

## Need Help?

If you encounter issues:
1. Check that build args are spelled correctly (they're case-sensitive)
2. Verify your registry/proxy URLs are accessible
3. Test without the override first: `docker-compose -f docker-compose.yml build`
4. Check Docker build output for specific errors: `docker-compose build --progress=plain`
