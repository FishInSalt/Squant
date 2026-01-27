<template>
  <div class="live-trading">
    <div class="page-header">
      <h1 class="page-title">实盘交易</h1>
    </div>

    <el-alert
      type="warning"
      show-icon
      :closable="false"
      class="warning-alert"
    >
      <template #title>
        <strong>风险提示</strong>
      </template>
      实盘交易涉及真实资金，请确保您已充分了解策略风险并做好风控设置。
    </el-alert>

    <div class="live-grid">
      <div class="config-panel card">
        <div class="card-header">
          <h3 class="card-title">启动实盘交易</h3>
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
                :disabled="!s.is_valid"
              />
            </el-select>
          </el-form-item>

          <el-form-item label="交易所账户" prop="account_id">
            <el-select
              v-model="form.account_id"
              placeholder="选择账户"
              style="width: 100%"
              @change="handleAccountChange"
            >
              <el-option
                v-for="a in accounts"
                :key="a.id"
                :label="`${a.name} (${formatExchangeName(a.exchange)})`"
                :value="a.id"
                :disabled="a.connection_status !== 'connected'"
              >
                <div class="account-option">
                  <span>{{ a.name }}</span>
                  <StatusBadge :status="a.connection_status" />
                </div>
              </el-option>
            </el-select>
          </el-form-item>

          <el-row :gutter="16">
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
          </el-row>

          <el-form-item label="投入资金" prop="initial_capital">
            <el-input-number
              v-model="form.initial_capital"
              :min="10"
              :step="100"
              style="width: 100%"
            />
          </el-form-item>

          <el-divider>风控设置</el-divider>

          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="最大持仓 (%)">
                <el-input-number
                  v-model="form.risk_config.max_position_size"
                  :min="1"
                  :max="100"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="日最大亏损 (%)">
                <el-input-number
                  v-model="form.risk_config.max_daily_loss"
                  :min="1"
                  :max="100"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
          </el-row>

          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="最大回撤 (%)">
                <el-input-number
                  v-model="form.risk_config.max_drawdown"
                  :min="1"
                  :max="100"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="止损 (%)">
                <el-input-number
                  v-model="form.risk_config.stop_loss_percent"
                  :min="0"
                  :max="100"
                  :precision="1"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
          </el-row>

          <div v-if="selectedStrategy?.params_schema?.properties" class="params-section">
            <el-divider>策略参数</el-divider>
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
              type="danger"
              size="large"
              :loading="submitting"
              @click="handleSubmit"
              style="width: 100%"
            >
              启动实盘交易
            </el-button>
          </el-form-item>
        </el-form>
      </div>

      <div class="sessions-panel card">
        <div class="card-header">
          <h3 class="card-title">实盘交易会话</h3>
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
                <span class="label">当前权益</span>
                <span class="value">{{ formatNumber(session.current_equity, 2) }}</span>
              </div>
              <div class="stat">
                <span class="label">总收益</span>
                <PriceCell
                  :value="session.realized_pnl + session.unrealized_pnl"
                  :change="session.realized_pnl + session.unrealized_pnl"
                  show-sign
                  class="value"
                />
              </div>
            </div>
            <div class="item-actions" @click.stop>
              <el-button
                v-if="session.status === 'running'"
                type="warning"
                size="small"
                @click="handleStop(session.id)"
              >
                停止
              </el-button>
              <el-button
                v-if="session.status === 'running'"
                type="danger"
                size="small"
                @click="handleEmergencyClose(session.id)"
              >
                紧急平仓
              </el-button>
            </div>
          </div>

          <div v-if="sessions.length === 0" class="empty-state">
            <p>暂无实盘交易会话</p>
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
import { useStrategyStore } from '@/stores/strategy'
import StatusBadge from '@/components/common/StatusBadge.vue'
import PriceCell from '@/components/common/PriceCell.vue'
import { formatExchangeName, formatNumber } from '@/utils/format'
import { TIMEFRAME_OPTIONS } from '@/utils/constants'
import { getSymbols } from '@/api/market'
import { getAccounts } from '@/api/account'
import { startLiveTrading, getLiveSessions, stopLiveTrading, emergencyClosePositions } from '@/api/live'
import { useNotification } from '@/composables/useNotification'
import type { LiveSession, ExchangeAccount } from '@/types'

const router = useRouter()
const route = useRoute()
const strategyStore = useStrategyStore()
const { toastSuccess, toastError, confirmDanger } = useNotification()

const formRef = ref<FormInstance>()
const submitting = ref(false)
const sessionsLoading = ref(false)
const symbols = ref<string[]>([])
const accounts = ref<ExchangeAccount[]>([])
const sessions = ref<LiveSession[]>([])

const form = reactive({
  strategy_id: (route.query.strategy_id as string) || '',
  account_id: '',
  symbol: (route.query.symbol as string) || '',
  timeframe: '1h',
  initial_capital: 1000,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  params: {} as Record<string, any>,
  risk_config: {
    max_position_size: 50,
    max_daily_loss: 5,
    max_drawdown: 10,
    stop_loss_percent: 2,
  },
})

const rules: FormRules = {
  strategy_id: [{ required: true, message: '请选择策略', trigger: 'change' }],
  account_id: [{ required: true, message: '请选择交易所账户', trigger: 'change' }],
  symbol: [{ required: true, message: '请选择交易对', trigger: 'change' }],
  timeframe: [{ required: true, message: '请选择时间周期', trigger: 'change' }],
  initial_capital: [{ required: true, message: '请输入投入资金', trigger: 'change' }],
}

const strategies = computed(() => strategyStore.strategies)
const timeframeOptions = TIMEFRAME_OPTIONS

const selectedStrategy = computed(() => {
  if (!form.strategy_id) return null
  return strategies.value.find((s) => s.id === form.strategy_id)
})

const selectedAccount = computed(() => {
  if (!form.account_id) return null
  return accounts.value.find((a) => a.id === form.account_id)
})

async function loadAccounts() {
  try {
    const response = await getAccounts()
    accounts.value = response.data
  } catch (error) {
    console.error('Failed to load accounts:', error)
  }
}

async function loadSymbols() {
  const account = selectedAccount.value
  if (!account) return
  try {
    const response = await getSymbols(account.exchange)
    symbols.value = response.data
  } catch (error) {
    console.error('Failed to load symbols:', error)
  }
}

async function loadSessions() {
  sessionsLoading.value = true
  try {
    const response = await getLiveSessions({ page: 1, page_size: 50 })
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

function handleAccountChange() {
  form.symbol = ''
  loadSymbols()
}

async function handleSubmit() {
  const valid = await formRef.value?.validate()
  if (!valid) return

  const confirmed = await confirmDanger(
    '您即将启动实盘交易，这将使用真实资金进行交易。请确认您已了解所有风险。'
  )
  if (!confirmed) return

  const account = selectedAccount.value
  if (!account) return

  submitting.value = true
  try {
    const config = {
      strategy_id: form.strategy_id,
      account_id: form.account_id,
      exchange: account.exchange,
      symbol: form.symbol,
      timeframe: form.timeframe,
      initial_capital: form.initial_capital,
      params: form.params,
      risk_config: form.risk_config,
    }

    const response = await startLiveTrading(config)
    toastSuccess('实盘交易已启动')
    router.push(`/trading/monitor/live/${response.data.id}`)
  } catch (error) {
    toastError('启动失败')
  } finally {
    submitting.value = false
  }
}

function goToMonitor(id: string) {
  router.push(`/trading/monitor/live/${id}`)
}

async function handleStop(id: string) {
  const confirmed = await confirmDanger('确定要停止该实盘交易吗？当前持仓将被保留。')
  if (!confirmed) return

  try {
    await stopLiveTrading(id)
    toastSuccess('已停止')
    loadSessions()
  } catch (error) {
    toastError('停止失败')
  }
}

async function handleEmergencyClose(id: string) {
  const confirmed = await confirmDanger('确定要执行紧急平仓吗？这将立即平掉所有持仓！')
  if (!confirmed) return

  try {
    await emergencyClosePositions(id)
    toastSuccess('紧急平仓执行中')
    loadSessions()
  } catch (error) {
    toastError('执行失败')
  }
}

onMounted(async () => {
  await Promise.all([
    strategyStore.loadStrategies(),
    loadAccounts(),
  ])
  loadSessions()

  if (form.strategy_id) {
    handleStrategyChange()
  }
})
</script>

<style lang="scss" scoped>
.live-trading {
  .page-header {
    margin-bottom: 16px;
  }

  .page-title {
    font-size: 20px;
    font-weight: 600;
  }

  .warning-alert {
    margin-bottom: 24px;
  }

  .live-grid {
    display: grid;
    grid-template-columns: 1fr 400px;
    gap: 24px;
  }

  .account-option {
    display: flex;
    justify-content: space-between;
    align-items: center;
    width: 100%;
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
      gap: 8px;
    }
  }

  .empty-state {
    text-align: center;
    padding: 40px;
    color: #909399;
  }
}
</style>
