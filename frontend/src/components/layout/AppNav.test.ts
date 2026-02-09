import { mountView } from '@/__tests__/test-utils'
import AppNav from './AppNav.vue'

describe('AppNav', () => {
  it('renders all main navigation sections', () => {
    const wrapper = mountView(AppNav)
    const text = wrapper.text()
    expect(text).toContain('行情中心')
    expect(text).toContain('策略中心')
    expect(text).toContain('交易中心')
    expect(text).toContain('订单中心')
    expect(text).toContain('风控中心')
    expect(text).toContain('账户中心')
    expect(text).toContain('系统设置')
  })

  it('renders el-menu component', () => {
    const wrapper = mountView(AppNav)
    expect(wrapper.find('.el-menu').exists()).toBe(true)
  })

  it('renders sub-menus for each section', () => {
    const wrapper = mountView(AppNav)
    const subMenus = wrapper.findAll('.el-sub-menu')
    expect(subMenus.length).toBeGreaterThanOrEqual(7)
  })

  it('uses horizontal mode', () => {
    const wrapper = mountView(AppNav)
    const menu = wrapper.find('.el-menu')
    expect(menu.classes()).toContain('el-menu--horizontal')
  })
})
