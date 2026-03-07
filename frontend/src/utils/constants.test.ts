import {
  COLORS,
  TIMEFRAME_OPTIONS,
  EXCHANGE_OPTIONS,
  SUPPORTED_EXCHANGES,
  ORDER_SIDE_OPTIONS,
  ORDER_TYPE_OPTIONS,
  ORDER_STATUS_OPTIONS,
  SESSION_STATUS_OPTIONS,
  PAGINATION,
} from './constants'

describe('COLORS', () => {
  it('has UP, DOWN, NEUTRAL color keys', () => {
    expect(COLORS.UP).toBeTruthy()
    expect(COLORS.DOWN).toBeTruthy()
    expect(COLORS.NEUTRAL).toBeTruthy()
  })

  it('has chart color keys', () => {
    expect(COLORS.CHART_LINE).toBeTruthy()
    expect(COLORS.CHART_AREA).toBeTruthy()
    expect(COLORS.CHART_GRID).toBeTruthy()
  })
})

describe('TIMEFRAME_OPTIONS', () => {
  it('has 8 timeframe options', () => {
    expect(TIMEFRAME_OPTIONS).toHaveLength(8)
  })

  it('each has label and value', () => {
    for (const option of TIMEFRAME_OPTIONS) {
      expect(option.label).toBeTruthy()
      expect(option.value).toBeTruthy()
    }
  })

  it('covers expected timeframes', () => {
    const values = TIMEFRAME_OPTIONS.map((o) => o.value)
    expect(values).toContain('1m')
    expect(values).toContain('1h')
    expect(values).toContain('1d')
  })
})

describe('EXCHANGE_OPTIONS', () => {
  it('has label/value pairs', () => {
    expect(EXCHANGE_OPTIONS.length).toBeGreaterThanOrEqual(2)
    for (const option of EXCHANGE_OPTIONS) {
      expect(option.label).toBeTruthy()
      expect(option.value).toBeTruthy()
    }
  })
})

describe('SUPPORTED_EXCHANGES', () => {
  it('has id/name/has_testnet fields', () => {
    for (const exchange of SUPPORTED_EXCHANGES) {
      expect(exchange.id).toBeTruthy()
      expect(exchange.name).toBeTruthy()
      expect(typeof exchange.has_testnet).toBe('boolean')
    }
  })
})

describe('ORDER_SIDE_OPTIONS', () => {
  it('has buy and sell', () => {
    expect(ORDER_SIDE_OPTIONS).toHaveLength(2)
    const values = ORDER_SIDE_OPTIONS.map((o) => o.value)
    expect(values).toContain('buy')
    expect(values).toContain('sell')
  })
})

describe('ORDER_TYPE_OPTIONS', () => {
  it('has 2 order types', () => {
    expect(ORDER_TYPE_OPTIONS).toHaveLength(2)
  })
})

describe('ORDER_STATUS_OPTIONS', () => {
  it('has 6 statuses', () => {
    expect(ORDER_STATUS_OPTIONS).toHaveLength(6)
  })
})

describe('SESSION_STATUS_OPTIONS', () => {
  it('has 6 statuses', () => {
    expect(SESSION_STATUS_OPTIONS).toHaveLength(6)
  })
})

describe('PAGINATION', () => {
  it('has default page size of 20', () => {
    expect(PAGINATION.DEFAULT_PAGE_SIZE).toBe(20)
  })

  it('has page sizes array', () => {
    expect(PAGINATION.PAGE_SIZES).toContain(10)
    expect(PAGINATION.PAGE_SIZES).toContain(20)
    expect(PAGINATION.PAGE_SIZES).toContain(50)
    expect(PAGINATION.PAGE_SIZES).toContain(100)
  })
})
