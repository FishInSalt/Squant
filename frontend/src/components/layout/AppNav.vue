<template>
  <nav class="app-nav">
    <el-menu
      :default-active="activeMenu"
      mode="horizontal"
      :ellipsis="false"
      router
    >
      <el-sub-menu index="/market">
        <template #title>
          <span class="nav-title" @click="navigateTo('/market/hot')">
            <el-icon><TrendCharts /></el-icon>
            <span>行情中心</span>
          </span>
        </template>
        <el-menu-item index="/market/hot">热门行情</el-menu-item>
        <el-menu-item index="/market/watchlist">自选行情</el-menu-item>
      </el-sub-menu>

      <el-sub-menu index="/strategy">
        <template #title>
          <span class="nav-title" @click="navigateTo('/strategy/list')">
            <el-icon><Document /></el-icon>
            <span>策略中心</span>
          </span>
        </template>
        <el-menu-item index="/strategy/list">策略库</el-menu-item>
        <el-menu-item index="/strategy/upload">上传策略</el-menu-item>
      </el-sub-menu>

      <el-sub-menu index="/trading">
        <template #title>
          <span class="nav-title" @click="navigateTo('/trading/backtest')">
            <el-icon><Operation /></el-icon>
            <span>交易中心</span>
          </span>
        </template>
        <el-menu-item index="/trading/backtest">回测</el-menu-item>
        <el-menu-item index="/trading/paper">模拟交易</el-menu-item>
        <el-menu-item index="/trading/live">实盘交易</el-menu-item>
        <el-menu-item index="/trading/monitor">运行监控</el-menu-item>
        <el-menu-item index="/trading/data">数据管理</el-menu-item>
      </el-sub-menu>

      <el-sub-menu index="/order">
        <template #title>
          <span class="nav-title" @click="navigateTo('/order/open')">
            <el-icon><List /></el-icon>
            <span>订单中心</span>
          </span>
        </template>
        <el-menu-item index="/order/open">当前挂单</el-menu-item>
        <el-menu-item index="/order/history">历史订单</el-menu-item>
      </el-sub-menu>

      <el-sub-menu index="/risk">
        <template #title>
          <span class="nav-title" @click="navigateTo('/risk/rules')">
            <el-icon><Warning /></el-icon>
            <span>风控中心</span>
          </span>
        </template>
        <el-menu-item index="/risk/rules">风控规则</el-menu-item>
        <el-menu-item index="/risk/circuit-breaker">熔断控制</el-menu-item>
        <el-menu-item index="/risk/triggers">触发记录</el-menu-item>
      </el-sub-menu>

      <el-sub-menu index="/account">
        <template #title>
          <span class="nav-title" @click="navigateTo('/account/exchanges')">
            <el-icon><User /></el-icon>
            <span>账户中心</span>
          </span>
        </template>
        <el-menu-item index="/account/exchanges">交易所配置</el-menu-item>
        <el-menu-item index="/account/assets">资产概览</el-menu-item>
      </el-sub-menu>

      <el-sub-menu index="/system">
        <template #title>
          <span class="nav-title" @click="navigateTo('/system/logs')">
            <el-icon><Setting /></el-icon>
            <span>系统设置</span>
          </span>
        </template>
        <el-menu-item index="/system/logs">系统日志</el-menu-item>
      </el-sub-menu>
    </el-menu>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const activeMenu = computed(() => {
  return route.path
})

function navigateTo(path: string) {
  if (route.path !== path) {
    router.push(path)
  }
}
</script>

<style lang="scss" scoped>
.app-nav {
  background: #fff;
  border-bottom: 1px solid #e4e7ed;

  :deep(.el-menu) {
    max-width: 1400px;
    margin: 0 auto;
    border-bottom: none;
    height: 48px;

    .el-menu-item,
    .el-sub-menu__title {
      height: 48px;
      line-height: 48px;
    }

    .el-sub-menu .el-sub-menu__icon-arrow {
      display: none;
    }

    .nav-title {
      display: inline-flex;
      align-items: center;
      cursor: pointer;
    }
  }
}
</style>
