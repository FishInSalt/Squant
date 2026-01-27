// 路由守卫

import type { Router } from 'vue-router'
import { ElMessage } from 'element-plus'

/**
 * 设置路由守卫
 */
export function setupRouterGuard(router: Router) {
  // 前置守卫
  router.beforeEach((to, _from, next) => {
    // 设置页面标题
    document.title = `${to.meta.title || '页面'} - 量化交易系统`

    // 检查是否需要登录
    if (to.meta.requiresAuth !== false) {
      // TODO: 添加登录状态检查
      // const userStore = useUserStore()
      // if (!userStore.isLoggedIn) {
      //   ElMessage.warning('请先登录')
      //   next({
      //     path: '/login',
      //     query: { redirect: to.fullPath }
      //   })
      //   return
      // }
    }

    // 必须调用 next() 以继续导航
    next()
  })

  // 后置守卫
  router.afterEach(() => {
    // 可以在这里做一些页面加载后的操作
    // 例如：关闭 loading、埋点统计等
  })

  // 错误处理
  router.onError((error) => {
    console.error('Router error:', error)
    ElMessage.error('页面加载失败')
  })
}
