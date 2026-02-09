<template>
  <div class="risk-rules">
    <div class="page-header">
      <h1 class="page-title">风控规则</h1>
      <el-button type="primary" @click="showCreateDialog">
        <el-icon><Plus /></el-icon>
        添加规则
      </el-button>
    </div>

    <div class="rules-grid" v-loading="loading">
      <div
        v-for="rule in rules"
        :key="rule.id"
        class="rule-card card"
        :class="{ disabled: !rule.enabled }"
      >
        <div class="card-header">
          <div class="header-left">
            <h3 class="rule-name">{{ rule.name }}</h3>
            <el-tag size="small" type="info">{{ getRuleTypeLabel(rule.type) }}</el-tag>
          </div>
          <el-switch
            v-model="rule.enabled"
            @change="handleToggle(rule)"
          />
        </div>

        <p class="rule-description">{{ rule.description }}</p>

        <div class="rule-params">
          <div v-for="(value, key) in rule.params" :key="key" class="param-item">
            <span class="param-key">{{ key }}:</span>
            <span class="param-value">{{ value }}</span>
          </div>
        </div>

        <div class="rule-footer">
          <span v-if="rule.last_triggered_at" class="last-triggered">
            上次触发: {{ formatRelativeTime(rule.last_triggered_at) }}
          </span>
        </div>

        <div class="rule-actions">
          <el-button size="small" @click="showEditDialog(rule)">编辑</el-button>
          <el-button size="small" type="danger" @click="handleDelete(rule)">删除</el-button>
        </div>
      </div>
    </div>

    <div v-if="rules.length === 0 && !loading" class="empty-state card">
      <el-icon class="empty-icon"><Warning /></el-icon>
      <p>暂无风控规则</p>
      <el-button type="primary" @click="showCreateDialog">添加规则</el-button>
    </div>

    <!-- 创建/编辑规则对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingRule ? '编辑规则' : '添加规则'"
      width="500px"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="formRules"
        label-position="top"
      >
        <el-form-item label="规则名称" prop="name">
          <el-input v-model="form.name" placeholder="输入规则名称" />
        </el-form-item>

        <el-form-item label="规则类型" prop="type">
          <el-select v-model="form.type" style="width: 100%" @change="handleTypeChange">
            <el-option
              v-for="t in ruleTypeOptions"
              :key="t.value"
              :label="t.label"
              :value="t.value"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="描述" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>

        <el-divider>规则参数</el-divider>

        <template v-if="form.type === 'order_limit'">
          <el-form-item label="最大单笔订单金额 (USDT)">
            <el-input-number v-model="form.params.max_amount" :min="1" style="width: 100%" />
          </el-form-item>
        </template>

        <template v-else-if="form.type === 'position_limit'">
          <el-form-item label="最大持仓比例 (%)">
            <el-input-number v-model="form.params.max_percent" :min="1" :max="100" style="width: 100%" />
          </el-form-item>
        </template>

        <template v-else-if="form.type === 'daily_loss_limit'">
          <el-form-item label="日最大亏损比例 (%)">
            <el-input-number v-model="form.params.max_percent" :min="1" :max="100" style="width: 100%" />
          </el-form-item>
        </template>

        <template v-else-if="form.type === 'total_loss_limit'">
          <el-form-item label="总最大亏损比例 (%)">
            <el-input-number v-model="form.params.max_percent" :min="1" :max="100" style="width: 100%" />
          </el-form-item>
        </template>

        <template v-else-if="form.type === 'frequency_limit'">
          <el-form-item label="最大交易频率 (次/小时)">
            <el-input-number v-model="form.params.max_count" :min="1" style="width: 100%" />
          </el-form-item>
        </template>

        <template v-else-if="form.type === 'volatility_break'">
          <el-form-item label="波动阈值 (%)">
            <el-input-number v-model="form.params.threshold_percent" :min="1" :max="100" style="width: 100%" />
          </el-form-item>
          <el-form-item label="检测时间窗口 (分钟)">
            <el-input-number v-model="form.params.window_minutes" :min="1" style="width: 100%" />
          </el-form-item>
        </template>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">
          确定
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { formatRelativeTime } from '@/utils/format'
import { RISK_RULE_TYPE_OPTIONS } from '@/utils/constants'
import {
  getRiskRules,
  createRiskRule,
  updateRiskRule,
  deleteRiskRule,
  toggleRiskRule,
} from '@/api/risk'
import { useNotification } from '@/composables/useNotification'
import type { RiskRule, RiskRuleType } from '@/types'

const { toastSuccess, toastError, confirmDelete } = useNotification()

const loading = ref(false)
const submitting = ref(false)
const rules = ref<RiskRule[]>([])
const dialogVisible = ref(false)
const editingRule = ref<RiskRule | null>(null)
const formRef = ref<FormInstance>()

interface RuleParams {
  max_percent?: number
  max_amount?: number
  max_count?: number
  threshold_percent?: number
  window_minutes?: number
}

const form = reactive({
  name: '',
  type: 'order_limit' as RiskRuleType,
  description: '',
  params: {} as RuleParams,
})

const formRules: FormRules = {
  name: [{ required: true, message: '请输入规则名称', trigger: 'blur' }],
  type: [{ required: true, message: '请选择规则类型', trigger: 'change' }],
}

const ruleTypeOptions = RISK_RULE_TYPE_OPTIONS

function getRuleTypeLabel(type: string) {
  return ruleTypeOptions.find((t) => t.value === type)?.label || type
}

async function loadRules() {
  loading.value = true
  try {
    const response = await getRiskRules()
    rules.value = response.data.items
  } catch (error) {
    console.error('Failed to load rules:', error)
  } finally {
    loading.value = false
  }
}

function showCreateDialog() {
  editingRule.value = null
  form.name = ''
  form.type = 'order_limit'
  form.description = ''
  form.params = { max_amount: 10000 } as RuleParams
  dialogVisible.value = true
}

function showEditDialog(rule: RiskRule) {
  editingRule.value = rule
  form.name = rule.name
  form.type = rule.type
  form.description = rule.description ?? ''
  form.params = { ...rule.params } as RuleParams
  dialogVisible.value = true
}

function handleTypeChange() {
  // 重置参数为默认值
  switch (form.type) {
    case 'order_limit':
      form.params = { max_amount: 10000 } as RuleParams
      break
    case 'position_limit':
    case 'daily_loss_limit':
    case 'total_loss_limit':
      form.params = { max_percent: 50 } as RuleParams
      break
    case 'frequency_limit':
      form.params = { max_count: 10 } as RuleParams
      break
    case 'volatility_break':
      form.params = { threshold_percent: 10, window_minutes: 5 } as RuleParams
      break
    default:
      form.params = {} as RuleParams
  }
}

async function handleSubmit() {
  const valid = await formRef.value?.validate()
  if (!valid) return

  submitting.value = true
  try {
    const data = {
      name: form.name,
      type: form.type,
      description: form.description,
      params: form.params,
      enabled: true,
    }

    if (editingRule.value) {
      await updateRiskRule(editingRule.value.id, data)
      toastSuccess('规则已更新')
    } else {
      await createRiskRule(data)
      toastSuccess('规则已创建')
    }

    dialogVisible.value = false
    loadRules()
  } catch (error) {
    toastError('操作失败')
  } finally {
    submitting.value = false
  }
}

async function handleToggle(rule: RiskRule) {
  try {
    await toggleRiskRule(rule.id, rule.enabled)
    toastSuccess(rule.enabled ? '规则已启用' : '规则已禁用')
  } catch (error) {
    rule.enabled = !rule.enabled
    toastError('操作失败')
  }
}

async function handleDelete(rule: RiskRule) {
  const confirmed = await confirmDelete('该规则')
  if (!confirmed) return

  try {
    await deleteRiskRule(rule.id)
    toastSuccess('规则已删除')
    loadRules()
  } catch (error) {
    toastError('删除失败')
  }
}

onMounted(() => {
  loadRules()
})
</script>

<style lang="scss" scoped>
.risk-rules {
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
  }

  .page-title {
    font-size: 20px;
    font-weight: 600;
  }

  .rules-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
    gap: 16px;
  }

  .rule-card {
    transition: all 0.2s;

    &.disabled {
      opacity: 0.6;
    }

    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 8px;

      .header-left {
        display: flex;
        align-items: center;
        gap: 8px;
      }

      .rule-name {
        font-size: 16px;
        font-weight: 600;
        margin: 0;
      }
    }

    .rule-description {
      color: #606266;
      font-size: 14px;
      margin: 0 0 12px;
    }

    .rule-params {
      background: #f5f7fa;
      padding: 12px;
      border-radius: 4px;
      margin-bottom: 12px;

      .param-item {
        display: flex;
        gap: 8px;
        font-size: 13px;
        margin-bottom: 4px;

        &:last-child {
          margin-bottom: 0;
        }

        .param-key {
          color: #909399;
        }

        .param-value {
          font-weight: 500;
        }
      }
    }

    .rule-footer {
      display: flex;
      justify-content: flex-end;
      align-items: center;
      margin-bottom: 12px;

      .last-triggered {
        font-size: 12px;
        color: #909399;
      }
    }

    .rule-actions {
      display: flex;
      gap: 8px;
      padding-top: 12px;
      border-top: 1px solid #ebeef5;
    }
  }

  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 60px;

    .empty-icon {
      font-size: 48px;
      color: #dcdfe6;
      margin-bottom: 16px;
    }

    p {
      color: #909399;
      margin-bottom: 16px;
    }
  }
}
</style>
