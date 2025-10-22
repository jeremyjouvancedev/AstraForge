FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .[dev]
COPY . .
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
