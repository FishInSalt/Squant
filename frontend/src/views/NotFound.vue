<template>
  <div class="not-found">
    <div class="content">
      <h1 class="error-code">404</h1>
      <h2 class="error-title">页面未找到</h2>
      <p class="error-message">抱歉，您访问的页面不存在或已被移除。</p>
      <div class="actions">
        <el-button type="primary" @click="goHome">
          <el-icon><HomeFilled /></el-icon>
          返回首页
        </el-button>
        <el-button @click="goBack">
          <el-icon><Back /></el-icon>
          返回上一页
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()

function goHome() {
  router.push('/')
}

function goBack() {
  router.back()
}
</script>

<style lang="scss" scoped>
.not-found {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: calc(100vh - 200px);

  .content {
    text-align: center;

    .error-code {
      font-size: 120px;
      font-weight: 700;
      color: #dcdfe6;
      margin: 0;
      line-height: 1;
    }

    .error-title {
      font-size: 24px;
      font-weight: 600;
      color: #303133;
      margin: 16px 0;
    }

    .error-message {
      color: #909399;
      margin-bottom: 32px;
    }

    .actions {
      display: flex;
      justify-content: center;
      gap: 16px;
    }
  }
}
</style>
