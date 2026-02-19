<template>
  <div class="backtest">
    <div class="page-header">
      <h1 class="page-title">回测</h1>
    </div>

    <div class="backtest-grid">
      <div class="config-panel card">
        <div class="card-header">
          <h3 class="card-title">回测配置</h3>
        </div>

        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-position="top"
          @submit.prevent="handleSubmit"
        >
          <el-form-item label="策略" prop="strategy_id">
            <el-select
              v-model="form.strategy_id"
              placeholder="选择策略"
              filterable
              style="width: 100%"
              @change="handleStrategyChange"
            >
              <el-option
                v-for="s in strategies"
                :key="s.id"
                :label="s.name"
                :value="s.id"
                :disabled="s.status !== 'active'"
              />
            </el-select>
          </el-form-item>

          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="交易所" prop="exchange">
                <el-select
                  v-model="form.exchange"
                  placeholder="选择交易所"
                  style="width: 100%"
                  @change="loadSymbols"
                >
                  <el-option
                    v-for="e in exchanges"
                    :key="e"
                    :label="formatExchangeName(e)"
                    :value="e"
                  />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="交易对" prop="symbol">
                <el-select
                  v-model="form.symbol"
                  placeholder="选择交易对"
                  filterable
                  style="width: 100%"
                >
                  <el-option
                    v-for="s in symbols"
                    :key="s"
                    :label="s"
                    :value="s"
                  />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>

          <el-form-item label="时间周期" prop="timeframe">
            <el-select v-model="form.timeframe" style="width: 100%">
              <el-option
                v-for="tf in timeframeOptions"
                :key="tf.value"
                :label="tf.label"
                :value="tf.value"
              />
            </el-select>
          </el-form-item>

          <el-form-item label="回测时间范围" prop="dateRange">
            <el-date-picker
              v-model="form.dateRange"
              type="daterange"
              range-separator="至"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              value-format="YYYY-MM-DD"
              style="width: 100%"
            />
          </el-form-item>

          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item label="初始资金" prop="initial_capital">
                <el-input-number
                  v-model="form.initial_capital"
                  :min="100"
                  :step="1000"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="手续费率 (%)" prop="commission_rate">
                <el-input-number
                  v-model="form.commission_rate"
                  :min="0"
                  :max="100"
                  :step="0.01"
                  :precision="4"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="滑点 (%)" prop="slippage">
                <el-input-number
                  v-model="form.slippage"
                  :min="0"
                  :max="100"
                  :step="0.01"
                  :precision="4"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
          </el-row>

          <div v-if="selectedStrategy?.params_schema?.properties" class="params-section">
            <h4>策略参数</h4>
            <el-row :gutter="16">
              <el-col
                v-for="(param, key) in selectedStrategy.params_schema.properties"
                :key="key"
                :span="12"
              >
                <el-form-item :label="param.title || String(key)">
                  <el-input-number
                    v-if="param.type === 'number' || param.type === 'integer'"
                    v-model="form.params[key]"
                    :min="param.minimum"
                    :max="param.maximum"
                    style="width: 100%"
                  />
                  <el-switch
                    v-else-if="param.type === 'boolean'"
                    v-model="form.params[key]"
                  />
                  <el-select
                    v-else-if="param.enum"
                    v-model="form.params[key]"
                    style="width: 100%"
                  >
                    <el-option
                      v-for="opt in param.enum"
                      :key="opt"
                      :label="opt"
                      :value="opt"
                    />
                  </el-select>
                  <el-input
                    v-else
                    v-model="form.params[key]"
                  />
                </el-form-item>
              </el-col>
            </el-row>
          </div>

          <el-form-item>
            <div style="display: flex; gap: 12px; width: 100%">
              <el-button
                size="large"
                @click="handleReset"
                style="flex: 0 0 auto"
              >
                重置
              </el-button>
              <el-button
                type="primary"
                size="large"
                :loading="submitting"
                @click="handleSubmit"
                style="flex: 1"
              >
                开始回测
              </el-button>
            </div>
          </el-form-item>
        </el-form>
      </div>

      <div class="history-panel card">
        <div class="card-header">
          <h3 class="card-title">回测历史</h3>
        </div>

        <div class="history-list" v-loading="historyLoading">
          <div
            v-for="backtest in backtestHistory"
            :key="backtest.id"
            class="history-item"
            @click="goToResult(backtest.id)"
          >
            <div class="item-header">
              <span class="strategy-name">{{ backtest.strategy_name }}</span>
              <StatusBadge :status="backtest.status" />
            </div>
            <div class="item-meta">
              <span>{{ backtest.symbol }}</span>
              <span>{{ formatDateTime(backtest.created_at, 'MM-DD HH:mm') }}</span>
            </div>
            <el-progress
              v-if="backtest.status === 'running'"
              :percentage="backtest.progress"
              :stroke-width="4"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { useMarketStore } from '@/stores/market'
import { useStrategyStore } from '@/stores/strategy'
import StatusBadge from '@/components/common/StatusBadge.vue'
import { formatExchangeName, formatDateTime } from '@/utils/format'
import { TIMEFRAME_OPTIONS } from '@/utils/constants'
import { getSymbols } from '@/api/market'
import { startBacktest, getBacktests, checkDataAvailability } from '@/api/backtest'
import { downloadHistoricalData } from '@/api/system'
import { useNotification } from '@/composables/useNotification'
import type { BacktestRun } from '@/types'

const router = useRouter()
const route = useRoute()
const marketStore = useMarketStore()
const strategyStore = useStrategyStore()
const { toastSuccess, toastError } = useNotification()

const formRef = ref<FormInstance>()
const submitting = ref(false)
const historyLoading = ref(false)
const symbols = ref<string[]>([])
const backtestHistory = ref<BacktestRun[]>([])

const q = route.query
const form = reactive({
  strategy_id: (q.strategy_id as string) || '',
  exchange: (q.exchange as string) || 'okx',
  symbol: (q.symbol as string) || '',
  timeframe: (q.timeframe as string) || '1h',
  dateRange: (q.start_date && q.end_date ? [q.start_date as string, q.end_date as string] : []) as string[],
  initial_capital: q.initial_capital ? Number(q.initial_capital) : 10000,
  commission_rate: q.commission_rate ? Number(q.commission_rate) : 0.1,
  slippage: q.slippage ? Number(q.slippage) : 0.1,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  params: {} as Record<string, any>,
})

const rules: FormRules = {
  strategy_id: [{ required: true, message: '请选择策略', trigger: 'change' }],
  exchange: [{ required: true, message: '请选择交易所', trigger: 'change' }],
  symbol: [{ required: true, message: '请选择交易对', trigger: 'change' }],
  timeframe: [{ required: true, message: '请选择时间周期', trigger: 'change' }],
  dateRange: [
    { required: true, message: '请选择时间范围', trigger: 'change' },
    {
      validator: (_rule: unknown, value: string[], callback: (error?: string | Error) => void) => {
        if (value && value.length === 2 && new Date(value[0]) >= new Date(value[1])) {
          callback(new Error('开始日期必须早于结束日期'))
        } else {
          callback()
        }
      },
      trigger: 'change',
    },
  ],
  initial_capital: [{ required: true, message: '请输入初始资金', trigger: 'change' }],
}

const exchanges = computed(() => marketStore.exchanges)
const strategies = computed(() => strategyStore.strategies)
const timeframeOptions = TIMEFRAME_OPTIONS

const selectedStrategy = computed(() => {
  if (!form.strategy_id) return null
  return strategies.value.find((s) => s.id === form.strategy_id)
})

async function loadSymbols() {
  if (!form.exchange) return
  try {
    const response = await getSymbols(form.exchange)
    symbols.value = response.data
  } catch (error) {
    console.error('Failed to load symbols:', error)
  }
}

async function loadHistory() {
  historyLoading.value = true
  try {
    const response = await getBacktests({ page: 1, page_size: 20 })
    backtestHistory.value = response.data.items
  } finally {
    historyLoading.value = false
  }
}

function handleReset() {
  form.strategy_id = ''
  form.exchange = 'okx'
  form.symbol = ''
  form.timeframe = '1h'
  form.dateRange = []
  form.initial_capital = 10000
  form.commission_rate = 0.1
  form.slippage = 0.1
  form.params = {}
  formRef.value?.resetFields()
}

function handleStrategyChange() {
  // 初始化策略参数默认值
  const strategy = selectedStrategy.value
  if (strategy?.params_schema?.properties) {
    const params: Record<string, unknown> = {}
    for (const [key, param] of Object.entries(strategy.params_schema.properties)) {
      if (param.default !== undefined) {
        params[key] = param.default
      }
    }
    form.params = params
  } else {
    form.params = {}
  }
}

async function triggerDownload() {
  try {
    await downloadHistoricalData({
      exchange: form.exchange,
      symbol: form.symbol,
      timeframe: form.timeframe,
      start_date: form.dateRange[0],
      end_date: form.dateRange[1],
    })
    toastSuccess('下载任务已创建，可在「系统管理 > 数据管理」中查看进度')
  } catch {
    toastError('创建下载任务失败')
  }
}

async function handleSubmit() {
  const valid = await formRef.value?.validate()
  if (!valid) return

  submitting.value = true
  try {
    // 提交前检查历史数据可用性
    const checkResponse = await checkDataAvailability({
      exchange: form.exchange,
      symbol: form.symbol,
      timeframe: form.timeframe,
      start_date: form.dateRange[0],
      end_date: form.dateRange[1],
    })
    const availability = checkResponse.data
    if (!availability.has_data) {
      try {
        await ElMessageBox.confirm(
          `所选时间范围内无可用历史数据（${form.exchange} · ${form.symbol} · ${form.timeframe}），是否立即下载？`,
          '缺少历史数据',
          { confirmButtonText: '下载数据', cancelButtonText: '取消', type: 'warning' },
        )
        await triggerDownload()
      } catch { /* 用户取消 */ }
      return
    }
    if (!availability.is_complete) {
      try {
        await ElMessageBox.confirm(
          `历史数据不完整（仅有 ${availability.total_bars} 根K线，` +
          `覆盖 ${availability.first_bar?.slice(0, 10) || '?'} 至 ${availability.last_bar?.slice(0, 10) || '?'}），` +
          `是否下载完整数据？`,
          '历史数据不完整',
          { confirmButtonText: '下载数据', cancelButtonText: '取消', type: 'warning' },
        )
        await triggerDownload()
      } catch { /* 用户取消 */ }
      return
    }

    const config = {
      strategy_id: form.strategy_id,
      exchange: form.exchange,
      symbol: form.symbol,
      timeframe: form.timeframe,
      start_date: form.dateRange[0],
      end_date: form.dateRange[1],
      initial_capital: form.initial_capital,
      commission_rate: form.commission_rate / 100,
      slippage: form.slippage / 100,
      params: form.params,
    }

    const response = await startBacktest(config)
    toastSuccess('回测已启动')
    router.push(`/trading/backtest/${response.data.id}/result`)
  } catch (error) {
    toastError('启动回测失败')
  } finally {
    submitting.value = false
  }
}

function goToResult(id: string) {
  router.push(`/trading/backtest/${id}/result`)
}

onMounted(async () => {
  await Promise.all([
    marketStore.loadExchanges(),
    strategyStore.loadStrategies(),
  ])
  loadSymbols()
  loadHistory()

  if (form.strategy_id) {
    handleStrategyChange()
    // Override with query params if present (from "再次回测")
    if (q.params) {
      try {
        const parsed = JSON.parse(q.params as string)
        Object.assign(form.params, parsed)
      } catch { /* ignore invalid JSON */ }
    }
  }
})
</script>

<style lang="scss" scoped>
.backtest {
  .page-header {
    margin-bottom: 24px;
  }

  .page-title {
    font-size: 20px;
    font-weight: 600;
  }

  .backtest-grid {
    display: grid;
    grid-template-columns: 1fr 360px;
    gap: 24px;
  }

  .config-panel {
    .params-section {
      margin-top: 16px;
      padding-top: 16px;
      border-top: 1px solid #ebeef5;

      h4 {
        margin: 0 0 16px;
        font-size: 14px;
      }
    }
  }

  .history-panel {
    .history-list {
      max-height: 600px;
      overflow-y: auto;
    }

    .history-item {
      padding: 12px;
      margin-bottom: 8px;
      background: #f5f7fa;
      border-radius: 4px;
      cursor: pointer;
      transition: background 0.2s;

      &:hover {
        background: #ebeef5;
      }

      .item-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 4px;

        .strategy-name {
          font-weight: 500;
        }
      }

      .item-meta {
        display: flex;
        justify-content: space-between;
        font-size: 12px;
        color: #909399;
      }
    }
  }
}
</style>
