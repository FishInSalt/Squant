<template>
  <div class="strategy-detail" v-loading="loading">
    <div class="page-header" v-if="strategy">
      <div class="header-left">
        <el-button icon="ArrowLeft" @click="goBack">返回</el-button>
        <div class="strategy-info">
          <h1 class="strategy-name">{{ strategy.name }}</h1>
          <StatusBadge :status="strategy.status === 'active' ? 'active' : 'archived'" />
          <el-tag size="small" type="info">v{{ strategy.version }}</el-tag>
        </div>
      </div>
      <div class="header-right">
        <template v-if="!isEditing">
          <el-button v-if="strategy.status === 'active'" @click="enterEditMode">
            <el-icon><Edit /></el-icon>
            编辑
          </el-button>
          <el-button type="primary" @click="goToBacktest">
            <el-icon><Histogram /></el-icon>
            回测
          </el-button>
          <el-button @click="goToPaper">
            <el-icon><Monitor /></el-icon>
            模拟交易
          </el-button>
          <el-button @click="goToLive">
            <el-icon><Connection /></el-icon>
            实盘交易
          </el-button>
          <el-button type="danger" @click="handleDelete">
            <el-icon><Delete /></el-icon>
            删除
          </el-button>
        </template>
        <template v-else>
          <el-button type="primary" :loading="saving" @click="saveChanges">
            <el-icon><Check /></el-icon>
            保存
          </el-button>
          <el-button @click="cancelEdit">
            取消
          </el-button>
        </template>
      </div>
    </div>

    <div class="content-grid" v-if="strategy">
      <div class="main-content">
        <div class="card info-card">
          <div class="card-header">
            <h3 class="card-title">基本信息</h3>
          </div>
          <div class="info-grid">
            <div class="info-item">
              <span class="label">策略名称</span>
              <span class="value">{{ strategy.name }}</span>
            </div>
            <div class="info-item">
              <span class="label">版本</span>
              <span class="value">v{{ strategy.version }}</span>
            </div>
            <div class="info-item">
              <span class="label">创建时间</span>
              <span class="value">{{ formatDateTime(strategy.created_at) }}</span>
            </div>
            <div class="info-item">
              <span class="label">更新时间</span>
              <span class="value">{{ formatDateTime(strategy.updated_at) }}</span>
            </div>
          </div>
          <div class="description">
            <h4>描述</h4>
            <template v-if="isEditing">
              <el-input
                v-model="editDescription"
                type="textarea"
                :rows="3"
                placeholder="添加策略描述..."
                maxlength="1000"
                show-word-limit
              />
            </template>
            <template v-else>
              <p v-if="strategy.description">{{ strategy.description }}</p>
              <p v-else class="empty-description">暂无描述</p>
            </template>
          </div>
        </div>

        <div class="card code-card">
          <div class="card-header">
            <h3 class="card-title">策略代码</h3>
            <span v-if="isEditing && codeChanged" class="unsaved-hint">未保存的更改</span>
          </div>
          <div class="editor-container" ref="editorContainerRef"></div>
        </div>
      </div>

      <div class="side-content">
        <div class="card params-card">
          <div class="card-header">
            <h3 class="card-title">参数配置</h3>
          </div>
          <div v-if="hasParams" class="params-list">
            <div
              v-for="(param, key) in strategy.params_schema.properties"
              :key="key"
              class="param-item"
            >
              <div class="param-header">
                <span class="param-name">{{ param.title || key }}</span>
                <el-tag size="small" type="info">{{ param.type }}</el-tag>
              </div>
              <p class="param-description" v-if="param.description">
                {{ param.description }}
              </p>
              <div class="param-meta">
                <span v-if="param.default !== undefined">
                  默认值: {{ param.default }}
                </span>
                <span v-if="param.minimum !== undefined">
                  最小值: {{ param.minimum }}
                </span>
                <span v-if="param.maximum !== undefined">
                  最大值: {{ param.maximum }}
                </span>
                <span v-if="param.enum">
                  可选值: {{ param.enum.join(', ') }}
                </span>
              </div>
            </div>
          </div>
          <div v-else class="empty-params">
            <p>该策略没有可配置的参数</p>
          </div>
        </div>

        <div class="card history-card">
          <div class="card-header">
            <h3 class="card-title">回测历史</h3>
          </div>
          <div v-if="backtestHistory.length > 0" class="history-list">
            <div
              v-for="backtest in backtestHistory"
              :key="backtest.id"
              class="history-item"
              @click="goToBacktestResult(backtest.id)"
            >
              <StatusBadge :status="backtest.status as any" />
              <span class="time">{{ formatRelativeTime(backtest.created_at) }}</span>
            </div>
          </div>
          <div v-else class="empty-history">
            <p>暂无回测记录</p>
          </div>
        </div>
      </div>
    </div>

    <ConfirmDialog
      v-model="showDeleteDialog"
      title="删除策略"
      :message="`确定要删除策略 '${strategy?.name}' 吗？此操作不可恢复。`"
      type="danger"
      :loading="deleteLoading"
      @confirm="confirmDelete"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useStrategyStore } from '@/stores/strategy'
import StatusBadge from '@/components/common/StatusBadge.vue'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import { formatDateTime, formatRelativeTime } from '@/utils/format'
import { getBacktests } from '@/api/backtest'
import { useNotification } from '@/composables/useNotification'
import type { Strategy } from '@/types'
import loader from '@monaco-editor/loader'
import type * as Monaco from 'monaco-editor'

const props = defineProps<{
  id: string
}>()

const router = useRouter()
const strategyStore = useStrategyStore()
const { toastSuccess, toastError } = useNotification()

// State
const loading = ref(false)
const strategy = ref<Strategy | null>(null)
const backtestHistory = ref<{ id: string; created_at: string; status: string }[]>([])
const showDeleteDialog = ref(false)
const deleteLoading = ref(false)

// Edit state
const isEditing = ref(false)
const saving = ref(false)
const editDescription = ref('')
const editCode = ref('')

// Monaco Editor
const editorContainerRef = ref<HTMLElement | null>(null)
let editorInstance: Monaco.editor.IStandaloneCodeEditor | null = null
let monacoModule: typeof Monaco | null = null

const hasParams = computed(() => {
  const schema = strategy.value?.params_schema
  return schema?.properties && Object.keys(schema.properties).length > 0
})

const codeChanged = computed(() => {
  return strategy.value ? editCode.value !== strategy.value.code : false
})

// Monaco Editor setup
async function initEditor() {
  if (!editorContainerRef.value) return

  monacoModule = await loader.init()
  const code = strategy.value?.code || ''
  editCode.value = code

  editorInstance = monacoModule.editor.create(editorContainerRef.value, {
    value: code,
    language: 'python',
    theme: 'vs',
    readOnly: !isEditing.value,
    minimap: { enabled: false },
    fontSize: 13,
    lineHeight: 20,
    scrollBeyondLastLine: false,
    automaticLayout: true,
    tabSize: 4,
    wordWrap: 'on',
    renderLineHighlight: isEditing.value ? 'line' : 'none',
    lineNumbers: 'on',
    folding: true,
    scrollbar: {
      verticalScrollbarSize: 8,
      horizontalScrollbarSize: 8,
    },
  })

  editorInstance.onDidChangeModelContent(() => {
    editCode.value = editorInstance?.getValue() || ''
  })

  // Ctrl+S to save
  if (monacoModule) {
    editorInstance.addCommand(monacoModule.KeyMod.CtrlCmd | monacoModule.KeyCode.KeyS, () => {
      if (isEditing.value) {
        saveChanges()
      }
    })
  }

  updateEditorHeight()
}

function updateEditorHeight() {
  if (!editorInstance || !editorContainerRef.value) return
  const lineCount = editorInstance.getModel()?.getLineCount() || 10
  const lineHeight = 20
  const minHeight = 200
  const maxHeight = 600
  const height = Math.min(maxHeight, Math.max(minHeight, lineCount * lineHeight + 20))
  editorContainerRef.value.style.height = `${height}px`
  editorInstance.layout()
}

function disposeEditor() {
  if (editorInstance) {
    editorInstance.dispose()
    editorInstance = null
  }
}

// Edit mode
function enterEditMode() {
  isEditing.value = true
  editDescription.value = strategy.value?.description || ''
  editCode.value = strategy.value?.code || ''

  if (editorInstance) {
    editorInstance.updateOptions({
      readOnly: false,
      renderLineHighlight: 'line',
    })
  }
}

function cancelEdit() {
  isEditing.value = false

  // Restore original code in editor
  if (editorInstance && strategy.value) {
    editorInstance.setValue(strategy.value.code || '')
    editorInstance.updateOptions({
      readOnly: true,
      renderLineHighlight: 'none',
    })
  }

  editDescription.value = ''
  editCode.value = strategy.value?.code || ''
}

async function saveChanges() {
  if (!strategy.value) return

  const updateData: Partial<Strategy> = {}
  let hasChanges = false

  // Check code changes
  if (editCode.value !== strategy.value.code) {
    updateData.code = editCode.value
    hasChanges = true
  }

  // Check description changes
  const newDesc = editDescription.value.trim()
  const oldDesc = strategy.value.description || ''
  if (newDesc !== oldDesc) {
    updateData.description = newDesc
    hasChanges = true
  }

  if (!hasChanges) {
    toastSuccess('没有需要保存的更改')
    cancelEdit()
    return
  }

  saving.value = true
  try {
    const updated = await strategyStore.updateStrategy(props.id, updateData)
    if (updated) {
      strategy.value = updated
      isEditing.value = false
      if (editorInstance) {
        editorInstance.updateOptions({
          readOnly: true,
          renderLineHighlight: 'none',
        })
      }
      toastSuccess(updateData.code ? `保存成功，版本更新至 v${updated.version}` : '保存成功')
    } else {
      toastError('保存失败')
    }
  } finally {
    saving.value = false
  }
}

// Data loading
async function loadStrategy() {
  loading.value = true
  try {
    strategy.value = await strategyStore.loadStrategy(props.id)

    if (strategy.value) {
      editCode.value = strategy.value.code || ''

      // Load backtest history
      try {
        const historyResponse = await getBacktests({ strategy_id: props.id, page_size: 10 })
        backtestHistory.value = historyResponse.data.items
      } catch {
        backtestHistory.value = []
      }
    }
  } finally {
    loading.value = false
  }
}

// Navigation
function goBack() {
  router.back()
}

function goToBacktest() {
  router.push({ path: '/trading/backtest', query: { strategy_id: props.id } })
}

function goToPaper() {
  router.push({ path: '/trading/paper', query: { strategy_id: props.id } })
}

function goToLive() {
  router.push({ path: '/trading/live', query: { strategy_id: props.id } })
}

function goToBacktestResult(backtestId: string) {
  router.push(`/trading/backtest/${backtestId}/result`)
}

// Delete
function handleDelete() {
  showDeleteDialog.value = true
}

async function confirmDelete() {
  deleteLoading.value = true
  try {
    const success = await strategyStore.deleteStrategy(props.id)
    if (success) {
      toastSuccess('策略已删除')
      router.push('/strategy/list')
    } else {
      toastError('删除失败')
    }
  } finally {
    deleteLoading.value = false
    showDeleteDialog.value = false
  }
}

// Lifecycle
onMounted(async () => {
  await loadStrategy()
  await nextTick()
  initEditor()
})

onBeforeUnmount(() => {
  disposeEditor()
})

// Re-init editor if strategy data loads after mount
watch(
  () => strategy.value?.code,
  (newCode) => {
    if (newCode && editorInstance && !isEditing.value) {
      editorInstance.setValue(newCode)
      updateEditorHeight()
    }
  }
)
</script>

<style lang="scss" scoped>
.strategy-detail {
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;

    .header-left {
      display: flex;
      align-items: center;
      gap: 16px;
    }

    .strategy-info {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .strategy-name {
      font-size: 24px;
      font-weight: 600;
      margin: 0;
    }

    .header-right {
      display: flex;
      gap: 12px;
    }
  }

  .content-grid {
    display: grid;
    grid-template-columns: 1fr 360px;
    gap: 24px;
  }

  .info-card {
    .info-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 16px;
    }

    .info-item {
      display: flex;
      flex-direction: column;
      gap: 4px;

      .label {
        font-size: 12px;
        color: #909399;
      }

      .value {
        font-size: 14px;
        font-weight: 500;
      }
    }

    .description {
      margin-top: 16px;
      padding-top: 16px;
      border-top: 1px solid #ebeef5;

      h4 {
        font-size: 14px;
        margin: 0 0 8px;
      }

      p {
        margin: 0;
        color: #606266;
        line-height: 1.6;
      }

      .empty-description {
        color: #c0c4cc;
        font-style: italic;
      }
    }
  }

  .code-card {
    margin-top: 24px;

    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .unsaved-hint {
      font-size: 12px;
      color: #e6a23c;
    }

    .editor-container {
      height: 400px;
      border: 1px solid #ebeef5;
      border-radius: 4px;
      overflow: hidden;
    }
  }

  .params-card {
    .params-list {
      max-height: 400px;
      overflow-y: auto;
    }

    .param-item {
      padding: 12px 0;
      border-bottom: 1px solid #ebeef5;

      &:last-child {
        border-bottom: none;
      }

      .param-header {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 4px;
      }

      .param-name {
        font-weight: 500;
      }

      .param-description {
        font-size: 12px;
        color: #909399;
        margin: 4px 0;
      }

      .param-meta {
        font-size: 12px;
        color: #909399;
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
      }
    }

    .empty-params {
      color: #909399;
      text-align: center;
      padding: 24px 0;
    }
  }

  .history-card {
    margin-top: 24px;

    .history-list {
      max-height: 300px;
      overflow-y: auto;
    }

    .history-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 8px 0;
      cursor: pointer;
      border-bottom: 1px solid #ebeef5;

      &:last-child {
        border-bottom: none;
      }

      &:hover {
        background: #f5f7fa;
        margin: 0 -16px;
        padding: 8px 16px;
      }

      .time {
        font-size: 12px;
        color: #909399;
      }
    }

    .empty-history {
      color: #909399;
      text-align: center;
      padding: 24px 0;
    }
  }
}
</style>
