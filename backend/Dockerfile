# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
RUN useradd --system --uid 10001 --no-create-home app
COPY --from=builder /install /usr/local
WORKDIR /srv
COPY app ./app
COPY scripts ./scripts
COPY migrations ./migrations
COPY alembic.ini .
USER 10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
