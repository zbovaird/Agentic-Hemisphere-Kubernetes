FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /install /usr/local
COPY operator.py .
COPY templates/ ./templates/

# Match k8s runAsUser: 1000; ensure /etc/passwd has entry for getpass.getuser()
RUN addgroup --system --gid 1000 appgroup && \
    adduser --system --uid 1000 --ingroup appgroup appuser
USER appuser

CMD ["kopf", "run", "operator.py", "--verbose", "--standalone"]
