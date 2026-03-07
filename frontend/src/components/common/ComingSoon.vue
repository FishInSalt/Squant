<template>
  <div class="coming-soon card">
    <el-icon class="coming-soon-icon">
      <component :is="icon" />
    </el-icon>
    <h2 class="coming-soon-title">功能开发中</h2>
    <p class="coming-soon-desc">{{ description }}</p>
    <p v-if="hint" class="coming-soon-hint">{{ hint }}</p>
    <slot />
  </div>
</template>

<script setup lang="ts">
import type { Component } from 'vue'

defineProps<{
  icon: Component
  description: string
  hint?: string
}>()
</script>

<style lang="scss" scoped>
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
</style>
