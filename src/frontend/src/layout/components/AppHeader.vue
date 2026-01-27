<script setup lang="ts">
import { computed } from 'vue'
import { useUiStore } from '@/stores/ui'

const uiStore = useUiStore()

const isDark = computed(() => uiStore.isDark)

const handleLogout = () => {
  // TODO: 实现登出逻辑
  console.log('Logout')
}
</script>

<template>
  <header class="app-header">
    <div class="header-left">
      <el-button
        text
        :icon="isDark ? 'Sunny' : 'Moon'"
        @click="uiStore.toggleTheme"
      />
    </div>
    
    <div class="header-center">
      <h1 class="app-title">量化交易系统</h1>
    </div>
    
    <div class="header-right">
      <el-button type="danger" size="small" @click="handleLogout">
        退出
      </el-button>
    </div>
  </header>
</template>

<style scoped lang="scss">
.app-header {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);

  .header-left {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .header-center {
    flex: 1;
    text-align: center;

    .app-title {
      margin: 0;
      font-size: 18px;
      font-weight: 600;
      color: #303133;
    }
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 12px;
  }
}
</style>
