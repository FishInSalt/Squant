<template>
  <div class="asset-overview">
    <div class="page-header">
      <h1 class="page-title">资产概览</h1>
    </div>

    <div class="coming-soon card">
      <el-icon class="coming-soon-icon"><Coin /></el-icon>
      <h2 class="coming-soon-title">功能开发中</h2>
      <p class="coming-soon-desc">资产概览与分布分析功能将在后续版本中提供</p>
      <p class="coming-soon-hint">计划支持：多账户资产汇总、资产分布饼图、持仓明细等功能</p>
      <el-button type="primary" style="margin-top: 20px" @click="goToAccounts">
        前往账户管理
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()

function goToAccounts() {
  router.push('/account/list')
}
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
