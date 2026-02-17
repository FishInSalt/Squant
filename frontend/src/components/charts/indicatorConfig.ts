/**
 * Shared indicator configuration for K-line chart components.
 *
 * Indicators with `dynamicCount: true` allow users to add/remove lines
 * (e.g. MA can have 1-8 moving average lines). Each entry in `params`
 * defines one line with its default period.
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
  /** If true, users can add/remove param entries (lines) */
  dynamicCount?: boolean
  /** Max number of lines when dynamicCount is true */
  maxCount?: number
  /** Prefix for auto-generated labels (e.g. "MA" → "MA1", "MA2") */
  paramPrefix?: string
}

// Color pools for dynamic-count indicators (up to 8 lines)
const MA_COLORS = ['#FF9600', '#935EBD', '#2196F3', '#E040FB', '#00BCD4', '#8BC34A', '#FF5722', '#795548']
const EMA_COLORS = ['#E11D74', '#01C5C4', '#4CAF50', '#FF6F00', '#3F51B5', '#9C27B0', '#009688', '#F44336']
const RSI_COLORS = ['#FF6D00', '#2196F3', '#4CAF50', '#E040FB', '#00BCD4', '#FF5722', '#795548', '#8BC34A']

export const INDICATOR_DEFS: IndicatorDef[] = [
  {
    key: 'MA',
    label: 'MA',
    dynamicCount: true,
    maxCount: 8,
    paramPrefix: 'MA',
    params: [
      { label: 'MA1', default: 5, min: 1, max: 500, step: 1 },
      { label: 'MA2', default: 10, min: 1, max: 500, step: 1 },
      { label: 'MA3', default: 20, min: 1, max: 500, step: 1 },
      { label: 'MA4', default: 60, min: 1, max: 500, step: 1 },
      { label: 'MA5', default: 120, min: 1, max: 500, step: 1 },
    ],
    colors: MA_COLORS,
  },
  {
    key: 'EMA',
    label: 'EMA',
    dynamicCount: true,
    maxCount: 8,
    paramPrefix: 'EMA',
    params: [
      { label: 'EMA1', default: 12, min: 1, max: 500, step: 1 },
      { label: 'EMA2', default: 26, min: 1, max: 500, step: 1 },
      { label: 'EMA3', default: 50, min: 1, max: 500, step: 1 },
      { label: 'EMA4', default: 200, min: 1, max: 500, step: 1 },
    ],
    colors: EMA_COLORS,
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
    dynamicCount: true,
    maxCount: 6,
    paramPrefix: 'MA',
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
    dynamicCount: true,
    maxCount: 6,
    paramPrefix: 'RSI',
    params: [
      { label: 'RSI1', default: 6, min: 1, max: 500, step: 1 },
      { label: 'RSI2', default: 12, min: 1, max: 500, step: 1 },
      { label: 'RSI3', default: 24, min: 1, max: 500, step: 1 },
    ],
    paneId: 'rsi',
    colors: RSI_COLORS,
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

/** Get the label for the i-th param of a dynamic-count indicator */
export function getDynamicParamLabel(def: IndicatorDef, index: number): string {
  return `${def.paramPrefix ?? def.key}${index + 1}`
}

/** Suggest a reasonable default period when user adds a new line */
export function suggestNewPeriod(def: IndicatorDef, currentParams: number[]): number {
  if (currentParams.length === 0) return def.params[0]?.default ?? 10
  const last = currentParams[currentParams.length - 1]
  // Double the last period, capped at 500
  return Math.min(last * 2, 500)
}
