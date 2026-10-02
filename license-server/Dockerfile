# CreatorWatch License Server — multi-stage (chhoti image, buildx-ready).
#   docker buildx build --platform linux/amd64,linux/arm64 -t creatorwatch-license .

# ---- stage 1: sirf dependencies install ----
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- stage 2: runtime — app + deps, NO pip/build tools ----
FROM python:3.12-slim
WORKDIR /srv/license-server
COPY --from=builder /install /usr/local
COPY app.py db.py ./
COPY templates/ ./templates/
ENV HOST=0.0.0.0 PORT=5001 LICENSE_DB=/data/licenses.db \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# Koi domain hardcode nahi — apne domain se chalao:
#   -e SITE_DOMAIN=cw.raoshahzaib.site -e SITE_NAME=CreatorWatch
VOLUME ["/data"]
EXPOSE 5001
CMD ["python", "app.py"]
