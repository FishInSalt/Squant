// 路由定义

import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  // ========== 公共路由 ==========
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/layout/BlankLayout.vue'),
    children: [
      {
        path: '',
        name: 'LoginPage',
        component: () => import('@/views/auth/Login.vue')
      }
    ],
    meta: {
      title: '登录',
      requiresAuth: false
    }
  },

  // ========== 主布局（需要登录）==========
  {
    path: '/',
    component: () => import('@/layout/DefaultLayout.vue'),
    redirect: '/market',
    meta: {
      requiresAuth: true
    },
    children: [
      // 市场模块
      {
        path: 'market',
        name: 'Market',
        redirect: '/market/dashboard',
        meta: {
          title: '行情',
          icon: 'TrendCharts'
        },
        children: [
          {
            path: 'dashboard',
            name: 'MarketDashboard',
            component: () => import('@/views/market/MarketDashboard.vue'),
            meta: {
              title: '行情看板',
              icon: 'TrendCharts'
            }
          }
        ]
      },

      // 策略模块
      {
        path: 'strategy',
        name: 'Strategy',
        redirect: '/strategy/list',
        meta: {
          title: '策略管理',
          icon: 'Document'
        },
        children: [
          {
            path: 'list',
            name: 'StrategyList',
            component: () => import('@/views/strategy/StrategyList.vue'),
            meta: {
              title: '策略列表',
              icon: 'List'
            }
          }
        ]
      },

      // 运行模块
      {
        path: 'runtime',
        name: 'Runtime',
        redirect: '/runtime/dashboard',
        meta: {
          title: '策略运行',
          icon: 'VideoPlay'
        },
        children: [
          {
            path: 'dashboard',
            name: 'RuntimeDashboard',
            component: () => import('@/views/runtime/RuntimeDashboard.vue'),
            meta: {
              title: '运行概览',
              icon: 'DataBoard'
            }
          }
        ]
      },

      // 监控模块
      {
        path: 'monitor',
        name: 'Monitor',
        redirect: '/monitor/dashboard',
        meta: {
          title: '监控中心',
          icon: 'Monitor'
        },
        children: [
          {
            path: 'dashboard',
            name: 'MonitorDashboard',
            component: () => import('@/views/monitor/MonitorDashboard.vue'),
            meta: {
              title: '监控面板',
              icon: 'DataBoard'
            }
          }
        ]
      },

      // 设置模块
      {
        path: 'settings',
        name: 'Settings',
        redirect: '/settings/account',
        meta: {
          title: '设置',
          icon: 'Setting'
        },
        children: [
          {
            path: 'account',
            name: 'AccountConfig',
            component: () => import('@/views/settings/AccountConfig.vue'),
            meta: {
              title: '账户配置',
              icon: 'User'
            }
          }
        ]
      }
    ]
  },

  // ========== 404 ==========
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/error/NotFound.vue'),
    meta: {
      title: '404'
    }
  }
]

export default routes
