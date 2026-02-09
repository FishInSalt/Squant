<template>
  <div class="system-logs">
    <div class="page-header">
      <h1 class="page-title">系统日志</h1>
    </div>

    <div class="coming-soon card">
      <el-icon class="coming-soon-icon"><Document /></el-icon>
      <h2 class="coming-soon-title">功能开发中</h2>
      <p class="coming-soon-desc">系统日志查看与导出功能将在后续版本中提供</p>
      <p class="coming-soon-hint">计划支持：日志查询、按级别过滤、日志导出等功能</p>
    </div>
  </div>
</template>

<script setup lang="ts">
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

  .coming-soon {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 80px 40px;
    text-align: center;

    .coming-soon-icon {
      font-size: 64px;
      color: #dcdfe6;
      margin-bottom: 24px;
    }

    .coming-soon-title {
      font-size: 20px;
      font-weight: 600;
      color: #303133;
      margin: 0 0 12px;
    }

    .coming-soon-desc {
      font-size: 14px;
      color: #606266;
      margin: 0 0 8px;
    }

    .coming-soon-hint {
      font-size: 13px;
      color: #909399;
      margin: 0;
    }
  }
}
</style>
