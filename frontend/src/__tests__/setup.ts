// Global test setup for Vitest

// Mock environment variables used by api/index.ts and stores/websocket.ts
vi.stubEnv('VITE_API_BASE_URL', '/api/v1')
vi.stubEnv('VITE_WS_BASE_URL', 'ws://localhost:8000/api/v1/ws')

// Mock Element Plus notification/message functions globally
vi.mock('element-plus', async () => {
  const actual = await vi.importActual<typeof import('element-plus')>('element-plus')
  return {
    ...actual,
    ElMessage: Object.assign(vi.fn(), {
      success: vi.fn(),
      warning: vi.fn(),
      error: vi.fn(),
      info: vi.fn(),
    }),
    ElNotification: Object.assign(vi.fn(), {
      success: vi.fn(),
      warning: vi.fn(),
      error: vi.fn(),
      info: vi.fn(),
    }),
    ElMessageBox: {
      confirm: vi.fn().mockResolvedValue('confirm'),
      prompt: vi.fn().mockResolvedValue({ value: '', action: 'confirm' }),
    },
  }
})
