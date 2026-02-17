/**
 * Shared indicator configuration for K-line chart components.
 */

export interface IndicatorParamDef {
  label: string
  default: number
  min: number
  max: number
  step: number
}

export interface IndicatorDef {
  key: string
  label: string
  params: IndicatorParamDef[]
  paneId?: string
  colors?: string[]
}

export const INDICATOR_DEFS: IndicatorDef[] = [
  {
    key: 'MA',
    label: 'MA',
    params: [
      { label: 'MA1', default: 5, min: 1, max: 500, step: 1 },
      { label: 'MA2', default: 10, min: 1, max: 500, step: 1 },
      { label: 'MA3', default: 30, min: 1, max: 500, step: 1 },
      { label: 'MA4', default: 60, min: 1, max: 500, step: 1 },
    ],
    colors: ['#FF9600', '#935EBD', '#2196F3', '#E040FB'],
  },
  {
    key: 'EMA',
    label: 'EMA',
    params: [
      { label: 'EMA1', default: 6, min: 1, max: 500, step: 1 },
      { label: 'EMA2', default: 12, min: 1, max: 500, step: 1 },
      { label: 'EMA3', default: 20, min: 1, max: 500, step: 1 },
    ],
    colors: ['#E11D74', '#01C5C4', '#4CAF50'],
  },
  {
    key: 'BOLL',
    label: 'BOLL',
    params: [
      { label: '周期', default: 20, min: 1, max: 500, step: 1 },
      { label: '倍数', default: 2, min: 0.5, max: 10, step: 0.5 },
    ],
    colors: ['#FF6D00', '#0D47A1', '#00897B'],
  },
  {
    key: 'VOL',
    label: 'VOL',
    params: [
      { label: 'MA1', default: 5, min: 1, max: 500, step: 1 },
      { label: 'MA2', default: 10, min: 1, max: 500, step: 1 },
      { label: 'MA3', default: 20, min: 1, max: 500, step: 1 },
    ],
    paneId: 'volume',
  },
  {
    key: 'MACD',
    label: 'MACD',
    params: [
      { label: '快线', default: 12, min: 1, max: 500, step: 1 },
      { label: '慢线', default: 26, min: 1, max: 500, step: 1 },
      { label: '信号', default: 9, min: 1, max: 500, step: 1 },
    ],
    paneId: 'macd',
  },
  {
    key: 'RSI',
    label: 'RSI',
    params: [
      { label: 'RSI1', default: 6, min: 1, max: 500, step: 1 },
      { label: 'RSI2', default: 12, min: 1, max: 500, step: 1 },
      { label: 'RSI3', default: 24, min: 1, max: 500, step: 1 },
    ],
    paneId: 'rsi',
  },
  {
    key: 'KDJ',
    label: 'KDJ',
    params: [
      { label: 'K周期', default: 9, min: 1, max: 500, step: 1 },
      { label: 'D平滑', default: 3, min: 1, max: 500, step: 1 },
      { label: 'J平滑', default: 3, min: 1, max: 500, step: 1 },
    ],
    paneId: 'kdj',
  },
]

export type IndicatorParams = Record<string, number[]>

export function getDefaultParams(): IndicatorParams {
  const params: IndicatorParams = {}
  for (const def of INDICATOR_DEFS) {
    params[def.key] = def.params.map((p) => p.default)
  }
  return params
}

export function getIndicatorDef(key: string): IndicatorDef | undefined {
  return INDICATOR_DEFS.find((d) => d.key === key)
}
