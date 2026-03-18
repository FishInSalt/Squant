<template>
  <div class="session-detail" v-loading="loading">
    <!-- Header -->
    <div class="page-header" v-if="session">
      <div class="header-left">
        <el-button icon="ArrowLeft" @click="goBack">返回</el-button>
        <div class="session-info">
          <h1 class="title">{{ session.strategy_name }}</h1>
          <el-tag size="small" :type="isPaper ? 'info' : 'danger'">
            {{ isPaper ? '模拟' : '实盘' }}
          </el-tag>
          <StatusBadge :status="session.status" />
          <span v-if="runningDuration" class="running-duration">已运行 {{ runningDuration }}</span>
        </div>
      </div>
      <div class="header-right">
        <el-button v-if="isRunning" type="warning" @click="handleStop">停止</el-button>
        <el-button v-if="isRunning && isLive" type="danger" @click="handleEmergencyClose">
          紧急平仓
        </el-button>
        <el-button v-if="canResume" type="primary" @click="handleResume" :loading="resuming">
          恢复
        </el-button>
      </div>
    </div>

    <!-- Error bar -->
    <div v-if="session?.error_message" class="error-bar">
      <el-icon class="error-icon"><CircleCloseFilled /></el-icon>
      <span class="error-message">{{ session.error_message }}</span>
    </div>

    <div v-if="session" class="result-content">
      <!-- Metrics grid -->
      <div v-if="status" class="metrics-section">
        <div class="metrics-grid primary">
          <div class="metric-card card highlight">
            <span class="label">总收益率</span>
            <PriceCell
              :value="totalReturnPct"
              :change="totalReturnPct"
              :decimals="2"
              show-sign
              suffix="%"
              class="value primary-value"
            />
          </div>
          <div class="metric-card card">
            <span class="label">当前权益</span>
            <span class="value">{{ formatNumber(status.equity, 2) }}</span>
          </div>
          <div class="metric-card card">
            <span class="label">可用资金</span>
            <span class="value">{{ formatNumber(status.cash, 2) }}</span>
          </div>
          <div class="metric-card card">
            <span class="label">未实现盈亏</span>
            <PriceCell
              :value="status.unrealized_pnl"
              :change="status.unrealized_pnl"
              show-sign
              class="value"
            />
          </div>
        </div>

        <div class="metrics-grid secondary">
          <div class="metric-card card">
            <span class="label">已实现盈亏</span>
            <PriceCell
              :value="status.realized_pnl"
              :change="status.realized_pnl"
              show-sign
              class="value secondary-value"
            />
          </div>
          <div class="metric-card card">
            <span class="label">总手续费</span>
            <span class="value secondary-value">{{ formatNumber(status.total_fees, 2) }}</span>
          </div>
          <div class="metric-card card">
            <span class="label">最大回撤</span>
            <span class="value secondary-value" :class="maxDrawdownPct != null && maxDrawdownPct < 0 ? 'text-danger' : ''">
              {{ maxDrawdownPct != null ? formatNumber(maxDrawdownPct, 2) + '%' : '-' }}
            </span>
          </div>
          <div class="metric-card card">
            <span class="label">胜率</span>
            <span class="value secondary-value">
              {{ winRate != null ? formatNumber(winRate, 1) + '%' : '-' }}
            </span>
          </div>
        </div>
      </div>

      <!-- Config section (collapsible) -->
      <div class="config-section card">
        <div class="config-header" @click="configExpanded = !configExpanded">
          <div class="config-summary">
            <h3 class="card-title">会话配置</h3>
            <span v-if="!configExpanded" class="config-brief">
              {{ formatExchangeName(session.exchange) }} · {{ session.symbol }} · {{ session.timeframe }}
              · 初始资金 {{ formatNumber(session.initial_capital ?? 0, 2) }}
            </span>
          </div>
          <el-icon class="expand-icon" :class="{ expanded: configExpanded }"><ArrowDown /></el-icon>
        </div>
        <div v-show="configExpanded" class="config-body">
          <el-descriptions :column="4" border>
            <el-descriptions-item label="交易所">{{ formatExchangeName(session.exchange) }}</el-descriptions-item>
            <el-descriptions-item label="交易对">{{ session.symbol }}</el-descriptions-item>
            <el-descriptions-item label="时间周期">{{ session.timeframe }}</el-descriptions-item>
            <el-descriptions-item label="初始资金">{{ formatNumber(session.initial_capital ?? 0, 2) }}</el-descriptions-item>
            <el-descriptions-item label="手续费率">{{ formatNumber((session.commission_rate ?? 0) * 100, 4) }}%</el-descriptions-item>
            <el-descriptions-item label="启动时间">{{ session.started_at ? new Date(session.started_at).toLocaleString('zh-CN') : '-' }}</el-descriptions-item>
            <el-descriptions-item label="停止时间">{{ session.stopped_at ? new Date(session.stopped_at).toLocaleString('zh-CN') : '-' }}</el-descriptions-item>
            <el-descriptions-item v-if="status" label="已处理Bar数">{{ status.bar_count }}</el-descriptions-item>
            <el-descriptions-item v-if="status" label="已完成订单/交易数">
              {{ status.completed_orders_count }} / {{ status.trades_count }}
            </el-descriptions-item>
          </el-descriptions>
          <div v-if="session.params && Object.keys(session.params).length > 0" class="config-params">
            <el-descriptions :column="4" border>
              <el-descriptions-item
                v-for="(value, key) in session.params"
                :key="key"
                :label="String(key)"
              >
                {{ value }}
              </el-descriptions-item>
            </el-descriptions>
          </div>
        </div>
      </div>

      <!-- Waiting for first bar -->
      <div v-if="status && status.bar_count === 0 && isRunning" class="waiting-hint">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>等待第一根K线数据...</span>
      </div>

      <!-- K-line chart -->
      <div class="kline-section card">
        <TradingKLineChart
          :symbol="session.symbol"
          :timeframe="session.timeframe"
          :trades="isPaper ? paperTrades : undefined"
          :fills="isPaper ? paperFills : liveFills"
          :open-trade="isPaper ? paperOpenTrade : liveOpenTrade"
          :realtime="isRunning && !!status?.is_running"
          height="500px"
        />
      </div>

      <!-- Equity curve (always visible) -->
      <div class="equity-section card">
        <div class="card-header">
          <h3 class="card-title">收益曲线</h3>
        </div>
        <EquityCurve :data="equityCurveWithFallback" height="250px" />
      </div>

      <!-- Activity Tabs -->
      <div class="activity-section card">
        <el-tabs v-model="activeTab">
          <el-tab-pane name="positions">
            <template #label>
              持仓
              <el-badge v-if="positions.length" :value="positions.length" class="tab-badge" />
            </template>
            <el-table :data="positionRows" stripe empty-text="暂无持仓">
              <el-table-column prop="symbol" label="币对" min-width="120" />
              <el-table-column prop="side" label="方向" min-width="80">
                <template #default="{ row }">
                  <el-tag
                    :type="row.side === 'long' ? 'success' : row.side === 'short' ? 'danger' : 'info'"
                    size="small"
                  >
                    {{ row.side === 'long' ? '多' : row.side === 'short' ? '空' : '空仓' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="amount" label="数量" min-width="100" align="right">
                <template #default="{ row }">
                  {{ formatNumber(row.amount, 4) }}
                </template>
              </el-table-column>
              <el-table-column prop="avg_entry_price" label="均价" min-width="120" align="right">
                <template #default="{ row }">
                  {{ formatPrice(row.avg_entry_price) }}
                </template>
              </el-table-column>
              <el-table-column prop="current_price" label="现价" min-width="120" align="right">
                <template #default="{ row }">
                  {{ row.current_price != null ? formatPrice(row.current_price) : '-' }}
                </template>
              </el-table-column>
              <el-table-column prop="market_value" label="市值" min-width="120" align="right">
                <template #default="{ row }">
                  {{ row.market_value != null ? formatPrice(row.market_value) : '-' }}
                </template>
              </el-table-column>
              <el-table-column prop="unrealized_pnl" label="未实现盈亏" min-width="140" align="right">
                <template #default="{ row }">
                  <PriceCell
                    v-if="row.unrealized_pnl != null"
                    :value="row.unrealized_pnl"
                    :change="row.unrealized_pnl"
                    show-sign
                  />
                  <span v-else>-</span>
                </template>
              </el-table-column>
              <el-table-column prop="pnl_pct" label="盈亏%" min-width="100" align="right">
                <template #default="{ row }">
                  <PriceCell
                    v-if="row.pnl_pct != null"
                    :value="row.pnl_pct"
                    :change="row.pnl_pct"
                    show-sign
                    suffix="%"
                  />
                  <span v-else>-</span>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane name="orders">
            <template #label>
              挂单
              <el-badge v-if="pendingCount" :value="pendingCount" class="tab-badge" />
            </template>
            <el-table
              v-if="isPaper"
              :data="paperPendingOrders"
              stripe
              empty-text="暂无挂单"
            >
              <el-table-column prop="symbol" label="币对" min-width="120" />
              <el-table-column prop="side" label="方向" min-width="80">
                <template #default="{ row }">
                  <el-tag
                    :type="row.side === 'buy' ? 'success' : 'danger'"
                    size="small"
                  >
                    {{ row.side === 'buy' ? '买入' : '卖出' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="type" label="类型" min-width="90">
                <template #default="{ row }">
                  {{ formatOrderType(row.type) }}
                </template>
              </el-table-column>
              <el-table-column prop="amount" label="数量" min-width="100" align="right">
                <template #default="{ row }">
                  {{ formatNumber(row.amount, 4) }}
                </template>
              </el-table-column>
              <el-table-column prop="price" label="价格" min-width="120" align="right">
                <template #default="{ row }">
                  {{ row.price != null ? formatPrice(row.price) : '市价' }}
                </template>
              </el-table-column>
              <el-table-column prop="status" label="状态" min-width="90">
                <template #default="{ row }">
                  <StatusBadge :status="row.status" context="order" />
                </template>
              </el-table-column>
              <el-table-column prop="created_at" label="创建时间" min-width="140">
                <template #default="{ row }">
                  {{ row.created_at ? formatTradeTime(row.created_at) : '-' }}
                </template>
              </el-table-column>
            </el-table>

            <el-table
              v-else
              :data="liveOrders"
              stripe
              empty-text="暂无挂单"
            >
              <el-table-column prop="symbol" label="币对" min-width="120" />
              <el-table-column prop="side" label="方向" min-width="80">
                <template #default="{ row }">
                  <el-tag
                    :type="row.side === 'buy' ? 'success' : 'danger'"
                    size="small"
                  >
                    {{ row.side === 'buy' ? '买入' : '卖出' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="type" label="类型" min-width="90">
                <template #default="{ row }">
                  {{ formatOrderType(row.type) }}
                </template>
              </el-table-column>
              <el-table-column prop="amount" label="数量" min-width="100" align="right">
                <template #default="{ row }">
                  {{ formatNumber(row.amount, 4) }}
                </template>
              </el-table-column>
              <el-table-column prop="filled_amount" label="已成交" min-width="100" align="right">
                <template #default="{ row }">
                  {{ formatNumber(row.filled_amount, 4) }}
                </template>
              </el-table-column>
              <el-table-column prop="price" label="价格" min-width="120" align="right">
                <template #default="{ row }">
                  {{ row.price != null ? formatPrice(row.price) : '市价' }}
                </template>
              </el-table-column>
              <el-table-column prop="avg_fill_price" label="均价" min-width="120" align="right">
                <template #default="{ row }">
                  {{ row.avg_fill_price != null ? formatPrice(row.avg_fill_price) : '-' }}
                </template>
              </el-table-column>
              <el-table-column prop="status" label="状态" min-width="90">
                <template #default="{ row }">
                  <StatusBadge :status="row.status" context="order" />
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane v-if="isPaper" name="trades">
            <template #label>
              交易记录
              <el-badge v-if="paperTrades.length" :value="paperTrades.length" class="tab-badge" />
            </template>
            <el-table :data="paperTrades" stripe empty-text="暂无交易记录" max-height="400">
              <el-table-column prop="symbol" label="币对" min-width="120" />
              <el-table-column prop="side" label="方向" min-width="70">
                <template #default="{ row }">
                  <el-tag
                    :type="row.side === 'buy' ? 'success' : 'danger'"
                    size="small"
                  >
                    {{ row.side === 'buy' ? '买入' : '卖出' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="entry_time" label="开仓时间" min-width="140">
                <template #default="{ row }">
                  {{ formatTradeTime(row.entry_time) }}
                </template>
              </el-table-column>
              <el-table-column prop="entry_price" label="开仓价" min-width="110" align="right">
                <template #default="{ row }">
                  {{ formatPrice(row.entry_price) }}
                </template>
              </el-table-column>
              <el-table-column prop="exit_time" label="平仓时间" min-width="140">
                <template #default="{ row }">
                  {{ row.exit_time ? formatTradeTime(row.exit_time) : '-' }}
                </template>
              </el-table-column>
              <el-table-column prop="exit_price" label="平仓价" min-width="110" align="right">
                <template #default="{ row }">
                  {{ row.exit_price != null ? formatPrice(row.exit_price) : '-' }}
                </template>
              </el-table-column>
              <el-table-column prop="amount" label="数量" min-width="100" align="right">
                <template #default="{ row }">
                  {{ formatNumber(row.amount, 4) }}
                </template>
              </el-table-column>
              <el-table-column prop="pnl" label="盈亏" min-width="110" align="right">
                <template #default="{ row }">
                  <PriceCell
                    :value="row.pnl"
                    :change="row.pnl"
                    show-sign
                  />
                </template>
              </el-table-column>
              <el-table-column prop="pnl_pct" label="盈亏%" min-width="90" align="right">
                <template #default="{ row }">
                  <PriceCell
                    :value="row.pnl_pct"
                    :change="row.pnl_pct"
                    show-sign
                    suffix="%"
                  />
                </template>
              </el-table-column>
              <el-table-column prop="fees" label="手续费" min-width="90" align="right">
                <template #default="{ row }">
                  {{ formatNumber(row.fees, 4) }}
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane v-if="isPaper" name="fills">
            <template #label>
              成交明细
              <el-badge v-if="paperFills.length" :value="paperFills.length" class="tab-badge" />
            </template>
            <el-table :data="paperFills" stripe empty-text="暂无成交记录" max-height="400">
              <el-table-column prop="timestamp" label="时间" min-width="140">
                <template #default="{ row }">
                  {{ formatTradeTime(row.timestamp) }}
                </template>
              </el-table-column>
              <el-table-column prop="symbol" label="币对" min-width="120" />
              <el-table-column prop="side" label="方向" min-width="70">
                <template #default="{ row }">
                  <el-tag
                    :type="row.side === 'buy' ? 'success' : 'danger'"
                    size="small"
                  >
                    {{ row.side === 'buy' ? '买入' : '卖出' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="price" label="价格" min-width="110" align="right">
                <template #default="{ row }">
                  {{ formatPrice(row.price) }}
                </template>
              </el-table-column>
              <el-table-column prop="amount" label="数量" min-width="100" align="right">
                <template #default="{ row }">
                  {{ formatNumber(row.amount, 4) }}
                </template>
              </el-table-column>
              <el-table-column label="成交额" min-width="120" align="right">
                <template #default="{ row }">
                  {{ formatNumber(row.price * row.amount, 2) }}
                </template>
              </el-table-column>
              <el-table-column prop="fee" label="手续费" min-width="90" align="right">
                <template #default="{ row }">
                  {{ formatNumber(row.fee, 4) }}
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane v-if="isPaper" name="logs">
            <template #label>
              日志
              <el-badge v-if="paperLogs.length" :value="paperLogs.length" class="tab-badge" />
            </template>
            <div class="log-controls">
              <el-switch
                v-model="autoScrollLogs"
                active-text="自动滚动"
                size="small"
              />
            </div>
            <div ref="logContainerRef" class="log-container">
              <div v-for="(log, index) in paperLogs" :key="index" class="log-entry">
                {{ log }}
              </div>
              <div v-if="paperLogs.length === 0" class="empty-logs">暂无日志</div>
            </div>
          </el-tab-pane>

          <el-tab-pane v-if="isLive" name="audit_orders">
            <template #label>
              历史订单
              <el-badge v-if="liveAuditTotal" :value="liveAuditTotal" class="tab-badge" />
            </template>
            <el-table
              v-loading="liveAuditLoading"
              :data="liveAuditOrders"
              stripe
              empty-text="暂无历史订单"
              row-key="id"
            >
              <el-table-column type="expand">
                <template #default="{ row }">
                  <div v-if="row.trades && row.trades.length" class="expand-trades">
                    <el-table :data="row.trades" size="small" :show-header="true">
                      <el-table-column label="时间" min-width="140">
                        <template #default="{ row: trade }">
                          {{ formatTradeTime(trade.timestamp) }}
                        </template>
                      </el-table-column>
                      <el-table-column label="价格" min-width="110" align="right">
                        <template #default="{ row: trade }">
                          {{ formatPrice(trade.price) }}
                        </template>
                      </el-table-column>
                      <el-table-column label="数量" min-width="100" align="right">
                        <template #default="{ row: trade }">
                          {{ formatNumber(trade.amount, 4) }}
                        </template>
                      </el-table-column>
                      <el-table-column label="成交额" min-width="120" align="right">
                        <template #default="{ row: trade }">
                          {{ formatNumber(trade.price * trade.amount, 2) }}
                        </template>
                      </el-table-column>
                      <el-table-column label="手续费" min-width="90" align="right">
                        <template #default="{ row: trade }">
                          {{ formatNumber(trade.fee, 4) }}
                          <span v-if="trade.fee_currency" class="fee-currency">{{ trade.fee_currency }}</span>
                        </template>
                      </el-table-column>
                    </el-table>
                  </div>
                  <div v-else class="expand-empty">暂无成交明细</div>
                </template>
              </el-table-column>
              <el-table-column prop="side" label="方向" min-width="80">
                <template #default="{ row }">
                  <el-tag
                    :type="row.side === 'buy' ? 'success' : 'danger'"
                    size="small"
                  >
                    {{ row.side === 'buy' ? '买入' : '卖出' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="type" label="类型" min-width="90">
                <template #default="{ row }">
                  {{ formatOrderType(row.type) }}
                </template>
              </el-table-column>
              <el-table-column prop="amount" label="委托量" min-width="100" align="right">
                <template #default="{ row }">
                  {{ formatNumber(row.amount, 4) }}
                </template>
              </el-table-column>
              <el-table-column prop="filled" label="已成交" min-width="100" align="right">
                <template #default="{ row }">
                  {{ formatNumber(row.filled, 4) }}
                </template>
              </el-table-column>
              <el-table-column prop="price" label="委托价" min-width="120" align="right">
                <template #default="{ row }">
                  {{ row.price != null ? formatPrice(row.price) : '市价' }}
                </template>
              </el-table-column>
              <el-table-column prop="avg_price" label="均价" min-width="120" align="right">
                <template #default="{ row }">
                  {{ row.avg_price != null ? formatPrice(row.avg_price) : '-' }}
                </template>
              </el-table-column>
              <el-table-column prop="status" label="状态" min-width="90">
                <template #default="{ row }">
                  <StatusBadge :status="row.status" context="order" />
                </template>
              </el-table-column>
              <el-table-column prop="created_at" label="时间" min-width="140">
                <template #default="{ row }">
                  {{ formatTradeTime(row.created_at) }}
                </template>
              </el-table-column>
            </el-table>
            <div v-if="liveAuditTotal > liveAuditPageSize" class="pagination-wrapper">
              <el-pagination
                :current-page="liveAuditPage"
                :page-size="liveAuditPageSize"
                :total="liveAuditTotal"
                layout="total, prev, pager, next"
                @current-change="handleAuditPageChange"
              />
            </div>
          </el-tab-pane>

          <el-tab-pane v-if="isLive" name="risk">
            <template #label>风控</template>
            <div v-if="riskState" class="risk-grid">
              <div class="risk-item">
                <span class="label">日盈亏</span>
                <PriceCell
                  :value="riskState.daily_pnl"
                  :change="riskState.daily_pnl"
                  show-sign
                  class="value"
                />
              </div>
              <div class="risk-item wide">
                <span class="label">日亏损限额</span>
                <el-progress
                  :percentage="dailyLossPercent"
                  :color="riskProgressColor(dailyLossPercent)"
                  :stroke-width="14"
                  :format="() => `${formatNumber(Math.abs(riskState!.daily_pnl), 2)} / ${formatNumber(dailyLossLimitAbs, 2)}`"
                />
              </div>
              <div class="risk-item wide">
                <span class="label">日交易次数</span>
                <el-progress
                  :percentage="dailyTradePercent"
                  :color="riskProgressColor(dailyTradePercent)"
                  :stroke-width="14"
                  :format="() => `${riskState!.daily_trade_count} / ${riskState!.daily_trade_limit}`"
                />
              </div>
              <div class="risk-item">
                <span class="label">连续亏损</span>
                <span class="value">{{ riskState.consecutive_losses }}</span>
              </div>
              <div class="risk-item">
                <span class="label">熔断状态</span>
                <el-tag :type="riskState.circuit_breaker_active ? 'danger' : 'success'" size="small">
                  {{ riskState.circuit_breaker_active ? '已触发' : '正常' }}
                </el-tag>
              </div>
              <div class="risk-item">
                <span class="label">最大持仓比例</span>
                <span class="value">{{ (riskState.max_position_size * 100).toFixed(0) }}%</span>
              </div>
              <div class="risk-item">
                <span class="label">最大下单比例</span>
                <span class="value">{{ (riskState.max_order_size * 100).toFixed(0) }}%</span>
              </div>
            </div>
            <el-empty v-else description="暂无风控数据" :image-size="80" />
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { CircleCloseFilled, ArrowDown, Loading } from '@element-plus/icons-vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import PriceCell from '@/components/common/PriceCell.vue'
import EquityCurve from '@/components/charts/EquityCurve.vue'
import TradingKLineChart from '@/components/charts/TradingKLineChart.vue'
import { formatNumber, formatPrice, formatOrderType, formatExchangeName, formatDuration } from '@/utils/format'
import { getPaperSession, getPaperSessionStatus, stopPaperTrading, getPaperEquityCurve, resumePaperTrading } from '@/api/paper'
import {
  getLiveSession,
  getLiveSessionStatus,
  stopLiveTrading,
  emergencyClosePositions,
  getLiveEquityCurve,
  resumeLiveTrading,
  getLiveSessionOrders,
} from '@/api/live'
import { useWebSocketStore } from '@/stores/websocket'
import { useNotification } from '@/composables/useNotification'
import { confirmStopLive, confirmEmergencyClose, showEmergencyCloseResult, type PositionRow } from '@/composables/useTradingConfirm'
import type {
  PaperSession,
  LiveSession,
  LiveSessionOrder,
  PaperTradingStatus,
  LiveTradingStatus,
  PendingOrderInfo,
  LiveOrderInfo,
  Position,
  RiskState,
  Trade,
  Fill,
  EquityPoint,
  OpenTrade,
} from '@/types'

const props = defineProps<{
  type: 'paper' | 'live'
  id: string
}>()

const router = useRouter()
const wsStore = useWebSocketStore()
const { toastSuccess, toastError, confirmDanger } = useNotification()

const loading = ref(true)
const session = ref<PaperSession | LiveSession | null>(null)
const status = ref<PaperTradingStatus | LiveTradingStatus | null>(null)
const equityCurve = ref<EquityPoint[]>([])

let refreshTimer: ReturnType<typeof setInterval> | null = null
let equityCurvePollCount = 0
let statusInFlight = false

// Running duration timer
const now = ref(Date.now())
let durationTimer: ReturnType<typeof setInterval> | null = null

const isPaper = computed(() => props.type === 'paper')
const isLive = computed(() => props.type === 'live')
const isRunning = computed(() => session.value?.status === 'running')
const canResume = computed(() => {
  const s = session.value?.status
  return s === 'error' || s === 'stopped' || s === 'interrupted'
})
const resuming = ref(false)

// Tabs
const activeTab = ref('positions')

// Config collapse
const configExpanded = ref(false)

// Auto-scroll logs
const autoScrollLogs = ref(true)
const logContainerRef = ref<HTMLElement | null>(null)

// --- Computed: new metrics ---

const totalReturnPct = computed(() => {
  if (!status.value?.initial_capital) return 0
  return ((status.value.equity - status.value.initial_capital) / status.value.initial_capital) * 100
})

const winRate = computed<number | null>(() => {
  if (!isPaper.value) return null
  const trades = paperTrades.value.filter(t => t.exit_time != null)
  if (trades.length === 0) return null
  return (trades.filter(t => t.pnl > 0).length / trades.length) * 100
})

const maxDrawdownPct = computed<number | null>(() => {
  if (equityCurve.value.length < 2) return null
  let peak = equityCurve.value[0].equity
  let maxDd = 0
  for (const p of equityCurve.value) {
    if (p.equity > peak) peak = p.equity
    const dd = (peak - p.equity) / peak * 100
    if (dd > maxDd) maxDd = dd
  }
  return -maxDd
})

const runningDuration = computed(() => {
  if (!session.value?.started_at) return ''
  const start = new Date(session.value.started_at).getTime()
  const end = session.value.stopped_at ? new Date(session.value.stopped_at).getTime() : now.value
  const seconds = Math.floor((end - start) / 1000)
  if (seconds < 0) return ''
  return formatDuration(seconds)
})

// --- Existing computed ---

const positions = computed<[string, Position][]>(() => {
  if (!status.value) return []
  return Object.entries(status.value.positions)
})

const positionRows = computed(() => {
  return positions.value.map(([symbol, pos]) => {
    const marketValue = pos.current_price != null ? pos.amount * pos.current_price : null
    const costBasis = pos.avg_entry_price * pos.amount
    const pnlPct = pos.unrealized_pnl != null && costBasis > 0
      ? (pos.unrealized_pnl / costBasis) * 100
      : null
    return {
      ...pos,
      symbol,
      side: pos.amount > 0 ? 'long' : pos.amount < 0 ? 'short' : 'flat',
      market_value: marketValue,
      pnl_pct: pnlPct,
    }
  })
})

const paperPendingOrders = computed<PendingOrderInfo[]>(() => {
  if (!status.value || !isPaper.value) return []
  return (status.value as PaperTradingStatus).pending_orders || []
})

const liveOrders = computed<LiveOrderInfo[]>(() => {
  if (!status.value || !isLive.value) return []
  return (status.value as LiveTradingStatus).live_orders || []
})

const pendingCount = computed(() => {
  return isPaper.value ? paperPendingOrders.value.length : liveOrders.value.length
})

const paperTrades = computed<Trade[]>(() => {
  if (!status.value || !isPaper.value) return []
  return (status.value as PaperTradingStatus).trades || []
})

const paperFills = computed<Fill[]>(() => {
  if (!status.value || !isPaper.value) return []
  return (status.value as PaperTradingStatus).fills || []
})

const paperOpenTrade = computed(() => {
  if (!status.value || !isPaper.value) return null
  return (status.value as PaperTradingStatus).open_trade ?? null
})

const paperLogs = computed<string[]>(() => {
  if (!status.value || !isPaper.value) return []
  return (status.value as PaperTradingStatus).logs || []
})

// Live session trade markers: accumulate fills from WebSocket events and audit orders
const liveWsFills = ref<Fill[]>([])
const liveOpenTrade = ref<{ entry_time: string; entry_price: number; amount: number } | null>(null)

// Combine fills from audit orders (initial load) with incremental WebSocket fills
const liveAllOrders = ref<LiveSessionOrder[]>([])

const liveFills = computed<Fill[]>(() => {
  if (!isLive.value) return []
  // Build fills from all audit orders (each order has nested trades = fills)
  const auditFills: Fill[] = []
  for (const order of liveAllOrders.value) {
    if (!order.trades || order.trades.length === 0) continue
    for (const trade of order.trades) {
      auditFills.push({
        order_id: order.id,
        symbol: order.symbol,
        side: order.side as 'buy' | 'sell',
        price: trade.price,
        amount: trade.amount,
        fee: trade.fee,
        timestamp: trade.timestamp,
      })
    }
  }
  // Merge with WebSocket fills, deduplicating by timestamp+price+amount
  const seen = new Set(auditFills.map(f => `${f.timestamp}|${f.price}|${f.amount}|${f.side}`))
  const merged = [...auditFills]
  for (const f of liveWsFills.value) {
    const key = `${f.timestamp}|${f.price}|${f.amount}|${f.side}`
    if (!seen.has(key)) {
      merged.push(f)
      seen.add(key)
    }
  }
  return merged
})

// Live audit orders (from DB audit table)
const liveAuditOrders = ref<LiveSessionOrder[]>([])
const liveAuditTotal = ref(0)
const liveAuditPage = ref(1)
const liveAuditPageSize = ref(20)
const liveAuditLoading = ref(false)
const prevCompletedOrdersCount = ref(0)

async function loadLiveAuditOrders() {
  if (!isLive.value) return
  liveAuditLoading.value = true
  try {
    const resp = await getLiveSessionOrders(props.id, {
      page: liveAuditPage.value,
      page_size: liveAuditPageSize.value,
    })
    liveAuditOrders.value = resp.data.items
    liveAuditTotal.value = resp.data.total
  } catch {
    // non-critical, don't block UI
  } finally {
    liveAuditLoading.value = false
  }
}

function handleAuditPageChange(page: number) {
  liveAuditPage.value = page
  loadLiveAuditOrders()
}

// Load all audit orders (unpaginated) for chart fill markers
async function loadAllLiveOrders() {
  if (!isLive.value) return
  try {
    const resp = await getLiveSessionOrders(props.id, { page: 1, page_size: 500 })
    liveAllOrders.value = resp.data.items
  } catch {
    // non-critical
  }
}

const riskState = computed<RiskState | null>(() => {
  if (!status.value || !isLive.value) return null
  return (status.value as LiveTradingStatus).risk_state || null
})

const dailyLossLimitAbs = computed(() =>
  (riskState.value?.daily_loss_limit ?? 0) * (status.value?.initial_capital ?? 0))

const dailyLossPercent = computed(() =>
  dailyLossLimitAbs.value ? Math.min(100, (Math.abs(riskState.value!.daily_pnl) / dailyLossLimitAbs.value) * 100) : 0)

const dailyTradePercent = computed(() =>
  riskState.value?.daily_trade_limit ? Math.min(100, (riskState.value.daily_trade_count / riskState.value.daily_trade_limit) * 100) : 0)

function riskProgressColor(pct: number): string {
  if (pct >= 90) return '#F56C6C'
  if (pct >= 70) return '#E6A23C'
  return '#67C23A'
}

// Equity curve fallback: always show at least a flat line
const equityCurveWithFallback = computed<EquityPoint[]>(() => {
  if (equityCurve.value.length > 0) return equityCurve.value
  const ic = status.value?.initial_capital ?? session.value?.initial_capital ?? 10000
  const t = session.value?.started_at ?? new Date().toISOString()
  return [
    { time: t, equity: ic, cash: ic, position_value: 0, unrealized_pnl: 0 },
    { time: new Date().toISOString(), equity: ic, cash: ic, position_value: 0, unrealized_pnl: 0 },
  ]
})

// --- WebSocket trading status ---

const wsChannel = computed(() => `trading:${props.id}`)

function handleTradingEvent(data: Record<string, unknown>) {
  if (!status.value) return
  const eventType = data.event as string

  if (eventType === 'bar_update') {
    // Replace scalar metrics
    status.value.bar_count = data.bar_count as number
    status.value.cash = parseFloat(data.cash as string)
    status.value.equity = parseFloat(data.equity as string)
    status.value.unrealized_pnl = parseFloat(data.unrealized_pnl as string)
    status.value.realized_pnl = parseFloat(data.realized_pnl as string)
    status.value.total_fees = parseFloat(data.total_fees as string)
    status.value.completed_orders_count = data.completed_orders_count as number
    status.value.trades_count = data.trades_count as number

    // Parse positions: convert string amounts to numbers
    const rawPositions = data.positions as Record<string, { amount: string; avg_entry_price: string }> | undefined
    if (rawPositions) {
      const parsed: Record<string, Position> = {}
      for (const [sym, pos] of Object.entries(rawPositions)) {
        parsed[sym] = {
          amount: parseFloat(pos.amount),
          avg_entry_price: parseFloat(pos.avg_entry_price),
        }
      }
      status.value.positions = parsed
    }

    // Replace pending orders
    status.value.pending_orders = (data.pending_orders as PendingOrderInfo[]) || []

    // Replace open trade
    if (isPaper.value) {
      const ps = status.value as PaperTradingStatus
      ps.open_trade = data.open_trade as OpenTrade | undefined
    } else if (isLive.value) {
      const ot = data.open_trade as OpenTrade | undefined
      liveOpenTrade.value = ot ? { entry_time: ot.entry_time, entry_price: ot.entry_price, amount: ot.amount } : null
    }

    // Append incremental data
    if (isPaper.value) {
      const ps = status.value as PaperTradingStatus
      const newFills = data.new_fills as Fill[] | undefined
      if (Array.isArray(newFills) && newFills.length && ps.fills) {
        ps.fills.push(...newFills)
      }
      const newTrades = data.new_trades as Trade[] | undefined
      if (Array.isArray(newTrades) && newTrades.length && ps.trades) {
        ps.trades.push(...newTrades)
      }
      const newLogs = data.new_logs as string[] | undefined
      if (Array.isArray(newLogs) && newLogs.length && ps.logs) {
        ps.logs.push(...newLogs)
      }
    } else if (isLive.value) {
      // Accumulate live fills for chart markers
      const newFills = data.new_fills as Fill[] | undefined
      if (Array.isArray(newFills) && newFills.length) {
        liveWsFills.value.push(...newFills)
      }
    }

    if (data.risk_state) {
      (status.value as LiveTradingStatus).risk_state = data.risk_state as RiskState
    }

    // Auto-refresh audit orders when new orders complete
    const newCount = data.completed_orders_count as number
    if (isLive.value && newCount > prevCompletedOrdersCount.value) {
      loadLiveAuditOrders()
      loadAllLiveOrders()
    }
    prevCompletedOrdersCount.value = newCount

    // Trigger incremental equity curve load
    loadEquityCurve(true)
  } else if (eventType === 'fill') {
    // Real-time fill event: update scalar state immediately (no fills list append —
    // authoritative fills list comes via bar_update's new_fills at bar close)
    status.value.cash = parseFloat(data.cash as string)
    status.value.equity = parseFloat(data.equity as string)
    status.value.unrealized_pnl = parseFloat(data.unrealized_pnl as string)

    const rawPositions = data.positions as Record<string, { amount: string; avg_entry_price: string }> | undefined
    if (rawPositions) {
      const parsed: Record<string, Position> = {}
      for (const [sym, pos] of Object.entries(rawPositions)) {
        parsed[sym] = {
          amount: parseFloat(pos.amount),
          avg_entry_price: parseFloat(pos.avg_entry_price),
        }
      }
      status.value.positions = parsed
    }

    status.value.pending_orders = (data.pending_orders as PendingOrderInfo[]) || []

    if (isPaper.value) {
      const ps = status.value as PaperTradingStatus
      ps.open_trade = data.open_trade as OpenTrade | undefined
    } else if (isLive.value) {
      const ot = data.open_trade as OpenTrade | undefined
      liveOpenTrade.value = ot ? { entry_time: ot.entry_time, entry_price: ot.entry_price, amount: ot.amount } : null
    }
  } else if (eventType === 'engine_stopped') {
    status.value.is_running = false
    if (data.error_message) {
      status.value.error_message = data.error_message as string
    }
    // Refresh session to get final DB state
    loadSession()
    // Reload audit orders for final state
    if (isLive.value) {
      loadLiveAuditOrders()
    }
    unsubscribeTradingChannel()
  }
}

function subscribeTradingChannel() {
  wsStore.subscribe(wsChannel.value)
  wsStore.onTradingStatus(props.id, handleTradingEvent)
}

function unsubscribeTradingChannel() {
  wsStore.offTradingStatus(props.id, handleTradingEvent)
  wsStore.unsubscribe(wsChannel.value)
}

function formatTradeTime(time: string): string {
  return new Date(time).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

// Auto-scroll logs only when logs tab is visible
watch(paperLogs, () => {
  if (autoScrollLogs.value && logContainerRef.value && activeTab.value === 'logs') {
    nextTick(() => {
      logContainerRef.value!.scrollTop = logContainerRef.value!.scrollHeight
    })
  }
})

async function loadSession() {
  try {
    loading.value = true
    const response = isPaper.value
      ? await getPaperSession(props.id)
      : await getLiveSession(props.id)
    session.value = response.data
    loadEquityCurve()
  } catch (error) {
    console.error('Failed to load session:', error)
    toastError('加载会话失败')
  } finally {
    loading.value = false
  }
}

function mapEquityPoint(d: any): EquityPoint {
  return {
    time: d.time,
    equity: d.equity,
    cash: d.cash ?? 0,
    position_value: d.position_value ?? 0,
    unrealized_pnl: d.unrealized_pnl ?? 0,
  }
}

async function loadEquityCurve(incremental = false) {
  try {
    // Incremental: only fetch new points since the last known time
    const since = incremental && equityCurve.value.length > 0
      ? equityCurve.value[equityCurve.value.length - 1].time
      : undefined
    const response = isPaper.value
      ? await getPaperEquityCurve(props.id, since)
      : await getLiveEquityCurve(props.id, since)
    const newPoints = response.data.map(mapEquityPoint)
    if (since && newPoints.length > 0) {
      equityCurve.value = [...equityCurve.value, ...newPoints]
    } else if (!since) {
      equityCurve.value = newPoints
    }
  } catch {
    // equity curve is optional, don't block UI
  }
}

async function loadStatus() {
  if (statusInFlight) return // skip if previous poll still pending
  statusInFlight = true
  try {
    const response = isPaper.value
      ? await getPaperSessionStatus(props.id)
      : await getLiveSessionStatus(props.id)
    status.value = response.data

    // Refresh equity curve every 2 polls (~6s), incremental after initial load
    equityCurvePollCount++
    if (equityCurvePollCount % 2 === 0) {
      loadEquityCurve(true)
    }

    if (!status.value.is_running) {
      stopPolling()
      // Reload session to get latest DB status
      try {
        const sessionResp = isPaper.value
          ? await getPaperSession(props.id)
          : await getLiveSession(props.id)
        session.value = sessionResp.data
      } catch { /* ignore refresh failure */ }

      // If session is in a recoverable state (interrupted), keep checking
      // at a lower frequency so we detect auto-recovery without page refresh
      if (session.value?.status === 'interrupted') {
        startRecoveryPolling()
      }
    } else if (!wsStore.connected) {
      // Defense-in-depth: session is running but WebSocket disconnected
      // (e.g., after backend restart with graceful close code).
      // Trigger immediate reconnect so real-time data resumes promptly.
      wsStore.reconnectNow()
    }
  } catch (error) {
    console.error('Failed to load status:', error)
  } finally {
    statusInFlight = false
  }
}

async function checkRecovery() {
  try {
    const sessionResp = isPaper.value
      ? await getPaperSession(props.id)
      : await getLiveSession(props.id)
    session.value = sessionResp.data

    if (session.value?.status === 'running') {
      // Session recovered — switch back to normal status polling
      stopRecoveryPolling()
      await loadStatus()
      startPolling()
    } else if (session.value?.status !== 'interrupted') {
      // Terminal state (error/stopped) — stop checking
      stopRecoveryPolling()
    }
  } catch {
    // Backend may still be restarting, keep trying
  }
}

let recoveryTimer: ReturnType<typeof setInterval> | null = null

function startPolling() {
  if (refreshTimer) return
  // Use 30s fallback polling when WebSocket is active (was 3s before WS support)
  refreshTimer = setInterval(loadStatus, 30000)
}

function stopPolling() {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

function startRecoveryPolling() {
  if (recoveryTimer) return
  recoveryTimer = setInterval(checkRecovery, 5000)
}

function stopRecoveryPolling() {
  if (recoveryTimer) {
    clearInterval(recoveryTimer)
    recoveryTimer = null
  }
}

function goBack() {
  router.push('/trading/monitor')
}

async function handleStop() {
  if (isPaper.value) {
    const confirmed = await confirmDanger('确定要停止该模拟交易吗？')
    if (!confirmed) return
    try {
      await stopPaperTrading(props.id)
      toastSuccess('已停止')
      unsubscribeTradingChannel()
      stopPolling()
      await loadSession()
    } catch (error) {
      toastError('停止失败')
    }
  } else {
    const { confirmed, cancelOrders } = await confirmStopLive()
    if (!confirmed) return
    try {
      await stopLiveTrading(props.id, cancelOrders)
      toastSuccess(cancelOrders ? '已停止，挂单已取消' : '已停止，挂单已保留')
      unsubscribeTradingChannel()
      stopPolling()
      await loadSession()
    } catch (error) {
      toastError('停止失败')
    }
  }
}

async function handleResume() {
  resuming.value = true
  try {
    let resumeMsg = '已恢复'
    if (isPaper.value) {
      const resp = await resumePaperTrading(props.id)
      if (resp.message && resp.message !== 'success') resumeMsg = resp.message
    } else {
      const resp = await resumeLiveTrading(props.id)
      if (resp.message && resp.message !== 'success') resumeMsg = resp.message
    }
    toastSuccess(resumeMsg)
    await loadSession()
    await loadStatus()
    subscribeTradingChannel()
    startPolling()
  } catch (error: any) {
    toastError(error?.response?.data?.message || '恢复失败')
  } finally {
    resuming.value = false
  }
}

async function handleEmergencyClose() {
  const rows: PositionRow[] = positionRows.value
    .filter((p) => p.amount !== 0)
    .map((p) => ({
      symbol: p.symbol,
      side: p.side,
      amount: p.amount,
      avg_entry_price: p.avg_entry_price,
    }))

  const confirmed = await confirmEmergencyClose(rows, true)
  if (!confirmed) return

  try {
    const resp = await emergencyClosePositions(props.id)
    showEmergencyCloseResult(resp.data)
    stopPolling()
    await loadSession()
    await loadStatus()
  } catch (error) {
    toastError('执行失败')
  }
}

onMounted(async () => {
  await loadSession()
  // Always load status (backend returns historical data from DB for stopped sessions)
  await loadStatus()
  // Init counter for auto-refresh tracking
  prevCompletedOrdersCount.value = status.value?.completed_orders_count ?? 0
  // Load audit orders for live sessions
  if (isLive.value) {
    loadLiveAuditOrders()
    loadAllLiveOrders()
  }
  if (isRunning.value && status.value?.is_running) {
    // Subscribe to WebSocket for real-time updates + fallback polling (30s)
    subscribeTradingChannel()
    startPolling()
  } else if (session.value?.status === 'interrupted') {
    // Session interrupted (e.g. backend restarting) — poll for recovery
    startRecoveryPolling()
  }
  // Start duration timer
  durationTimer = setInterval(() => {
    now.value = Date.now()
  }, 1000)
})

onUnmounted(() => {
  unsubscribeTradingChannel()
  stopPolling()
  stopRecoveryPolling()
  if (durationTimer) {
    clearInterval(durationTimer)
    durationTimer = null
  }
})
</script>

<style lang="scss" scoped>
.session-detail {
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

    .session-info {
      display: flex;
      align-items: center;
      gap: 12px;

      .title {
        font-size: 24px;
        font-weight: 600;
        margin: 0;
      }

      .running-duration {
        font-size: 13px;
        color: #909399;
      }
    }

    .header-right {
      display: flex;
      gap: 12px;
    }
  }

  .error-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 16px;
    margin-bottom: 16px;
    background: #fff2f0;
    border: 1px solid #ffccc7;
    border-radius: 4px;

    .error-icon {
      font-size: 16px;
      color: #ff4d4f;
      flex-shrink: 0;
    }

    .error-message {
      color: #ff4d4f;
      word-break: break-word;
    }
  }

  .metrics-section {
    margin-bottom: 24px;
  }

  .metrics-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;

    &.primary {
      margin-bottom: 16px;
    }

    &.secondary {
      margin-bottom: 0;
    }
  }

  .metric-card {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 20px;

    &.highlight {
      border-left: 3px solid #409eff;
    }

    .label {
      font-size: 12px;
      color: #909399;
    }

    .value {
      font-size: 24px;
      font-weight: 600;

      &.primary-value {
        font-size: 28px;
      }

      &.secondary-value {
        font-size: 18px;
      }
    }

    .text-danger {
      color: #FF1744;
    }
  }

  .config-section {
    margin-bottom: 24px;

    .config-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      cursor: pointer;
      padding: 16px 20px;

      .config-summary {
        display: flex;
        align-items: center;
        gap: 12px;

        .card-title {
          margin: 0;
          font-size: 16px;
          font-weight: 600;
        }

        .config-brief {
          font-size: 13px;
          color: #909399;
        }
      }

      .expand-icon {
        transition: transform 0.3s;
        color: #909399;

        &.expanded {
          transform: rotate(180deg);
        }
      }
    }

    .config-body {
      padding: 0 20px 16px;
    }

    .config-params {
      margin-top: 12px;
    }
  }

  .waiting-hint {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 24px;
    margin-bottom: 24px;
    color: #909399;
    font-size: 14px;
  }

  .kline-section {
    margin-bottom: 24px;
    padding: 16px;
  }

  .equity-section {
    margin-bottom: 24px;
  }

  .activity-section {
    margin-bottom: 24px;
    padding: 0 16px 16px;

    :deep(.el-tabs__header) {
      margin-bottom: 16px;
    }

    .tab-badge {
      margin-left: 4px;
      vertical-align: middle;

      :deep(.el-badge__content) {
        height: 16px;
        line-height: 16px;
        padding: 0 5px;
        font-size: 11px;
      }
    }
  }

  .log-controls {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 8px;
  }

  .log-container {
    max-height: 300px;
    overflow-y: auto;
    background: #fafafa;
    border-radius: 4px;
    padding: 12px;
    font-family: Consolas, Monaco, 'Courier New', monospace;
    font-size: 12px;
    line-height: 1.6;
  }

  .log-entry {
    padding: 2px 0;
    color: #606266;
    word-break: break-all;
  }

  .empty-logs {
    color: #c0c4cc;
    text-align: center;
    padding: 24px 0;
  }

  .expand-trades {
    padding: 8px 16px;
  }

  .expand-empty {
    padding: 12px 16px;
    color: #c0c4cc;
    font-size: 13px;
  }

  .fee-currency {
    font-size: 11px;
    color: #909399;
    margin-left: 2px;
  }

  .pagination-wrapper {
    display: flex;
    justify-content: flex-end;
    margin-top: 12px;
  }

  .risk-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    padding: 16px 0;
  }

  .risk-item {
    display: flex;
    flex-direction: column;
    gap: 8px;

    &.wide {
      grid-column: span 2;
    }

    .label {
      font-size: 12px;
      color: #909399;
    }

    .value {
      font-size: 18px;
      font-weight: 500;
    }
  }
}
</style>
