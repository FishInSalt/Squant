<template>
  <div class="system-logs">
    <div class="page-header">
      <h1 class="page-title">系统日志</h1>
    </div>
    <ComingSoon
      :icon="Document"
      description="系统日志查看与导出功能将在后续版本中提供"
      hint="计划支持：日志查询、按级别过滤、日志导出等功能"
    />
  </div>
</template>

<script setup lang="ts">
import { Document } from '@element-plus/icons-vue'
import ComingSoon from '@/components/common/ComingSoon.vue'
</script>

<style lang="scss" scoped>
.system-logs {
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
  }

  .page-title {
    font-size: 20px;
    font-weight: 600;
  }
}
</style>
