<template>
  <div class="trigger-records">
    <div class="page-header">
      <h1 class="page-title">触发记录</h1>
    </div>

    <div class="filter-bar card">
      <el-form :inline="true" :model="filter">
        <el-form-item label="规则类型">
          <el-select v-model="filter.rule_type" placeholder="全部" clearable style="width: 150px">
            <el-option
              v-for="t in ruleTypeOptions"
              :key="t.value"
              :label="t.label"
              :value="t.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="filter.dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="YYYY-MM-DD"
            style="width: 240px"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadRecords">查询</el-button>
        </el-form-item>
      </el-form>
    </div>

    <div class="records-table card">
      <el-table :data="records" v-loading="loading" stripe>
        <el-table-column prop="time" label="触发时间" width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.time) }}
          </template>
        </el-table-column>

        <el-table-column prop="rule_name" label="规则名称" width="150">
          <template #default="{ row }">
            <span class="rule-name">{{ row.rule_name || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="rule_type" label="规则类型" width="120">
          <template #default="{ row }">
            <el-tag v-if="row.rule_type" size="small" type="info">{{ getRuleTypeLabel(row.rule_type) }}</el-tag>
            <span v-else>{{ row.trigger_type }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="strategy_name" label="策略" width="120">
          <template #default="{ row }">
            {{ row.strategy_name || '-' }}
          </template>
        </el-table-column>

        <el-table-column prop="symbol" label="交易对" width="120">
          <template #default="{ row }">
            {{ row.symbol || '-' }}
          </template>
        </el-table-column>

        <el-table-column label="触发值" width="150">
          <template #default="{ row }">
            <span class="trigger-value">{{ formatTriggerValue(row) }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="message" label="详情" min-width="200">
          <template #default="{ row }">
            {{ row.message || '-' }}
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @size-change="loadRecords"
          @current-change="loadRecords"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { formatDateTime } from '@/utils/format'
import { RISK_RULE_TYPE_OPTIONS } from '@/utils/constants'
import { getRiskTriggers } from '@/api/risk'
import type { RiskTrigger } from '@/types'

const loading = ref(false)
const records = ref<RiskTrigger[]>([])
const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0,
})

const filter = reactive({
  rule_type: '',
  dateRange: [] as string[],
})

const ruleTypeOptions = RISK_RULE_TYPE_OPTIONS

function getRuleTypeLabel(type: string) {
  return ruleTypeOptions.find((t) => t.value === type)?.label || type
}

function formatTriggerValue(row: RiskTrigger) {
  const value = row.details?.trigger_value ?? row.details?.value
  if (value == null) return '-'
  if (typeof value === 'number') {
    return value.toFixed(2)
  }
  return String(value)
}

async function loadRecords() {
  loading.value = true
  try {
    const params: Record<string, unknown> = {
      page: pagination.page,
      page_size: pagination.pageSize,
    }
    if (filter.rule_type) params.rule_type = filter.rule_type
    if (filter.dateRange.length === 2) {
      params.start_date = filter.dateRange[0]
      params.end_date = filter.dateRange[1]
    }

    const response = await getRiskTriggers(params as any)
    records.value = response.data.items
    pagination.total = response.data.total
  } catch (error) {
    console.error('Failed to load records:', error)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadRecords()
})
</script>

<style lang="scss" scoped>
.trigger-records {
  .page-header {
    margin-bottom: 16px;
  }

  .page-title {
    font-size: 20px;
    font-weight: 600;
  }

  .filter-bar {
    margin-bottom: 16px;
    padding: 16px;

    :deep(.el-form-item) {
      margin-bottom: 0;
    }
  }

  .rule-name {
    font-weight: 500;
  }

  .trigger-value {
    color: #ff4d4f;
    font-weight: 500;
  }

  .pagination {
    display: flex;
    justify-content: flex-end;
    margin-top: 16px;
  }
}
</style>
