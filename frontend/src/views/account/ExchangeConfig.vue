<template>
  <div class="exchange-config">
    <div class="page-header">
      <h1 class="page-title">交易所配置</h1>
      <el-button type="primary" @click="showCreateDialog">
        <el-icon><Plus /></el-icon>
        添加账户
      </el-button>
    </div>

    <div class="accounts-grid" v-loading="loading">
      <div
        v-for="account in accounts"
        :key="account.id"
        class="account-card card"
        :class="{ inactive: !account.is_active }"
      >
        <div class="card-header">
          <div class="header-left">
            <span class="exchange-icon">{{ account.exchange.toUpperCase().charAt(0) }}</span>
            <div class="account-info">
              <h3 class="account-name">{{ account.name }}</h3>
              <span class="exchange-name">{{ formatExchangeName(account.exchange) }}</span>
            </div>
          </div>
          <el-tag :type="account.is_active ? 'success' : 'info'" size="small">
            {{ account.is_active ? '已启用' : '已禁用' }}
          </el-tag>
        </div>

        <div class="account-meta">
          <el-tag v-if="account.testnet" type="warning" size="small">测试网</el-tag>
        </div>

        <div class="account-actions">
          <el-button size="small" @click="testConnection(account)" :loading="testingId === account.id">
            测试连接
          </el-button>
          <el-button size="small" @click="showEditDialog(account)">编辑</el-button>
          <el-button size="small" type="danger" @click="handleDelete(account)">删除</el-button>
        </div>
      </div>
    </div>

    <div v-if="accounts.length === 0 && !loading" class="empty-state card">
      <el-icon class="empty-icon"><Connection /></el-icon>
      <p>暂无交易所账户</p>
      <el-button type="primary" @click="showCreateDialog">添加账户</el-button>
    </div>

    <!-- 创建/编辑账户对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingAccount ? '编辑账户' : '添加账户'"
      width="500px"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="formRules"
        label-position="top"
      >
        <el-form-item label="账户名称" prop="name">
          <el-input v-model="form.name" placeholder="输入账户名称" />
        </el-form-item>

        <el-form-item label="交易所" prop="exchange" v-if="!editingAccount">
          <el-select v-model="form.exchange" style="width: 100%">
            <el-option
              v-for="e in supportedExchanges"
              :key="e.id"
              :label="e.name"
              :value="e.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="API Key" prop="api_key">
          <el-input
            v-model="form.api_key"
            placeholder="输入 API Key"
            show-password
          />
        </el-form-item>

        <el-form-item label="API Secret" prop="api_secret">
          <el-input
            v-model="form.api_secret"
            placeholder="输入 API Secret"
            show-password
          />
        </el-form-item>

        <el-form-item
          v-if="needsPassphrase"
          label="Passphrase"
          prop="passphrase"
        >
          <el-input
            v-model="form.passphrase"
            placeholder="输入 Passphrase"
            show-password
          />
        </el-form-item>

        <el-form-item v-if="!editingAccount">
          <el-checkbox v-model="form.testnet">使用测试网</el-checkbox>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">
          确定
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { formatExchangeName } from '@/utils/format'
import {
  getAccounts,
  getSupportedExchanges,
  createAccount,
  updateAccount,
  deleteAccount,
  testConnection as apiTestConnection,
} from '@/api/account'
import { useNotification } from '@/composables/useNotification'
import type { ExchangeAccount } from '@/types'

const { toastSuccess, toastError, confirmDelete } = useNotification()

const loading = ref(false)
const submitting = ref(false)
const testingId = ref<string | null>(null)
const accounts = ref<ExchangeAccount[]>([])
const supportedExchanges = ref<{ id: string; name: string; has_testnet: boolean }[]>([])
const dialogVisible = ref(false)
const editingAccount = ref<ExchangeAccount | null>(null)
const formRef = ref<FormInstance>()

const form = reactive({
  name: '',
  exchange: 'binance',
  api_key: '',
  api_secret: '',
  passphrase: '',
  testnet: false,
})

const formRules: FormRules = {
  name: [{ required: true, message: '请输入账户名称', trigger: 'blur' }],
  exchange: [{ required: true, message: '请选择交易所', trigger: 'change' }],
  api_key: [{ required: true, message: '请输入 API Key', trigger: 'blur' }],
  api_secret: [{ required: true, message: '请输入 API Secret', trigger: 'blur' }],
}

const needsPassphrase = computed(() => {
  return ['okx', 'bybit'].includes(form.exchange)
})

// 对话框关闭时清理敏感凭证
watch(dialogVisible, (visible) => {
  if (!visible) {
    form.api_key = ''
    form.api_secret = ''
    form.passphrase = ''
  }
})

async function loadAccounts() {
  loading.value = true
  try {
    const response = await getAccounts()
    accounts.value = response.data
  } catch (error) {
    console.error('Failed to load accounts:', error)
  } finally {
    loading.value = false
  }
}

async function loadSupportedExchanges() {
  try {
    const response = await getSupportedExchanges()
    supportedExchanges.value = response.data
  } catch (error) {
    console.error('Failed to load supported exchanges:', error)
  }
}

function showCreateDialog() {
  editingAccount.value = null
  form.name = ''
  form.exchange = 'binance'
  form.api_key = ''
  form.api_secret = ''
  form.passphrase = ''
  form.testnet = false
  dialogVisible.value = true
}

function showEditDialog(account: ExchangeAccount) {
  editingAccount.value = account
  form.name = account.name
  form.exchange = account.exchange
  form.api_key = ''
  form.api_secret = ''
  form.passphrase = ''
  dialogVisible.value = true
}

async function handleSubmit() {
  const valid = await formRef.value?.validate()
  if (!valid) return

  submitting.value = true
  try {
    if (editingAccount.value) {
      const data: Record<string, unknown> = { name: form.name }
      if (form.api_key) data.api_key = form.api_key
      if (form.api_secret) data.api_secret = form.api_secret
      if (form.passphrase) data.passphrase = form.passphrase

      await updateAccount(editingAccount.value.id, data as any)
      toastSuccess('账户已更新')
    } else {
      await createAccount({
        name: form.name,
        exchange: form.exchange,
        api_key: form.api_key,
        api_secret: form.api_secret,
        passphrase: form.passphrase || undefined,
        testnet: form.testnet,
      })
      toastSuccess('账户已添加')
    }

    dialogVisible.value = false
    loadAccounts()
  } catch (error) {
    toastError('操作失败')
  } finally {
    submitting.value = false
  }
}

async function testConnection(account: ExchangeAccount) {
  testingId.value = account.id
  try {
    const response = await apiTestConnection(account.id)
    if (response.data.success) {
      toastSuccess('连接成功')
    } else {
      toastError(response.data.message || '连接失败')
    }
    loadAccounts()
  } catch (error) {
    toastError('连接测试失败')
  } finally {
    testingId.value = null
  }
}

async function handleDelete(account: ExchangeAccount) {
  const confirmed = await confirmDelete('该账户')
  if (!confirmed) return

  try {
    await deleteAccount(account.id)
    toastSuccess('账户已删除')
    loadAccounts()
  } catch (error) {
    toastError('删除失败')
  }
}

onMounted(() => {
  loadAccounts()
  loadSupportedExchanges()
})
</script>

<style lang="scss" scoped>
.exchange-config {
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

  .accounts-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
    gap: 16px;
  }

  .account-card {
    &.inactive {
      opacity: 0.6;
    }

    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 12px;

      .header-left {
        display: flex;
        gap: 12px;
      }

      .exchange-icon {
        width: 48px;
        height: 48px;
        background: linear-gradient(135deg, #1890ff, #096dd9);
        border-radius: 12px;
        display: flex;
        align-items: center;
        justify-content: center;
        color: #fff;
        font-size: 20px;
        font-weight: 700;
      }

      .account-info {
        .account-name {
          font-size: 16px;
          font-weight: 600;
          margin: 0;
        }

        .exchange-name {
          font-size: 12px;
          color: #909399;
        }
      }
    }

    .account-meta {
      display: flex;
      gap: 8px;
      margin-bottom: 12px;
    }

    .account-permissions {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 12px;

      .label {
        font-size: 12px;
        color: #909399;
      }
    }

    .last-connected {
      font-size: 12px;
      color: #909399;
      margin-bottom: 12px;
    }

    .error-message {
      display: flex;
      align-items: center;
      gap: 4px;
      font-size: 12px;
      color: #ff4d4f;
      background: #fff2f0;
      padding: 8px;
      border-radius: 4px;
      margin-bottom: 12px;
    }

    .account-actions {
      display: flex;
      gap: 8px;
      padding-top: 12px;
      border-top: 1px solid #ebeef5;
    }
  }

  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 60px;

    .empty-icon {
      font-size: 48px;
      color: #dcdfe6;
      margin-bottom: 16px;
    }

    p {
      color: #909399;
      margin-bottom: 16px;
    }
  }
}
</style>
