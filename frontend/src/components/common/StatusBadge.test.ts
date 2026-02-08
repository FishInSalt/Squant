import { mount } from '@vue/test-utils'
import StatusBadge from './StatusBadge.vue'

describe('StatusBadge', () => {
  describe('session statuses', () => {
    it.each([
      ['running', 'success', '运行中'],
      ['pending', 'info', '待启动'],
      ['completed', 'primary', '已完成'],
      ['failed', 'danger', '已失败'],
      ['stopped', 'warning', '已停止'],
    ])('renders %s as %s tag with text %s', (status, expectedType, expectedText) => {
      const wrapper = mount(StatusBadge, { props: { status: status as any } })
      expect(wrapper.text()).toBe(expectedText)
      expect(wrapper.find('.el-tag').classes()).toContain(`el-tag--${expectedType}`)
    })
  })

  describe('order statuses', () => {
    it.each([
      ['open', 'primary', '挂单中'],
      ['filled', 'success', '已成交'],
      ['cancelled', 'info', '已取消'],
      ['rejected', 'danger', '已拒绝'],
    ])('renders %s as %s tag with text %s', (status, expectedType, expectedText) => {
      const wrapper = mount(StatusBadge, { props: { status: status as any } })
      expect(wrapper.text()).toBe(expectedText)
      expect(wrapper.find('.el-tag').classes()).toContain(`el-tag--${expectedType}`)
    })
  })

  describe('connection statuses', () => {
    it('renders connected as success', () => {
      const wrapper = mount(StatusBadge, { props: { status: 'connected' as any } })
      expect(wrapper.text()).toBe('已连接')
    })

    it('renders error as danger', () => {
      const wrapper = mount(StatusBadge, { props: { status: 'error' as any } })
      expect(wrapper.text()).toBe('错误')
    })
  })

  describe('unknown status fallback', () => {
    it('falls back to info type and raw status text', () => {
      const wrapper = mount(StatusBadge, { props: { status: 'unknown_status' as any } })
      expect(wrapper.text()).toBe('unknown_status')
      expect(wrapper.find('.el-tag').classes()).toContain('el-tag--info')
    })
  })

  describe('props', () => {
    it('applies size prop', () => {
      const wrapper = mount(StatusBadge, { props: { status: 'running' as any, size: 'large' } })
      expect(wrapper.find('.el-tag').classes()).toContain('el-tag--large')
    })

    it('applies effect prop', () => {
      const wrapper = mount(StatusBadge, { props: { status: 'running' as any, effect: 'dark' } })
      expect(wrapper.find('.el-tag').classes()).toContain('el-tag--dark')
    })

    it('defaults to small size and light effect', () => {
      const wrapper = mount(StatusBadge, { props: { status: 'running' as any } })
      expect(wrapper.find('.el-tag').classes()).toContain('el-tag--small')
      expect(wrapper.find('.el-tag').classes()).toContain('el-tag--light')
    })
  })
})
