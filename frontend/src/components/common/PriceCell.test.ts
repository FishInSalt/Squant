import { mount } from '@vue/test-utils'
import PriceCell from './PriceCell.vue'

describe('PriceCell', () => {
  describe('CSS classes', () => {
    it('applies price-up when change > 0', () => {
      const wrapper = mount(PriceCell, { props: { value: 100, change: 5 } })
      expect(wrapper.find('.price-up').exists()).toBe(true)
    })

    it('applies price-down when change < 0', () => {
      const wrapper = mount(PriceCell, { props: { value: 100, change: -3 } })
      expect(wrapper.find('.price-down').exists()).toBe(true)
    })

    it('applies price-neutral when change is 0', () => {
      const wrapper = mount(PriceCell, { props: { value: 100, change: 0 } })
      expect(wrapper.find('.price-neutral').exists()).toBe(true)
    })

    it('applies price-neutral when neutral prop is true', () => {
      const wrapper = mount(PriceCell, { props: { value: 100, change: 5, neutral: true } })
      expect(wrapper.find('.price-neutral').exists()).toBe(true)
      expect(wrapper.find('.price-up').exists()).toBe(false)
    })
  })

  describe('display value', () => {
    it('formats with custom decimals', () => {
      const wrapper = mount(PriceCell, { props: { value: 123.456789, decimals: 2 } })
      expect(wrapper.text()).toContain('123.46')
    })

    it('uses formatPrice when no decimals specified', () => {
      const wrapper = mount(PriceCell, { props: { value: 50000 } })
      // formatPrice uses toLocaleString, check number is present
      expect(wrapper.text()).toContain('50')
    })

    it('shows dash for null-like value', () => {
      const wrapper = mount(PriceCell, { props: { value: null as any } })
      expect(wrapper.text()).toContain('-')
    })
  })

  describe('sign display', () => {
    it('shows + sign when showSign and change > 0', () => {
      const wrapper = mount(PriceCell, { props: { value: 100, change: 5, showSign: true } })
      expect(wrapper.text()).toContain('+')
    })

    it('does not show + when showSign is false', () => {
      const wrapper = mount(PriceCell, { props: { value: 100, change: 5, showSign: false } })
      // The "+" sign span should not be rendered
      const text = wrapper.text()
      // Value starts directly without +
      expect(text.startsWith('+')).toBe(false)
    })

    it('does not show + when change is 0', () => {
      const wrapper = mount(PriceCell, { props: { value: 100, change: 0, showSign: true } })
      expect(wrapper.text()).not.toMatch(/^\+/)
    })
  })

  describe('percent display', () => {
    it('shows percent when showPercent and percent provided', () => {
      const wrapper = mount(PriceCell, {
        props: { value: 100, percent: 5.23, showPercent: true },
      })
      expect(wrapper.find('.percent').exists()).toBe(true)
      expect(wrapper.text()).toContain('5.23')
    })

    it('hides percent when showPercent is false', () => {
      const wrapper = mount(PriceCell, {
        props: { value: 100, percent: 5.23, showPercent: false },
      })
      expect(wrapper.find('.percent').exists()).toBe(false)
    })

    it('hides percent when percent is undefined', () => {
      const wrapper = mount(PriceCell, {
        props: { value: 100, showPercent: true },
      })
      expect(wrapper.find('.percent').exists()).toBe(false)
    })
  })

  describe('suffix', () => {
    it('shows suffix text', () => {
      const wrapper = mount(PriceCell, { props: { value: 100, suffix: ' USDT' } })
      expect(wrapper.text()).toContain('USDT')
    })
  })
})
