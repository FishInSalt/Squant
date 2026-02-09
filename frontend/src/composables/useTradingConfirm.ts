import { h, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { formatNumber, formatPrice } from '@/utils/format'

export interface PositionRow {
  symbol: string
  side: string
  amount: number
  avg_entry_price?: number
}

/**
 * 停止实盘交易确认对话框（含取消挂单选项）
 * 使用 VNode 渲染，避免 XSS 和 DOM 竞态问题
 */
export async function confirmStopLive(): Promise<{ confirmed: boolean; cancelOrders: boolean }> {
  const cancelOrders = ref(false)

  try {
    await ElMessageBox({
      title: '停止实盘交易',
      message: h('div', null, [
        h('p', null, '确定要停止该实盘交易吗？当前持仓将被保留。'),
        h('label', {
          style: 'display:flex;align-items:center;gap:8px;margin-top:12px;cursor:pointer',
        }, [
          h('input', {
            type: 'checkbox',
            style: 'width:16px;height:16px;cursor:pointer',
            onChange: (e: Event) => {
              cancelOrders.value = (e.target as HTMLInputElement).checked
            },
          }),
          h('span', null, '同时取消所有挂单'),
        ]),
        h('p', {
          style: 'color:#909399;font-size:12px;margin-top:8px',
        }, '不勾选则保留挂单，仅停止策略运行'),
      ]),
      type: 'warning',
      confirmButtonText: '确认停止',
      cancelButtonText: '取消',
      showCancelButton: true,
    })
    return { confirmed: true, cancelOrders: cancelOrders.value }
  } catch {
    return { confirmed: false, cancelOrders: false }
  }
}

/**
 * 构建持仓列表 VNode 表格
 */
function buildPositionTable(positions: PositionRow[], showAvgPrice = false) {
  const rows = positions.filter((p) => p.amount !== 0)
  if (rows.length === 0) {
    return h('p', { style: 'color:#909399;margin-top:8px' }, '当前无持仓')
  }

  const headerCells = [
    h('td', { style: 'padding:6px 8px' }, '币对'),
    h('td', { style: 'padding:6px 8px' }, '方向'),
    h('td', { style: 'padding:6px 8px;text-align:right' }, '数量'),
  ]
  if (showAvgPrice) {
    headerCells.push(h('td', { style: 'padding:6px 8px;text-align:right' }, '均价'))
  }

  const tableRows = rows.map((row) => {
    const sideLabel = row.side === 'long' ? '多' : '空'
    const sideColor = row.side === 'long' ? '#00C853' : '#FF1744'
    const cells = [
      h('td', { style: 'padding:6px 8px' }, row.symbol),
      h('td', { style: `padding:6px 8px;color:${sideColor}` }, sideLabel),
      h('td', { style: 'padding:6px 8px;text-align:right' }, formatNumber(Math.abs(row.amount), 4)),
    ]
    if (showAvgPrice && row.avg_entry_price != null) {
      cells.push(h('td', { style: 'padding:6px 8px;text-align:right' }, formatPrice(row.avg_entry_price)))
    }
    return h('tr', { style: 'border-bottom:1px solid #f5f7fa' }, cells)
  })

  return h('table', {
    style: 'width:100%;border-collapse:collapse;margin-top:12px;font-size:13px',
  }, [
    h('tr', { style: 'border-bottom:1px solid #ebeef5;color:#909399' }, headerCells),
    ...tableRows,
  ])
}

/**
 * 紧急平仓确认对话框（展示持仓列表）
 * 使用 VNode 渲染，避免 XSS 问题
 */
export async function confirmEmergencyClose(
  positions: PositionRow[],
  showAvgPrice = false,
): Promise<boolean> {
  const positionTable = buildPositionTable(positions, showAvgPrice)

  try {
    await ElMessageBox({
      title: '紧急平仓',
      message: h('div', null, [
        h('p', {
          style: 'color:#FF1744;font-weight:500',
        }, '确定要执行紧急平仓吗？这将立即市价平掉以下所有持仓！'),
        positionTable,
      ]),
      type: 'error',
      confirmButtonText: '确认平仓',
      cancelButtonText: '取消',
      showCancelButton: true,
    })
    return true
  } catch {
    return false
  }
}

/**
 * 从 API 返回的 positions Record 转换为 PositionRow 数组
 */
export function toPositionRows(
  positions: Record<string, { amount: number; avg_entry_price: number; current_price?: number }>,
): PositionRow[] {
  return Object.entries(positions).map(([symbol, pos]) => ({
    symbol,
    side: pos.amount > 0 ? 'long' : pos.amount < 0 ? 'short' : 'flat',
    amount: pos.amount,
    avg_entry_price: pos.avg_entry_price,
  }))
}
