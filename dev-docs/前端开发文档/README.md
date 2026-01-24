# 量化交易系统 - 前端开发文档

## 📋 文档说明

本文档为量化交易系统前端开发的完整指南，基于 **Vue 3 + TypeScript + Element Plus + Pinia** 技术栈。

## 🎯 技术栈

- **框架**: Vue 3 (Composition API)
- **语言**: TypeScript 5.0+
- **构建工具**: Vite 5.0+
- **UI组件库**: Element Plus
- **状态管理**: Pinia
- **路由**: Vue Router 4
- **图表库**:
  - K线图: TradingView Lightweight Charts
  - 其他图表: ECharts 5
- **HTTP客户端**: Axios
- **代码规范**: ESLint + Prettier

## 📚 文档目录

### 01-架构设计
- [00-技术栈选型.md](./01-架构设计/00-技术栈选型.md) - 技术选型说明与对比
- [01-项目结构.md](./01-架构设计/01-项目结构.md) - 项目目录结构设计
- [02-状态管理设计.md](./01-架构设计/02-状态管理设计.md) - Pinia 状态管理架构
- [03-路由设计.md](./01-架构设计/03-路由设计.md) - 路由配置与权限控制
- [04-组件库设计.md](./01-架构设计/04-组件库设计.md) - 组件库封装规范

### 02-页面设计
- [README.md](./02-页面设计/README.md) - 页面设计总览
- [01-登录页面.md](./02-页面设计/01-登录页面.md) - 登录功能
- [02-行情看板页面.md](./02-页面设计/02-行情看板页面.md) - 实时行情展示
- [03-策略管理页面.md](./02-页面设计/03-策略管理页面.md) - 策略CRUD管理
- [04-策略运行页面.md](./02-页面设计/04-策略运行页面.md) - 策略运行与监控
- [05-监控页面.md](./02-页面设计/05-监控页面.md) - 系统监控与告警
- [06-账户配置页面.md](./02-页面设计/06-账户配置页面.md) - 交易所账户配置

## 🚀 快速开始

### 1. 安装依赖
```bash
npm install
# 或
pnpm install
```

### 2. 启动开发服务器
```bash
npm run dev
# 或
pnpm dev
```

### 3. 构建生产版本
```bash
npm run build
# 或
pnpm build
```

## 📦 项目特性

- ✅ TypeScript 类型安全
- ✅ Composition API
- ✅ 响应式设计
- ✅ WebSocket 实时数据
- ✅ K线图专业展示
- ✅ 策略配置与运行监控
- ✅ 权限管理
- ✅ 主题定制

## 🔧 开发规范

### 命名规范
- 组件文件: PascalCase (如 `UserProfile.vue`)
- 工具函数: camelCase (如 `formatDate.ts`)
- 常量: UPPER_SNAKE_CASE (如 `API_BASE_URL`)

### 代码风格
- 使用 2 空格缩进
- 单引号字符串
- 尾随逗号
- 分号可选

### 提交规范
- feat: 新功能
- fix: 修复bug
- docs: 文档更新
- style: 代码格式调整
- refactor: 重构
- test: 测试相关
- chore: 构建/工具链相关

## 📖 相关文档

- [系统架构设计](../design/01-系统架构设计/)
- [API接口设计](../design/02-API接口详细设计/)
- [需求文档](../requirements/)

## 💬 技术支持

开发过程中遇到问题，请参考：
- [Vue 3 官方文档](https://vuejs.org/)
- [Element Plus 文档](https://element-plus.org/)
- [Pinia 文档](https://pinia.vuejs.org/)
- [TradingView Lightweight Charts](https://www.tradingview.com/lightweight-charts/)
- [ECharts 文档](https://echarts.apache.org/zh/)

---

**最后更新**: 2026-01-24
**文档版本**: v1.0 (Vue 3)
