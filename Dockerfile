# =====================================================
# Agnes AI Platform 生产镜像（多阶段）
# 阶段 1：构建前端 dist；阶段 2：Python 运行时同源托管前后端
# 用户产物（uploads/data/logs/SQLite）全部落在 /app/data 数据卷，见 docker/entrypoint.sh
# 构建：docker build -t agnes-ai-platform .
# 运行：docker run -d -p 8080:8000 -v agnes-data:/app/data agnes-ai-platform
# =====================================================

# ---------- 阶段 1：前端构建 ----------
FROM node:22-alpine AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---------- 阶段 2：后端运行时 ----------
FROM python:3.12-slim
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION} \
    DATABASE_URL=sqlite:////app/data/agnes_platform.db \
    HF_HOME=/app/data/hf

WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ /app/backend/
COPY --from=frontend-build /build/dist /app/frontend/dist
COPY VERSION /app/VERSION
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh && mkdir -p /app/data

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"
ENTRYPOINT ["/app/entrypoint.sh"]
