<template>
  <div class="strategy-upload">
    <div class="page-header">
      <h1 class="page-title">上传策略</h1>
    </div>

    <div class="upload-container card">
      <el-upload
        ref="uploadRef"
        class="upload-dragger"
        drag
        :auto-upload="false"
        :limit="1"
        accept=".py"
        :on-change="handleFileChange"
        :on-exceed="handleExceed"
      >
        <el-icon class="upload-icon"><UploadFilled /></el-icon>
        <div class="upload-text">
          将策略文件拖拽到此处，或<em>点击上传</em>
        </div>
        <div class="upload-tip">
          仅支持 .py 文件，文件大小不超过 1MB
        </div>
      </el-upload>

      <div v-if="selectedFile" class="file-info">
        <el-icon><Document /></el-icon>
        <span class="file-name">{{ selectedFile.name }}</span>
        <span class="file-size">{{ formatFileSize(selectedFile.size) }}</span>
        <el-button type="danger" link @click="clearFile">
          <el-icon><Delete /></el-icon>
        </el-button>
      </div>

      <div class="upload-actions">
        <el-button
          type="primary"
          size="large"
          :loading="uploading"
          :disabled="!selectedFile"
          @click="handleUpload"
        >
          {{ uploading ? `上传中 ${uploadProgress}%` : '上传并验证' }}
        </el-button>
      </div>
    </div>

    <div v-if="validationResult" class="validation-result card">
      <div class="result-header">
        <h3>
          <el-icon :class="validationResult.valid ? 'success' : 'error'">
            <CircleCheckFilled v-if="validationResult.valid" />
            <CircleCloseFilled v-else />
          </el-icon>
          {{ validationResult.valid ? '验证通过' : '验证失败' }}
        </h3>
      </div>

      <div v-if="validationResult.strategy_info" class="strategy-info">
        <div class="info-item">
          <span class="label">策略名称:</span>
          <span class="value">{{ validationResult.strategy_info.name }}</span>
        </div>
        <div class="info-item">
          <span class="label">类名:</span>
          <span class="value">{{ validationResult.strategy_info.class_name }}</span>
        </div>
      </div>

      <div v-if="validationResult.errors.length > 0" class="error-list">
        <h4>错误信息</h4>
        <div
          v-for="(error, index) in validationResult.errors"
          :key="index"
          class="error-item"
        >
          <el-icon class="error"><CircleCloseFilled /></el-icon>
          <span v-if="error.line">第 {{ error.line }} 行: </span>
          {{ error.message }}
        </div>
      </div>

      <div v-if="validationResult.warnings.length > 0" class="warning-list">
        <h4>警告信息</h4>
        <div
          v-for="(warning, index) in validationResult.warnings"
          :key="index"
          class="warning-item"
        >
          <el-icon class="warning"><WarningFilled /></el-icon>
          <span v-if="warning.line">第 {{ warning.line }} 行: </span>
          {{ warning.message }}
        </div>
      </div>

      <div v-if="uploadedStrategyId" class="result-actions">
        <el-button type="primary" @click="goToDetail">
          查看策略详情
        </el-button>
        <el-button @click="goToBacktest">
          开始回测
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import type { UploadInstance, UploadFile } from 'element-plus'
import { createStrategy, validateStrategy } from '@/api/strategy'
import { formatFileSize } from '@/utils/format'
import { useNotification } from '@/composables/useNotification'
import type { ValidationResult } from '@/types'

const router = useRouter()
const { toastSuccess, toastError } = useNotification()

const uploadRef = ref<UploadInstance>()
const selectedFile = ref<File | null>(null)
const uploading = ref(false)
const uploadProgress = ref(0)
const validationResult = ref<ValidationResult | null>(null)
const uploadedStrategyId = ref<string | null>(null)

function handleFileChange(uploadFile: UploadFile) {
  if (uploadFile.raw) {
    selectedFile.value = uploadFile.raw
    validationResult.value = null
    uploadedStrategyId.value = null
  }
}

function handleExceed() {
  toastError('只能上传一个文件')
}

function clearFile() {
  selectedFile.value = null
  validationResult.value = null
  uploadedStrategyId.value = null
  uploadRef.value?.clearFiles()
}

async function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = () => reject(reader.error)
    reader.readAsText(file)
  })
}

async function handleUpload() {
  if (!selectedFile.value) return

  uploading.value = true
  uploadProgress.value = 0

  try {
    // 读取文件内容为文本
    const code = await readFileAsText(selectedFile.value)
    uploadProgress.value = 30

    // 先验证策略代码
    const validateResponse = await validateStrategy(code)
    uploadProgress.value = 60
    validationResult.value = validateResponse.data

    if (!validationResult.value.valid) {
      toastError('策略验证失败，请检查错误信息')
      return
    }

    // 验证通过，创建策略
    const name = selectedFile.value.name.replace(/\.py$/, '')
    const createResponse = await createStrategy({ name, code })
    uploadProgress.value = 100
    uploadedStrategyId.value = createResponse.data.id

    toastSuccess('策略上传成功')
  } catch (error) {
    toastError('上传失败，请重试')
  } finally {
    uploading.value = false
  }
}

function goToDetail() {
  if (uploadedStrategyId.value) {
    router.push(`/strategy/${uploadedStrategyId.value}`)
  }
}

function goToBacktest() {
  if (uploadedStrategyId.value) {
    router.push({
      path: '/trading/backtest',
      query: { strategy_id: uploadedStrategyId.value },
    })
  }
}
</script>

<style lang="scss" scoped>
.strategy-upload {
  max-width: 800px;
  margin: 0 auto;

  .page-header {
    margin-bottom: 24px;
  }

  .page-title {
    font-size: 20px;
    font-weight: 600;
  }

  .upload-container {
    padding: 32px;

    .upload-dragger {
      width: 100%;

      :deep(.el-upload-dragger) {
        width: 100%;
        padding: 40px;
      }
    }

    .upload-icon {
      font-size: 48px;
      color: #c0c4cc;
      margin-bottom: 16px;
    }

    .upload-text {
      font-size: 16px;
      color: #606266;

      em {
        color: #1890ff;
        font-style: normal;
      }
    }

    .upload-tip {
      font-size: 12px;
      color: #909399;
      margin-top: 8px;
    }

    .file-info {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-top: 16px;
      padding: 12px;
      background: #f5f7fa;
      border-radius: 4px;

      .file-name {
        flex: 1;
        font-weight: 500;
      }

      .file-size {
        color: #909399;
        font-size: 12px;
      }
    }

    .upload-actions {
      margin-top: 24px;
      text-align: center;
    }
  }

  .validation-result {
    margin-top: 24px;
    padding: 24px;

    .result-header {
      margin-bottom: 16px;

      h3 {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 18px;
        margin: 0;

        .success {
          color: #4caf50;
        }

        .error {
          color: #ff4d4f;
        }
      }
    }

    .strategy-info {
      background: #f5f7fa;
      padding: 16px;
      border-radius: 4px;
      margin-bottom: 16px;

      .info-item {
        display: flex;
        gap: 8px;
        margin-bottom: 8px;

        &:last-child {
          margin-bottom: 0;
        }

        .label {
          color: #909399;
          width: 80px;
        }

        .value {
          font-weight: 500;
        }
      }
    }

    .error-list,
    .warning-list {
      margin-bottom: 16px;

      h4 {
        font-size: 14px;
        margin: 0 0 8px;
      }

      .error-item,
      .warning-item {
        display: flex;
        align-items: flex-start;
        gap: 8px;
        padding: 8px 12px;
        border-radius: 4px;
        margin-bottom: 8px;
        font-size: 14px;

        &:last-child {
          margin-bottom: 0;
        }
      }

      .error-item {
        background: #fff2f0;
        color: #ff4d4f;
      }

      .warning-item {
        background: #fffbe6;
        color: #faad14;
      }
    }

    .result-actions {
      display: flex;
      gap: 12px;
      margin-top: 24px;
      padding-top: 16px;
      border-top: 1px solid #ebeef5;
    }
  }
}
</style>
