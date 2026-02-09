import { mountView } from '@/__tests__/test-utils'
import AppHeader from './AppHeader.vue'

describe('AppHeader', () => {
  it('renders logo text', () => {
    const wrapper = mountView(AppHeader)
    expect(wrapper.text()).toContain('Squant')
  })

  it('renders logo icon S', () => {
    const wrapper = mountView(AppHeader)
    expect(wrapper.find('.logo-icon').text()).toBe('S')
  })

  it('shows search input', () => {
    const wrapper = mountView(AppHeader)
    expect(wrapper.find('.search-input').exists()).toBe(true)
  })

  it('shows connection status indicator', () => {
    const wrapper = mountView(AppHeader)
    expect(wrapper.find('.connection-status').exists()).toBe(true)
  })

  it('shows connected class when websocket is connected', () => {
    const wrapper = mountView(AppHeader, {
      initialState: { websocket: { connected: true } },
    })
    expect(wrapper.find('.connection-status.connected').exists()).toBe(true)
  })

  it('does not show connected class when disconnected', () => {
    const wrapper = mountView(AppHeader, {
      initialState: { websocket: { connected: false } },
    })
    expect(wrapper.find('.connection-status.connected').exists()).toBe(false)
  })
})
