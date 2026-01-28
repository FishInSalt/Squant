# ============ 构建阶段 ============
FROM node:20-alpine AS builder

WORKDIR /app

# 安装依赖
COPY package.json package-lock.json ./
RUN npm ci

# 复制源代码并构建
COPY . .
RUN npm run build

# ============ 生产阶段 ============
FROM nginx:alpine AS production

# 复制构建产物
COPY --from=builder /app/dist /usr/share/nginx/html

# 复制 nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost/ || exit 1

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
