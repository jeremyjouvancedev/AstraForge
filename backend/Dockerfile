FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates openssh-client curl tar \
    && ARCH=$(uname -m) \
    && curl -fsSL https://download.docker.com/linux/static/stable/${ARCH}/docker-25.0.5.tgz | tar -xz -C /usr/local/bin --strip-components=1 docker/docker \
    && case "${ARCH}" in \
        x86_64) KUBECTL_ARCH=amd64 ;; \
        aarch64) KUBECTL_ARCH=arm64 ;; \
        *) echo "Unsupported architecture ${ARCH}" && exit 1 ;; \
    esac \
    && curl -fsSLo /usr/local/bin/kubectl "https://dl.k8s.io/release/v1.30.3/bin/linux/${KUBECTL_ARCH}/kubectl" \
    && chmod +x /usr/local/bin/kubectl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./

RUN pip install --upgrade pip && pip install .[dev]

COPY . .

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
