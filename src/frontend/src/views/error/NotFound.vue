<template>
  <div class="not-found-page">
    <h1>404</h1>
    <p>页面不存在</p>
    <el-button type="primary" @click="$router.push('/')">返回首页</el-button>
  </div>
</template>

<script setup lang="ts">
// 404 页面
</script>

<style scoped lang="scss">
.not-found-page {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100vh;

  h1 {
    font-size: 120px;
    color: #409eff;
    margin: 0;
  }

  p {
    font-size: 18px;
    color: #606266;
    margin-bottom: 24px;
  }
}
</style>
