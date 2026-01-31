FROM python:3.12-slim AS base

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ============ 开发阶段 ============
FROM base AS development

# 安装开发工具
RUN pip install uv

# 复制依赖文件
COPY pyproject.toml uv.lock README.md ./

# 安装所有依赖（包括开发依赖）
RUN uv sync --frozen

# 复制源代码
COPY . .

CMD ["uv", "run", "uvicorn", "squant.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ============ 构建阶段 ============
FROM base AS builder

RUN pip install uv

COPY pyproject.toml uv.lock README.md ./

# 只安装生产依赖
RUN uv sync --frozen --no-dev

# ============ 生产阶段 ============
FROM python:3.12-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 安装运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash appuser

# 从构建阶段复制虚拟环境
COPY --from=builder /app/.venv /app/.venv

# 设置 PATH 和 PYTHONPATH
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src:$PYTHONPATH"

# 复制应用代码
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser alembic/ ./alembic/
COPY --chown=appuser:appuser alembic.ini ./

# 创建必要目录
RUN mkdir -p /app/strategies /app/logs && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "squant.main:app", "--host", "0.0.0.0", "--port", "8000"]
