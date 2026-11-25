# syntax=docker/dockerfile:1
# --- build : on installe les dependances dans un venv, sans outils de compilation dans l'image finale
FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
RUN python -m venv /opt/venv
COPY requirements.txt .
# Allègement de l'image (mesuré dans le rapport) : pip n'est plus utile à l'exécution, et botocore embarque les
# descriptions de ~400 services AWS alors que seul S3 est utilisé.
RUN /opt/venv/bin/pip install -r requirements.txt \
 && /opt/venv/bin/pip uninstall -y pip \
 && find /opt/venv/lib/python3.12/site-packages/botocore/data -mindepth 1 -maxdepth 1 -type d ! -name s3 ! -name sts -exec rm -rf {} +

# --- runtime : image fine, utilisateur non-root, aucun secret
FROM python:3.12-slim
ARG APP_VERSION=dev
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_VERSION=${APP_VERSION}
# correctifs de securite zlib/zstd publies apres la construction de l'image de base (CVE signalees par Trivy)
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends --only-upgrade zlib1g libzstd1 \
 && rm -rf /var/lib/apt/lists/*
RUN groupadd --system --gid 10001 app && useradd --system --uid 10001 --gid app --no-create-home app
COPY --from=builder /opt/venv /opt/venv
WORKDIR /srv
COPY app ./app
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s   CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status==200 else 1)"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
