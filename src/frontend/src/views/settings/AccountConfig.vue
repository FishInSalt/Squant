<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import type { ExchangeAccount, AccountFormData } from '@/types/account'
import { getAccounts, createAccount, updateAccount, deleteAccount, validateAccount } from '@/api/account'
import { EXCHANGES } from '@/types/account'

// ========== 状态 ==========
const accounts = ref<ExchangeAccount[]>([])
const dialogVisible = ref(false)
const dialogType = ref<'create' | 'edit'>('create')
const formRef = ref<FormInstance>()
const loading = ref(false)
const submitLoading = ref(false)
const testLoading = ref<number | null>(null)

// 当前编辑的账户ID
const currentAccountId = ref<number>(0)

// 表单数据
const formData = ref<AccountFormData>({
  name: '',
  exchange: 'BINANCE',
  apiKey: '',
  apiSecret: '',
  passphrase: '',
  isDemo: false
})

// 表单验证规则
const rules: FormRules = {
  name: [
    { required: true, message: '请输入账户名称', trigger: 'blur' }
  ],
  exchange: [
    { required: true, message: '请选择交易所', trigger: 'change' }
  ],
  apiKey: [
    { required: true, message: '请输入 API Key', trigger: 'blur' }
  ],
  apiSecret: [
    { required: true, message: '请输入 API Secret', trigger: 'blur' }
  ],
  passphrase: [
    {
      required: false,
      message: '请输入 Passphrase',
      trigger: 'blur',
      validator: (_rule, value, callback) => {
        const exchange = formData.value.exchange
        if (exchange === 'OKX' && !value) {
          callback(new Error('OKX 需要 Passphrase'))
        } else {
          callback()
        }
      }
    }
  ]
}

// ========== 方法 ==========

/**
 * 格式化日期时间
 */
const formatDate = (dateStr: string | null | undefined): string => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

/**
 * 加载账户列表
 */
const loadAccounts = async () => {
  loading.value = true
  try {
    const data = await getAccounts()
    accounts.value = data
  } catch (error: any) {
    console.error('Failed to load accounts:', error)
  } finally {
    loading.value = false
  }
}

/**
 * 添加账户
 */
const handleAdd = () => {
  dialogType.value = 'create'
  currentAccountId.value = 0
  formData.value = {
    name: '',
    exchange: 'BINANCE',
    apiKey: '',
    apiSecret: '',
    passphrase: '',
    isDemo: false
  }
  dialogVisible.value = true
}

/**
 * 编辑账户
 */
const handleEdit = (account: ExchangeAccount) => {
  dialogType.value = 'edit'
  currentAccountId.value = account.id
  formData.value = {
    name: account.name,
    exchange: account.exchange,
    apiKey: '', // 不回填密钥，需要重新输入
    apiSecret: '',
    passphrase: '',
    isDemo: account.isDemo
  }
  dialogVisible.value = true
}

/**
 * 保存账户
 */
const handleSave = async () => {
  if (!formRef.value) return

  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  submitLoading.value = true
  try {
    if (dialogType.value === 'create') {
      await createAccount(formData.value)
      ElMessage.success('添加成功')
    } else {
      await updateAccount(currentAccountId.value, formData.value)
      ElMessage.success('更新成功')
    }
    dialogVisible.value = false
    loadAccounts()
  } catch (error: any) {
    ElMessage.error(error.message || '保存失败')
  } finally {
    submitLoading.value = false
  }
}

/**
 * 删除账户
 */
const handleDelete = async (account: ExchangeAccount) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除账户 "${account.name}" 吗？此操作不可撤销。`,
      '警告',
      {
        type: 'warning',
        confirmButtonText: '确定删除',
        cancelButtonText: '取消'
      }
    )
    await deleteAccount(account.id)
    ElMessage.success('删除成功')
    loadAccounts()
  } catch (error) {
    // 用户取消
  }
}

/**
 * 测试连接
 */
const handleTestConnection = async (account: ExchangeAccount) => {
  testLoading.value = account.id
  try {
    const result = await validateAccount(account.id)
    if (result.isValid) {
      ElMessage.success(result.message || '连接测试成功')
    } else {
      ElMessage.error(result.message || '连接测试失败')
    }
  } catch (error: any) {
    ElMessage.error(error.message || '连接测试失败')
  } finally {
    testLoading.value = null
  }
}

/**
 * 获取状态图标
 */
const getStatusIcon = (account: ExchangeAccount) => {
  if (account.isValidated) {
    return '✅'
  }
  return '⚠️'
}

/**
 * 获取状态文本
 */
const getStatusText = (account: ExchangeAccount) => {
  if (account.isValidated) {
    return '已验证'
  }
  return '未验证'
}

// ========== 生命周期 ==========
onMounted(() => {
  loadAccounts()
})
</script>

<template>
  <div class="account-config">
    <!-- 页面头部 -->
    <div class="page-header">
      <h2 class="page-title">账户配置</h2>
      <el-button type="primary" @click="handleAdd">
        + 添加账户
      </el-button>
    </div>

    <!-- 账户列表 -->
    <div class="account-list" v-loading="loading">
      <el-empty v-if="accounts.length === 0" description="暂无账户配置" />
      <div v-else class="account-cards">
        <div
          v-for="account in accounts"
          :key="account.id"
          class="account-card"
        >
          <div class="card-header">
            <div class="account-info">
              <h3 class="account-name">{{ account.name }}</h3>
              <div class="tags">
                <el-tag size="small" type="info" v-if="account.isDemo">
                  模拟交易
                </el-tag>
                <el-tag size="small" type="warning" v-else>
                  实盘交易
                </el-tag>
                <el-tag size="small">
                  {{ EXCHANGES.find((e: typeof EXCHANGES[number]) => e.value === account.exchange)?.label }}
                </el-tag>
              </div>
            </div>
            <div class="account-status">
              <span class="status-icon">{{ getStatusIcon(account) }}</span>
              <span class="status-text">{{ getStatusText(account) }}</span>
            </div>
          </div>

          <div class="card-body">
            <div class="info-row">
              <span class="label">交易所</span>
              <span class="value">{{ account.exchange.toUpperCase() }}</span>
            </div>
            <div class="info-row">
              <span class="label">创建时间</span>
              <span class="value">{{ formatDate(account.createdAt) }}</span>
            </div>
            <div v-if="account.lastValidatedAt" class="info-row">
              <span class="label">最后验证</span>
              <span class="value">{{ formatDate(account.lastValidatedAt) }}</span>
            </div>
          </div>

          <div class="card-footer">
            <el-button
              size="small"
              :loading="testLoading === account.id"
              @click="handleTestConnection(account)"
            >
              测试连接
            </el-button>
            <el-button size="small" @click="handleEdit(account)">
              编辑
            </el-button>
            <el-button
              size="small"
              type="danger"
              @click="handleDelete(account)"
            >
              删除
            </el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- 添加/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogType === 'create' ? '添加账户' : '编辑账户'"
      width="600px"
      :close-on-click-modal="false"
    >
      <el-form
        ref="formRef"
        :model="formData"
        :rules="rules"
        label-width="120px"
      >
        <el-form-item label="账户名称" prop="name">
          <el-input
            v-model="formData.name"
            placeholder="请输入账户名称，如：Binance 主账户"
          />
        </el-form-item>

        <el-form-item label="交易所" prop="exchange">
          <el-select v-model="formData.exchange" placeholder="请选择交易所">
            <el-option
              v-for="item in EXCHANGES"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="账户类型" prop="isDemo">
          <el-radio-group v-model="formData.isDemo">
            <el-radio :label="false">实盘交易</el-radio>
            <el-radio :label="true">模拟交易</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="API Key" prop="apiKey">
          <el-input
            v-model="formData.apiKey"
            placeholder="请输入 API Key"
            show-password
          />
        </el-form-item>

        <el-form-item label="API Secret" prop="apiSecret">
          <el-input
            v-model="formData.apiSecret"
            placeholder="请输入 API Secret"
            show-password
          />
        </el-form-item>

        <el-form-item
          v-if="formData.exchange === 'OKX'"
          label="Passphrase"
          prop="passphrase"
        >
          <el-input
            v-model="formData.passphrase"
            placeholder="请输入 Passphrase（OKX 必填）"
            show-password
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
.account-config {
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;

    .page-title {
      margin: 0;
      font-size: 24px;
      font-weight: 600;
    }
  }

  .account-list {
    .account-cards {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
      gap: 20px;

      .account-card {
        padding: 20px;
        background: #fff;
        border-radius: 8px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        border: 1px solid #e4e7ed;
        transition: all 0.3s;

        &:hover {
          box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
          transform: translateY(-2px);
        }

        .card-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 16px;
          padding-bottom: 12px;
          border-bottom: 1px solid #e4e7ed;

          .account-info {
            display: flex;
            align-items: center;
            gap: 8px;

            .account-name {
              margin: 0;
              font-size: 16px;
              font-weight: 600;
            }

            .tags {
              display: flex;
              align-items: center;
              gap: 6px;
            }
          }

          .account-status {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 13px;

            .status-icon {
              font-size: 16px;
            }

            .status-text {
              color: #606266;
            }
          }
        }

        .card-body {
          display: flex;
          flex-direction: column;
          gap: 8px;
          margin-bottom: 16px;

          .info-row {
            display: flex;
            gap: 8px;
            font-size: 13px;

            .label {
              color: #909399;
            }

            .value {
              color: #303133;
            }
          }
        }

        .card-footer {
          display: flex;
          gap: 8px;
          padding-top: 12px;
          border-top: 1px solid #e4e7ed;
        }
      }
    }
  }
}

// 响应式设计
@media (max-width: 768px) {
  .account-config {
    .page-header {
      flex-direction: column;
      gap: 16px;
      align-items: flex-start;
    }

    .account-list {
      .account-cards {
        grid-template-columns: 1fr;
      }
    }
  }
}
</style>
