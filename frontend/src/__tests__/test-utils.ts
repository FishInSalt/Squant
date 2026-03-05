import { mount, type ComponentMountingOptions } from '@vue/test-utils'
import { createTestingPinia, type TestingOptions } from '@pinia/testing'
import { createRouter, createMemoryHistory, type RouteRecordRaw } from 'vue-router'
import { type Component } from 'vue'

interface MountViewOptions {
  props?: Record<string, unknown>
  stubs?: Record<string, boolean | Component>
  initialState?: TestingOptions['initialState']
  routes?: RouteRecordRaw[]
  initialRoute?: string
  slots?: ComponentMountingOptions<unknown>['slots']
}

/**
 * Mount a View or Component with Pinia + Router pre-configured.
 * Element Plus heavy components and chart components are stubbed by default.
 */
export function mountView<T extends Component>(
  component: T,
  options: MountViewOptions = {}
) {
  const pinia = createTestingPinia({
    createSpy: vi.fn,
    initialState: options.initialState,
  })

  const routes: RouteRecordRaw[] = options.routes ?? [
    { path: '/:pathMatch(.*)*', name: 'Catchall', component: { template: '<div />' } },
  ]

  const router = createRouter({
    history: createMemoryHistory(),
    routes,
  })

  if (options.initialRoute) {
    router.push(options.initialRoute)
  }

  return mount(component, {
    global: {
      plugins: [pinia, router],
      stubs: {
        // Chart components (Canvas not supported in happy-dom)
        EquityCurve: { template: '<div class="equity-curve-stub" />' },
        KLineChart: { template: '<div class="kline-chart-stub" />' },
        TradingKLineChart: { template: '<div class="trading-kline-chart-stub" />' },
        PieChart: { template: '<div class="pie-chart-stub" />' },
        // Heavy Element Plus components
        ElDatePicker: { template: '<div class="el-date-picker-stub" />' },
        // Custom stubs
        ...options.stubs,
      },
    },
    props: options.props,
    slots: options.slots,
  } as ComponentMountingOptions<any>)
}
