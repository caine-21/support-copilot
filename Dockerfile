FROM python:3.12.16-slim-trixie

# Docker runtimes must refresh their own system trust store (DSA-6572-1).
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates \
    && dpkg --compare-versions "$(dpkg-query -W -f='${Version}' ca-certificates)" ge '20250419+deb13u1' \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

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
# pip vendors a separate CA bundle; updating application certifi is insufficient.
RUN python -m pip install --no-cache-dir --upgrade 'pip>=26.2.2' \
    && python -m pip install --no-cache-dir --requirement requirements-runtime.txt \
    && python -m pip check

COPY . .
RUN mkdir -p /app/data/service && chown -R 1000:1000 /app
USER 1000:1000

EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '7860') + '/livez', timeout=3).read()"]
CMD ["python", "-m", "service.container_entrypoint"]
