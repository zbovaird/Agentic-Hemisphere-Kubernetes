FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /install /usr/local
COPY operator.py .
COPY templates/ ./templates/

RUN addgroup --system appgroup && \
    adduser --system --ingroup appgroup appuser
USER appuser

CMD ["kopf", "run", "operator.py", "--verbose"]
