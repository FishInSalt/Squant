<script setup lang="ts">
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUiStore } from '@/stores/ui'

const router = useRouter()
const route = useRoute()
const uiStore = useUiStore()

const collapsed = computed(() => uiStore.sidebarCollapsed)

// 菜单数据
const menuData = [
  {
    path: '/market',
    icon: 'TrendCharts',
    title: '行情看板',
    children: [
      { path: '/market/dashboard', title: '行情看板' }
    ]
  },
  {
    path: '/strategy',
    icon: 'Document',
    title: '策略管理',
    children: [
      { path: '/strategy/list', title: '策略列表' }
    ]
  },
  {
    path: '/runtime',
    icon: 'VideoPlay',
    title: '策略运行',
    children: [
      { path: '/runtime/dashboard', title: '运行概览' }
    ]
  },
  {
    path: '/monitor',
    icon: 'Monitor',
    title: '监控中心',
    children: [
      { path: '/monitor/dashboard', title: '监控面板' }
    ]
  },
  {
    path: '/settings',
    icon: 'Setting',
    title: '设置',
    children: [
      { path: '/settings/account', title: '账户配置' }
    ]
  }
]

const activeMenu = computed(() => route.path)

const handleMenuSelect = (index: string) => {
  router.push(index)
}

const toggleSidebar = () => {
  uiStore.toggleSidebar()
}
</script>

<template>
  <aside class="sidebar" :class="{ collapsed }">
    <div class="logo">
      <h2>{{ collapsed ? '量化' : '量化交易系统' }}</h2>
    </div>
    <el-menu
      :default-active="activeMenu"
      :collapse="collapsed"
      @select="handleMenuSelect"
    >
      <template v-for="menu in menuData" :key="menu.path">
        <el-sub-menu v-if="menu.children?.length" :index="menu.path">
          <template #title>
            <el-icon><component :is="menu.icon" /></el-icon>
            <span>{{ menu.title }}</span>
          </template>
          <el-menu-item
            v-for="item in menu.children"
            :key="item.path"
            :index="item.path"
          >
            {{ item.title }}
          </el-menu-item>
        </el-sub-menu>
        <el-menu-item v-else :index="menu.path">
          <el-icon><component :is="menu.icon" /></el-icon>
          <span>{{ menu.title }}</span>
        </el-menu-item>
      </template>
    </el-menu>
    <div class="collapse-btn" @click="toggleSidebar">
      <el-icon>
        <component :is="collapsed ? 'DArrowRight' : 'DArrowLeft'" />
      </el-icon>
    </div>
  </aside>
</template>

<style scoped lang="scss">
.sidebar {
  width: 240px;
  height: 100vh;
  background: #304156;
  color: #fff;
  display: flex;
  flex-direction: column;
  transition: width 0.3s;
  position: relative;

  &.collapsed {
    width: 64px;
  }

  .logo {
    height: 60px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #2b3a4d;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);

    h2 {
      margin: 0;
      font-size: 18px;
      font-weight: 600;
      white-space: nowrap;
      transition: font-size 0.3s;
    }

    &:hover {
      background: #263445;
    }
  }

  .collapse-btn {
    height: 48px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    background: rgba(0, 0, 0, 0.2);
    transition: background 0.3s;

    &:hover {
      background: rgba(0, 0, 0, 0.3);
    }
  }

  :deep(.el-menu) {
    border-right: none;
    background: #304156;
    flex: 1;
  }

  :deep(.el-menu-item),
  :deep(.el-sub-menu__title) {
    color: #bfcbd9;

    &:hover {
      background: #263445;
    }
  }

  :deep(.el-menu-item.is-active) {
    color: #409eff;
    background: #263445;
  }
}
</style>
