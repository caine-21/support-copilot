FROM python:3.12.11-slim

ARG SUPPORT_GIT_SHA=unknown
ARG SUPPORT_BUILD_TIME=unknown

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860 \
    SUPPORT_DEPLOYMENT_MODE=demo \
    ENABLE_PROVIDER_CALLS=false \
    ENABLE_PUBLIC_DEMO=true \
    ENABLE_CUSTOMER_PORTAL=true \
    ENABLE_EXECUTOR=false \
    ENABLE_ADMIN=false \
    ENABLE_DOCS=false \
    SUPPORT_GIT_SHA=${SUPPORT_GIT_SHA} \
    SUPPORT_BUILD_TIME=${SUPPORT_BUILD_TIME}

WORKDIR /app
COPY requirements-runtime.txt ./
RUN pip install --no-cache-dir --requirement requirements-runtime.txt

COPY . .
RUN mkdir -p /app/data/service && chown -R 1000:1000 /app
USER 1000:1000

EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '7860') + '/livez', timeout=3).read()"]
CMD ["python", "-m", "service.container_entrypoint"]
