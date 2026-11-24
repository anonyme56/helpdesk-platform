# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
RUN python -m venv /opt/venv
COPY requirements.txt .
RUN /opt/venv/bin/pip install -r requirements.txt \
 && /opt/venv/bin/pip uninstall -y pip \
 && find /opt/venv/lib/python3.12/site-packages/botocore/data -mindepth 1 -maxdepth 1 -type d ! -name s3 ! -name sts -exec rm -rf {} +

FROM python:3.12-slim
ARG APP_VERSION=dev
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 APP_VERSION=${APP_VERSION}
# correctif de securite zlib publie apres la construction de l'image de base (CVE signalees par Trivy)
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends --only-upgrade zlib1g \
 && rm -rf /var/lib/apt/lists/*
RUN groupadd --system --gid 10001 app && useradd --system --uid 10001 --gid app --no-create-home app
COPY --from=builder /opt/venv /opt/venv
WORKDIR /srv
COPY config.py crypto.py tasks.py worker.py ./
USER 10001
# metriques Prometheus du worker
EXPOSE 9100
CMD ["python", "worker.py"]
