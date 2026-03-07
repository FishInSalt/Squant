<template>
  <el-dialog
    v-model="visible"
    :title="title"
    :width="width"
    :close-on-click-modal="!loading"
    :close-on-press-escape="!loading"
    :show-close="!loading"
    @close="handleClose"
  >
    <div class="confirm-content">
      <el-icon v-if="icon" :class="['confirm-icon', type]" :size="48">
        <component :is="iconComponent" />
      </el-icon>
      <div class="confirm-message">
        <slot>{{ message }}</slot>
      </div>
    </div>

    <template #footer>
      <el-button @click="handleCancel" :disabled="loading">
        {{ cancelText }}
      </el-button>
      <el-button
        :type="confirmType"
        @click="handleConfirm"
        :loading="loading"
      >
        {{ confirmText }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { WarningFilled, CircleCheckFilled, CircleCloseFilled, InfoFilled } from '@element-plus/icons-vue'

interface Props {
  modelValue: boolean
  title?: string
  message?: string
  type?: 'warning' | 'success' | 'danger' | 'info'
  icon?: boolean
  width?: string
  confirmText?: string
  cancelText?: string
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  title: '确认',
  message: '',
  type: 'warning',
  icon: true,
  width: '400px',
  confirmText: '确定',
  cancelText: '取消',
  loading: false,
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'confirm'): void
  (e: 'cancel'): void
}>()

const visible = ref(props.modelValue)

watch(() => props.modelValue, (val) => {
  visible.value = val
})

watch(visible, (val) => {
  emit('update:modelValue', val)
})

const iconComponent = computed(() => {
  switch (props.type) {
    case 'success':
      return CircleCheckFilled
    case 'danger':
      return CircleCloseFilled
    case 'info':
      return InfoFilled
    default:
      return WarningFilled
  }
})

const confirmType = computed(() => {
  return props.type === 'danger' ? 'danger' : 'primary'
})

function handleConfirm() {
  emit('confirm')
}

function handleCancel() {
  visible.value = false
  emit('cancel')
}

function handleClose() {
  if (!props.loading) {
    emit('cancel')
  }
}
</script>

<style lang="scss" scoped>
.confirm-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px 0;
}

.confirm-icon {
  margin-bottom: 16px;

  &.warning {
    color: #ff9800;
  }

  &.success {
    color: #4caf50;
  }

  &.danger {
    color: #ff4d4f;
  }

  &.info {
    color: #909399;
  }
}

.confirm-message {
  text-align: center;
  font-size: 14px;
  color: #606266;
  line-height: 1.6;
}
</style>
