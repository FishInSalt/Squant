import { mount } from '@vue/test-utils'
import ConfirmDialog from './ConfirmDialog.vue'

// Stub el-dialog to render content inline (avoids Teleport issues in tests)
const ElDialogStub = {
  template: `
    <div class="el-dialog" v-if="modelValue">
      <div class="el-dialog__header"><slot name="title">{{ title }}</slot></div>
      <div class="el-dialog__body"><slot /></div>
      <div class="el-dialog__footer"><slot name="footer" /></div>
    </div>
  `,
  props: ['modelValue', 'title', 'width', 'closeOnClickModal', 'closeOnPressEscape', 'showClose'],
  emits: ['update:modelValue', 'close'],
}

function mountDialog(props: Record<string, unknown> = {}) {
  return mount(ConfirmDialog, {
    props: { modelValue: true, ...props },
    global: {
      stubs: { ElDialog: ElDialogStub },
    },
  })
}

describe('ConfirmDialog', () => {
  it('renders title and message', () => {
    const wrapper = mountDialog({ title: '删除确认', message: '确定删除？' })
    expect(wrapper.text()).toContain('删除确认')
    expect(wrapper.text()).toContain('确定删除？')
  })

  it('uses default title and button text', () => {
    const wrapper = mountDialog()
    expect(wrapper.text()).toContain('确认')
    expect(wrapper.text()).toContain('确定')
    expect(wrapper.text()).toContain('取消')
  })

  it('emits confirm when confirm button clicked', async () => {
    const wrapper = mountDialog({ confirmText: '确定' })
    const buttons = wrapper.findAll('button')
    const confirmBtn = buttons.find((b) => b.text().includes('确定'))
    expect(confirmBtn).toBeDefined()
    await confirmBtn!.trigger('click')
    expect(wrapper.emitted('confirm')).toHaveLength(1)
  })

  it('emits cancel when cancel button clicked', async () => {
    const wrapper = mountDialog()
    const buttons = wrapper.findAll('button')
    const cancelBtn = buttons.find((b) => b.text().includes('取消'))
    expect(cancelBtn).toBeDefined()
    await cancelBtn!.trigger('click')
    expect(wrapper.emitted('cancel')).toHaveLength(1)
  })

  it('disables cancel button when loading', () => {
    const wrapper = mountDialog({ loading: true })
    const buttons = wrapper.findAll('button')
    const cancelBtn = buttons.find((b) => b.text().includes('取消'))
    expect(cancelBtn).toBeDefined()
    expect(cancelBtn!.attributes('disabled')).toBeDefined()
  })

  it('uses danger button type for danger dialog type', () => {
    const wrapper = mountDialog({ type: 'danger', confirmText: '删除' })
    const buttons = wrapper.findAll('button')
    const confirmBtn = buttons.find((b) => b.text().includes('删除'))
    expect(confirmBtn).toBeDefined()
    expect(confirmBtn!.classes().some((c) => c.includes('danger'))).toBe(true)
  })
})
