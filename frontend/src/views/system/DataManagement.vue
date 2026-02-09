<template>
  <div class="data-management">
    <div class="page-header">
      <h1 class="page-title">数据管理</h1>
    </div>
    <ComingSoon
      :icon="DataLine"
      description="历史数据下载与管理功能将在后续版本中提供"
      hint="计划支持：历史K线数据下载、数据管理、数据导出等功能"
    />
  </div>
</template>

<script setup lang="ts">
import { DataLine } from '@element-plus/icons-vue'
import ComingSoon from '@/components/common/ComingSoon.vue'
</script>

<style lang="scss" scoped>
.data-management {
  .page-header {
    margin-bottom: 24px;
  }

  .page-title {
    font-size: 20px;
    font-weight: 600;
  }
}
</style>
