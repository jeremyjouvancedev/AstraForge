FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates openssh-client curl tar \
    && ARCH=$(uname -m) \
    && curl -fsSL https://download.docker.com/linux/static/stable/${ARCH}/docker-25.0.5.tgz | tar -xz -C /usr/local/bin --strip-components=1 docker/docker \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./

RUN pip install --upgrade pip && pip install .[dev]

COPY . .

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
