<template>
  <div class="paper-trading">
    <div class="page-header">
      <h1 class="page-title">模拟交易</h1>
    </div>

    <div class="paper-grid">
      <div class="config-panel card">
        <div class="card-header">
          <h3 class="card-title">启动模拟交易</h3>
        </div>

        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-position="top"
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

          <el-row :gutter="16">
            <el-col :span="12">
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
            </el-col>
            <el-col :span="12">
              <el-form-item label="初始资金" prop="initial_capital">
                <el-input-number
                  v-model="form.initial_capital"
                  :min="100"
                  :step="1000"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
          </el-row>

          <el-row :gutter="16">
            <el-col :span="12">
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
            <!-- 滑点已由实时 bid/ask spread 模拟替代，后端使用默认值作为降级保护 -->
          </el-row>

          <div class="risk-config-section">
            <div class="risk-config-header">
              <el-switch v-model="enableRiskConfig" size="small" />
              <span class="risk-config-label">风控配置（可选）</span>
            </div>
            <div v-show="enableRiskConfig" class="risk-config-body">
              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item label="最大持仓比例">
                    <el-input-number
                      v-model="riskConfig.max_position_size"
                      :min="0.01"
                      :max="1"
                      :step="0.1"
                      :precision="2"
                      style="width: 100%"
                    />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="最大单笔下单比例">
                    <el-input-number
                      v-model="riskConfig.max_order_size"
                      :min="0.01"
                      :max="1"
                      :step="0.1"
                      :precision="2"
                      style="width: 100%"
                    />
                  </el-form-item>
                </el-col>
              </el-row>
              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item label="每日交易限制">
                    <el-input-number
                      v-model="riskConfig.daily_trade_limit"
                      :min="1"
                      :max="1000"
                      style="width: 100%"
                    />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="日最大亏损比例">
                    <el-input-number
                      v-model="riskConfig.daily_loss_limit"
                      :min="0.01"
                      :max="1"
                      :step="0.01"
                      :precision="2"
                      style="width: 100%"
                    />
                  </el-form-item>
                </el-col>
              </el-row>
              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item label="价格偏离限制">
                    <el-input-number
                      v-model="riskConfig.price_deviation_limit"
                      :min="0.001"
                      :max="0.5"
                      :step="0.01"
                      :precision="3"
                      style="width: 100%"
                    />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="熔断触发次数">
                    <el-input-number
                      v-model="riskConfig.circuit_breaker_threshold"
                      :min="1"
                      :max="20"
                      style="width: 100%"
                    />
                  </el-form-item>
                </el-col>
              </el-row>
              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item label="最小下单金额 (USDT)">
                    <el-input-number
                      v-model="riskConfig.min_order_value"
                      :min="1"
                      :max="100000"
                      :step="5"
                      style="width: 100%"
                    />
                  </el-form-item>
                </el-col>
              </el-row>
            </div>
          </div>

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
            <el-button
              type="primary"
              size="large"
              :loading="submitting"
              @click="handleSubmit"
              style="width: 100%"
            >
              启动模拟交易
            </el-button>
          </el-form-item>
        </el-form>
      </div>

      <div class="sessions-panel card">
        <div class="card-header">
          <h3 class="card-title">模拟交易会话</h3>
        </div>

        <div class="sessions-list" v-loading="sessionsLoading">
          <div
            v-for="session in sessions"
            :key="session.id"
            class="session-item"
            @click="goToMonitor(session.id)"
          >
            <div class="item-header">
              <span class="strategy-name">{{ session.strategy_name }}</span>
              <StatusBadge :status="session.status" />
            </div>
            <div class="item-info">
              <span>{{ session.symbol }}</span>
              <span>{{ formatExchangeName(session.exchange) }}</span>
            </div>
            <div class="item-stats">
              <div class="stat">
                <span class="label">初始资金</span>
                <span class="value">{{ formatNumber(session.initial_capital ?? 0, 2) }}</span>
              </div>
            </div>
            <div class="item-actions" @click.stop>
              <el-button
                v-if="session.status === 'running'"
                type="danger"
                size="small"
                @click="handleStop(session.id)"
              >
                停止
              </el-button>
            </div>
          </div>

          <div v-if="sessions.length === 0" class="empty-state">
            <p>暂无模拟交易会话</p>
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
import { formatExchangeName, formatNumber } from '@/utils/format'
import { TIMEFRAME_OPTIONS } from '@/utils/constants'
import { getSymbols } from '@/api/market'
import { startPaperTrading, getPaperSessions, stopPaperTrading } from '@/api/paper'
import { useNotification } from '@/composables/useNotification'
import type { PaperSession } from '@/types'

const router = useRouter()
const route = useRoute()
const marketStore = useMarketStore()
const strategyStore = useStrategyStore()
const { toastSuccess, toastError, confirmDanger } = useNotification()

const formRef = ref<FormInstance>()
const submitting = ref(false)
const sessionsLoading = ref(false)
const symbols = ref<string[]>([])
const sessions = ref<PaperSession[]>([])

const form = reactive({
  strategy_id: (route.query.strategy_id as string) || '',
  exchange: (route.query.exchange as string) || 'okx',
  symbol: (route.query.symbol as string) || '',
  timeframe: '1h',
  initial_capital: 10000,
  commission_rate: 0.1,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  params: {} as Record<string, any>,
})

const enableRiskConfig = ref(false)
const riskConfig = reactive({
  max_position_size: 0.5,
  max_order_size: 0.2,
  daily_trade_limit: 50,
  daily_loss_limit: 0.05,
  price_deviation_limit: 0.02,
  circuit_breaker_threshold: 3,
  min_order_value: 10,
})

const rules: FormRules = {
  strategy_id: [{ required: true, message: '请选择策略', trigger: 'change' }],
  exchange: [{ required: true, message: '请选择交易所', trigger: 'change' }],
  symbol: [{ required: true, message: '请选择交易对', trigger: 'change' }],
  timeframe: [{ required: true, message: '请选择时间周期', trigger: 'change' }],
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

async function loadSessions() {
  sessionsLoading.value = true
  try {
    const response = await getPaperSessions({ page: 1, page_size: 50 })
    sessions.value = response.data.items
  } finally {
    sessionsLoading.value = false
  }
}

function handleStrategyChange() {
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

async function handleSubmit() {
  const valid = await formRef.value?.validate()
  if (!valid) return

  submitting.value = true
  try {
    const config: Record<string, unknown> = {
      strategy_id: form.strategy_id,
      exchange: form.exchange,
      symbol: form.symbol,
      timeframe: form.timeframe,
      initial_capital: form.initial_capital,
      commission_rate: form.commission_rate / 100,
      params: form.params,
    }
    if (enableRiskConfig.value) {
      config.risk_config = { ...riskConfig }
    }

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const response = await startPaperTrading(config as any)
    toastSuccess('模拟交易已启动')
    router.push(`/trading/monitor/paper/${response.data.id}`)
  } catch (error) {
    toastError('启动失败')
  } finally {
    submitting.value = false
  }
}

function goToMonitor(id: string) {
  router.push(`/trading/monitor/paper/${id}`)
}

async function handleStop(id: string) {
  const confirmed = await confirmDanger('确定要停止该模拟交易吗？')
  if (!confirmed) return

  try {
    await stopPaperTrading(id)
    toastSuccess('已停止')
    loadSessions()
  } catch (error) {
    toastError('停止失败')
  }
}

onMounted(async () => {
  await Promise.all([
    marketStore.loadExchanges(),
    strategyStore.loadStrategies(),
  ])
  loadSymbols()
  loadSessions()

  if (form.strategy_id) {
    handleStrategyChange()
  }
})
</script>

<style lang="scss" scoped>
.paper-trading {
  .page-header {
    margin-bottom: 24px;
  }

  .page-title {
    font-size: 20px;
    font-weight: 600;
  }

  .paper-grid {
    display: grid;
    grid-template-columns: 1fr 400px;
    gap: 24px;
  }

  .risk-config-section {
    margin: 16px 0;
    padding: 12px 0;
    border-top: 1px solid #ebeef5;

    .risk-config-header {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 12px;
    }

    .risk-config-label {
      font-size: 14px;
      color: #606266;
    }

    .risk-config-body {
      padding-top: 4px;
    }
  }

  .params-section {
    margin-top: 16px;
    padding-top: 16px;
    border-top: 1px solid #ebeef5;

    h4 {
      margin: 0 0 16px;
      font-size: 14px;
    }
  }

  .sessions-list {
    max-height: 600px;
    overflow-y: auto;
  }

  .session-item {
    padding: 16px;
    margin-bottom: 12px;
    background: #f5f7fa;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s;

    &:hover {
      background: #ebeef5;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
    }

    .item-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;

      .strategy-name {
        font-weight: 600;
      }
    }

    .item-info {
      display: flex;
      gap: 12px;
      font-size: 12px;
      color: #909399;
      margin-bottom: 12px;
    }

    .item-stats {
      display: flex;
      gap: 24px;
      margin-bottom: 12px;

      .stat {
        display: flex;
        flex-direction: column;
        gap: 2px;

        .label {
          font-size: 12px;
          color: #909399;
        }

        .value {
          font-size: 14px;
          font-weight: 500;
        }
      }
    }

    .item-actions {
      display: flex;
      justify-content: flex-end;
    }
  }

  .empty-state {
    text-align: center;
    padding: 40px;
    color: #909399;
  }
}
</style>
