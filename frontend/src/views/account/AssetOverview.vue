<template>
  <div class="asset-overview">
    <div class="page-header">
      <h1 class="page-title">资产概览</h1>
    </div>
    <ComingSoon
      :icon="Coin"
      description="资产概览与分布分析功能将在后续版本中提供"
      hint="计划支持：多账户资产汇总、资产分布饼图、持仓明细等功能"
    >
      <el-button type="primary" style="margin-top: 20px" @click="goToAccounts">
        前往账户管理
      </el-button>
    </ComingSoon>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { Coin } from '@element-plus/icons-vue'
import ComingSoon from '@/components/common/ComingSoon.vue'

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
}
</style>
