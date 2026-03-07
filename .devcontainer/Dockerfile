# Dev Container Dockerfile for Squant
# Base: Microsoft Python 3.12 devcontainer image (Debian Bookworm)
FROM mcr.microsoft.com/devcontainers/python:3.12-bookworm

# Install Node.js 20
ARG NODE_VERSION="20"
RUN su vscode -c "umask 0002 && . /usr/local/share/nvm/nvm.sh && nvm install ${NODE_VERSION} 2>&1"

# Install uv (Python package manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Install pnpm and configure store path (avoid writing to project directory)
RUN npm install -g pnpm \
    && mkdir -p /home/vscode/.local/share/pnpm/store \
    && chown -R vscode:vscode /home/vscode/.local/share/pnpm
ENV PNPM_HOME=/home/vscode/.local/share/pnpm
ENV PNPM_STORE_DIR=/home/vscode/.local/share/pnpm/store

# Install PostgreSQL client and Redis CLI
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends \
        postgresql-client \
        redis-tools \
    && apt-get clean -y \
    && rm -rf /var/lib/apt/lists/*

# Set uv environment variables
ENV UV_LINK_MODE=copy
ENV UV_COMPILE_BYTECODE=1

# Configure uv to use project virtual environment
ENV UV_PROJECT_ENVIRONMENT=/workspaces/Squant/.venv

WORKDIR /workspaces/Squant
