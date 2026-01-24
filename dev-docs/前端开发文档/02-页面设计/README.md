# 页面设计

## 📋 页面列表

本节详细介绍系统中各个页面的设计和实现。

### 已完成设计

| 序号 | 页面 | 路由 | 状态 | 文档 |
|------|------|------|------|------|
| 01 | 登录页面 | `/login` | ✅ 已完成 | [01-登录页面.md](./01-登录页面.md) |
| 02 | 行情看板 | `/market/dashboard` | ✅ 已完成 | [02-行情看板页面.md](./02-行情看板页面.md) |
| 03 | 策略管理 | `/strategy/list` | ✅ 已完成 | [03-策略管理页面.md](./03-策略管理页面.md) |
| 04 | 策略运行 | `/runtime/dashboard` | ✅ 已完成 | [04-策略运行页面.md](./04-策略运行页面.md) |
| 05 | 监控页面 | `/monitor/dashboard` | ✅ 已完成 | [05-监控页面.md](./05-监控页面.md) |
| 06 | 账户配置 | `/settings/account` | ✅ 已完成 | [06-账户配置页面.md](./06-账户配置页面.md) |

---

## 🎨 页面结构

```
/src/views/
├── auth/                 # 认证相关
│   └── Login.vue        # 登录页
├── market/              # 行情相关
│   ├── MarketDashboard.vue  # 行情看板
│   └── MarketDetail.vue    # 行情详情
├── strategy/            # 策略相关
│   ├── StrategyList.vue     # 策略列表
│   ├── StrategyForm.vue     # 策略表单（创建/编辑）
│   └── StrategyDetail.vue   # 策略详情
├── runtime/             # 运行相关
│   ├── RuntimeDashboard.vue # 运行概览
│   └── RuntimeDetail.vue    # 运行详情
├── monitor/             # 监控相关
│   └── MonitorDashboard.vue # 监控面板
└── settings/            # 设置相关
    ├── AccountConfig.vue   # 账户配置
    └── SystemSettings.vue  # 系统设置
```

---

## 📝 页面设计规范

### 1. 页面结构

```vue
<script setup lang="ts">
// 1. 导入
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useXxxStore } from '@/stores/xxx'
import XxxComponent from '@/components/xxx/XxxComponent.vue'

// 2. 状态定义
const router = useRouter()
const store = useXxxStore()

// 3. 数据
const data = ref([])
const loading = ref(false)

// 4. 方法
const fetchData = async () => { }

// 5. 生命周期
onMounted(() => {
  fetchData()
})
</script>

<template>
  <!-- 1. 页面容器 -->
  <div class="page-container">
    <!-- 2. 页面头部 -->
    <div class="page-header">
      <h2 class="page-title">页面标题</h2>
      <div class="page-actions">
        <!-- 操作按钮 -->
      </div>
    </div>

    <!-- 3. 页面内容 -->
    <div class="page-content">
      <!-- 具体内容 -->
    </div>
  </div>
</template>

<style scoped lang="scss">
.page-container {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-title {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
}
</style>
```

### 2. 加载状态

使用 `ElLoading` 或自定义加载状态：

```vue
<template>
  <div v-loading="loading" class="page-container">
    <!-- 内容 -->
  </div>
</template>
```

### 3. 空状态

使用 `ElEmpty` 展示空状态：

```vue
<template>
  <div class="page-container">
    <el-empty v-if="data.length === 0" description="暂无数据" />
    <div v-else>
      <!-- 数据列表 -->
    </div>
  </div>
</template>
```

### 4. 错误处理

```vue
<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

const error = ref<Error | null>(null)

const fetchData = async () => {
  try {
    error.value = null
    // 请求逻辑
  } catch (err) {
    error.value = err as Error
    ElMessage.error(error.value.message)
  }
}
</script>
```

---

## 🔗 相关文档

- [项目结构](../01-架构设计/01-项目结构.md)
- [路由设计](../01-架构设计/03-路由设计.md)
- [组件库设计](../01-架构设计/04-组件库设计.md)
- [状态管理设计](../01-架构设计/02-状态管理设计.md)

---

**最后更新**: 2026-01-24
**版本**: v1.0
