ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE} AS base

# Company-specific customization arguments
ARG HTTP_PROXY=""
ARG HTTPS_PROXY=""
ARG NO_PROXY=""
ARG PIP_INDEX_URL=""
ARG PIP_TRUSTED_HOST=""
ARG EXTRA_CA_CERTS=""

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENV HTTP_PROXY=${HTTP_PROXY} HTTPS_PROXY=${HTTPS_PROXY} NO_PROXY=${NO_PROXY}

WORKDIR /app

USER root

# Install extra CA certificates if provided
RUN if [ -n "${EXTRA_CA_CERTS}" ]; then \
        echo "${EXTRA_CA_CERTS}" > /usr/local/share/ca-certificates/company-certs.crt \
        && update-ca-certificates; \
    fi

# Configure pip with persistent settings if custom registry is provided
RUN if [ -n "${PIP_INDEX_URL}" ]; then \
        mkdir -p /etc/pip && \
        echo "[global]" > /etc/pip/pip.conf && \
        echo "index-url = ${PIP_INDEX_URL}" >> /etc/pip/pip.conf && \
        if [ -n "${PIP_TRUSTED_HOST}" ]; then \
            echo "trusted-host = ${PIP_TRUSTED_HOST}" >> /etc/pip/pip.conf; \
        fi; \
    fi

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates openssh-client curl tar \
    && ARCH=$(uname -m) \
    && curl -fsSLk https://download.docker.com/linux/static/stable/${ARCH}/docker-25.0.5.tgz | tar -xz -C /usr/local/bin --strip-components=1 docker/docker \
    && case "${ARCH}" in \
        x86_64) KUBECTL_ARCH=amd64 ;; \
        aarch64) KUBECTL_ARCH=arm64 ;; \
        *) echo "Unsupported architecture ${ARCH}" && exit 1 ;; \
    esac \
    && curl -fsSLko /usr/local/bin/kubectl "https://dl.k8s.io/release/v1.30.3/bin/linux/${KUBECTL_ARCH}/kubectl" \
    && chmod +x /usr/local/bin/kubectl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-dev.txt ./

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip \
    && pip install --retries 10 --timeout 300 -r requirements-dev.txt

RUN useradd -m -u 1000 appuser \
    && groupadd -g 999 docker || true \
    && chown -R appuser:appuser /app

COPY --chown=appuser:appuser . .

USER appuser

CMD ["python", "manage.py", "runserver", "0.0.0.0:8001"]
