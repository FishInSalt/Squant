<template>
  <div class="asset-overview">
    <div class="page-header">
      <h1 class="page-title">资产概览</h1>
      <el-button @click="refreshData" :loading="loading">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
    </div>

    <div class="total-value card">
      <div class="value-info">
        <span class="label">总资产估值 (USD)</span>
        <span class="value">${{ formatNumber(overview?.total_usd_value || 0, 2) }}</span>
      </div>
    </div>

    <div class="overview-grid">
      <div class="distribution-panel card">
        <div class="card-header">
          <h3 class="card-title">资产分布</h3>
        </div>
        <PieChart
          v-if="assetDistribution.length > 0"
          :data="assetDistribution"
          height="350px"
        />
        <div v-else class="empty-state">
          <p>暂无资产数据</p>
        </div>
      </div>

      <div class="accounts-panel card">
        <div class="card-header">
          <h3 class="card-title">账户资产</h3>
        </div>
        <div class="accounts-list">
          <div
            v-for="account in overview?.accounts || []"
            :key="account.account_id"
            class="account-item"
          >
            <div class="account-header">
              <div class="account-info">
                <span class="account-name">{{ account.account_name }}</span>
                <el-tag size="small" type="info">{{ formatExchangeName(account.exchange) }}</el-tag>
              </div>
              <span class="account-value">${{ formatNumber(account.total_usd_value, 2) }}</span>
            </div>
            <div class="balance-list">
              <div
                v-for="balance in getTopBalances(account.balances)"
                :key="balance.currency"
                class="balance-item"
              >
                <span class="asset">{{ balance.currency }}</span>
                <span class="amount">{{ formatNumber(balance.total, 6) }}</span>
                <span class="usd-value" v-if="balance.usd_value">
                  ${{ formatNumber(balance.usd_value, 2) }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="details-panel card">
      <div class="card-header">
        <h3 class="card-title">资产明细</h3>
        <el-input
          v-model="searchQuery"
          placeholder="搜索资产..."
          prefix-icon="Search"
          clearable
          style="width: 200px"
        />
      </div>

      <el-table :data="filteredBalances" stripe>
        <el-table-column prop="currency" label="资产" width="100">
          <template #default="{ row }">
            <span class="asset-name">{{ row.currency }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="account_name" label="账户" width="150" />
        <el-table-column prop="exchange" label="交易所" width="100">
          <template #default="{ row }">
            {{ formatExchangeName(row.exchange) }}
          </template>
        </el-table-column>
        <el-table-column prop="available" label="可用" width="150" align="right">
          <template #default="{ row }">
            {{ formatNumber(row.available, 6) }}
          </template>
        </el-table-column>
        <el-table-column prop="frozen" label="冻结" width="150" align="right">
          <template #default="{ row }">
            {{ formatNumber(row.frozen, 6) }}
          </template>
        </el-table-column>
        <el-table-column prop="total" label="总计" width="150" align="right">
          <template #default="{ row }">
            {{ formatNumber(row.total, 6) }}
          </template>
        </el-table-column>
        <el-table-column prop="usd_value" label="USD估值" width="150" align="right">
          <template #default="{ row }">
            {{ row.usd_value ? `$${formatNumber(row.usd_value, 2)}` : '-' }}
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import PieChart from '@/components/charts/PieChart.vue'
import { formatNumber, formatExchangeName } from '@/utils/format'
import { getAssetOverview } from '@/api/account'
import type { AssetOverview, Balance } from '@/types'

const loading = ref(false)
const overview = ref<AssetOverview | null>(null)
const searchQuery = ref('')

const assetDistribution = computed(() => {
  if (!overview.value?.asset_distribution) return []
  return overview.value.asset_distribution.map((d) => ({
    name: d.asset,
    value: d.usd_value,
  }))
})

interface FlatBalance extends Balance {
  account_id: string
  account_name: string
  exchange: string
}

const allBalances = computed<FlatBalance[]>(() => {
  if (!overview.value?.accounts) return []

  const balances: FlatBalance[] = []
  overview.value.accounts.forEach((account) => {
    account.balances.forEach((balance) => {
      balances.push({
        ...balance,
        account_id: account.account_id,
        account_name: account.account_name,
        exchange: account.exchange,
      })
    })
  })

  return balances.sort((a, b) => (b.usd_value || 0) - (a.usd_value || 0))
})

const filteredBalances = computed(() => {
  if (!searchQuery.value) return allBalances.value

  const query = searchQuery.value.toUpperCase()
  return allBalances.value.filter((b) => b.currency.toUpperCase().includes(query))
})

function getTopBalances(balances: Balance[], limit = 5) {
  return [...balances]
    .filter((b) => b.total > 0)
    .sort((a, b) => (b.usd_value || 0) - (a.usd_value || 0))
    .slice(0, limit)
}

async function loadOverview() {
  loading.value = true
  try {
    const response = await getAssetOverview()
    overview.value = response.data
  } catch (error) {
    console.error('Failed to load overview:', error)
  } finally {
    loading.value = false
  }
}

async function refreshData() {
  await loadOverview()
}

onMounted(() => {
  loadOverview()
})
</script>

<style lang="scss" scoped>
.asset-overview {
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

  .total-value {
    margin-bottom: 24px;
    padding: 32px;
    background: linear-gradient(135deg, #1890ff, #096dd9);
    color: #fff;

    .value-info {
      text-align: center;

      .label {
        display: block;
        font-size: 14px;
        opacity: 0.8;
        margin-bottom: 8px;
      }

      .value {
        font-size: 48px;
        font-weight: 600;
      }
    }
  }

  .overview-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px;
    margin-bottom: 24px;
  }

  .accounts-list {
    max-height: 350px;
    overflow-y: auto;
  }

  .account-item {
    padding: 16px;
    background: #f5f7fa;
    border-radius: 8px;
    margin-bottom: 12px;

    &:last-child {
      margin-bottom: 0;
    }

    .account-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;

      .account-info {
        display: flex;
        align-items: center;
        gap: 8px;

        .account-name {
          font-weight: 600;
        }
      }

      .account-value {
        font-size: 18px;
        font-weight: 600;
        color: #1890ff;
      }
    }

    .balance-list {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;

      .balance-item {
        display: flex;
        gap: 4px;
        font-size: 12px;
        background: #fff;
        padding: 4px 8px;
        border-radius: 4px;

        .asset {
          font-weight: 500;
        }

        .amount {
          color: #606266;
        }

        .usd-value {
          color: #909399;
        }
      }
    }
  }

  .details-panel {
    .asset-name {
      font-weight: 500;
    }
  }

  .empty-state {
    display: flex;
    justify-content: center;
    align-items: center;
    height: 350px;
    color: #909399;
  }
}
</style>
