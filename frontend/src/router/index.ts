import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/market/hot',
  },
  // 行情中心
  {
    path: '/market',
    redirect: '/market/hot',
    children: [
      {
        path: 'hot',
        name: 'HotMarket',
        component: () => import('@/views/market/HotMarket.vue'),
        meta: { title: '热门行情' },
      },
      {
        path: 'watchlist',
        name: 'Watchlist',
        component: () => import('@/views/market/Watchlist.vue'),
        meta: { title: '自选行情' },
      },
      {
        path: 'chart/:exchange/:symbol',
        name: 'ChartDetail',
        component: () => import('@/views/market/ChartDetail.vue'),
        meta: { title: 'K线详情' },
        props: true,
      },
    ],
  },
  // 策略中心
  {
    path: '/strategy',
    redirect: '/strategy/list',
    children: [
      {
        path: 'list',
        name: 'StrategyList',
        component: () => import('@/views/strategy/StrategyList.vue'),
        meta: { title: '策略库' },
      },
      {
        path: 'upload',
        name: 'StrategyUpload',
        component: () => import('@/views/strategy/StrategyUpload.vue'),
        meta: { title: '上传策略' },
      },
      {
        path: ':id',
        name: 'StrategyDetail',
        component: () => import('@/views/strategy/StrategyDetail.vue'),
        meta: { title: '策略详情' },
        props: true,
      },
    ],
  },
  // 交易中心
  {
    path: '/trading',
    redirect: '/trading/backtest',
    children: [
      {
        path: 'backtest',
        name: 'Backtest',
        component: () => import('@/views/trading/Backtest.vue'),
        meta: { title: '回测' },
      },
      {
        path: 'backtest/:id/result',
        name: 'BacktestResult',
        component: () => import('@/views/trading/BacktestResult.vue'),
        meta: { title: '回测结果' },
        props: true,
      },
      {
        path: 'paper',
        name: 'PaperTrading',
        component: () => import('@/views/trading/PaperTrading.vue'),
        meta: { title: '模拟交易' },
      },
      {
        path: 'live',
        name: 'LiveTrading',
        component: () => import('@/views/trading/LiveTrading.vue'),
        meta: { title: '实盘交易' },
      },
      {
        path: 'monitor',
        name: 'Monitor',
        component: () => import('@/views/trading/Monitor.vue'),
        meta: { title: '运行监控' },
      },
      {
        path: 'monitor/:type/:id',
        name: 'SessionMonitor',
        component: () => import('@/views/trading/Monitor.vue'),
        meta: { title: '会话监控' },
        props: true,
      },
    ],
  },
  // 订单中心
  {
    path: '/order',
    redirect: '/order/open',
    children: [
      {
        path: 'open',
        name: 'OpenOrders',
        component: () => import('@/views/order/OpenOrders.vue'),
        meta: { title: '当前挂单' },
      },
      {
        path: 'history',
        name: 'OrderHistory',
        component: () => import('@/views/order/OrderHistory.vue'),
        meta: { title: '历史订单' },
      },
    ],
  },
  // 风控中心
  {
    path: '/risk',
    redirect: '/risk/rules',
    children: [
      {
        path: 'rules',
        name: 'RiskRules',
        component: () => import('@/views/risk/RiskRules.vue'),
        meta: { title: '风控规则' },
      },
      {
        path: 'circuit-breaker',
        name: 'CircuitBreaker',
        component: () => import('@/views/risk/CircuitBreaker.vue'),
        meta: { title: '熔断控制' },
      },
      {
        path: 'triggers',
        name: 'TriggerRecords',
        component: () => import('@/views/risk/TriggerRecords.vue'),
        meta: { title: '触发记录' },
      },
    ],
  },
  // 账户中心
  {
    path: '/account',
    redirect: '/account/exchanges',
    children: [
      {
        path: 'exchanges',
        name: 'ExchangeConfig',
        component: () => import('@/views/account/ExchangeConfig.vue'),
        meta: { title: '交易所配置' },
      },
      {
        path: 'assets',
        name: 'AssetOverview',
        component: () => import('@/views/account/AssetOverview.vue'),
        meta: { title: '资产概览' },
      },
    ],
  },
  // 系统设置
  {
    path: '/system',
    redirect: '/system/data',
    children: [
      {
        path: 'data',
        name: 'DataManagement',
        component: () => import('@/views/system/DataManagement.vue'),
        meta: { title: '数据管理' },
      },
      {
        path: 'logs',
        name: 'SystemLogs',
        component: () => import('@/views/system/SystemLogs.vue'),
        meta: { title: '系统日志' },
      },
    ],
  },
  // 404
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/NotFound.vue'),
    meta: { title: '页面不存在' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫 - 设置页面标题
router.beforeEach((to, _from, next) => {
  const title = to.meta.title as string
  document.title = title ? `${title} - Squant` : 'Squant'
  next()
})

export default router
