ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE}

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
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

COPY --chown=appuser:appuser pyproject.toml ./
COPY --chown=appuser:appuser app ./app

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip \
    && pip install --retries 10 --timeout 300 .

USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
