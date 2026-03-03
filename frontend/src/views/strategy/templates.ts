export interface StrategyTemplate {
  id: string
  name: string
  displayName: string
  description: string
  code: string
  params_schema: Record<string, unknown>
  default_params: Record<string, unknown>
}

export const strategyTemplates: StrategyTemplate[] = [
  {
    id: 'dual_ma',
    name: 'dual_ma',
    displayName: '双均线交叉',
    description: '经典趋势跟踪策略。使用 ta.sma() 计算均线，金叉买入，死叉平仓。适合趋势行情。',
    code: `from decimal import Decimal


class DualMA(Strategy):
    """双均线交叉策略

    当短周期均线上穿长周期均线时买入（金叉），
    当短周期均线下穿长周期均线时平仓（死叉）。
    """

    def on_init(self):
        self.fast_period = self.ctx.params.get("fast_period", 5)
        self.slow_period = self.ctx.params.get("slow_period", 20)
        self.position_ratio = Decimal(str(self.ctx.params.get("position_ratio", 0.9)))

    def on_bar(self, bar):
        closes = self.ctx.get_closes(self.slow_period + 1)
        if len(closes) < self.slow_period + 1:
            return

        fast_now = ta.sma(closes, self.fast_period)
        slow_now = ta.sma(closes, self.slow_period)
        fast_prev = ta.sma(closes[:-1], self.fast_period)
        slow_prev = ta.sma(closes[:-1], self.slow_period)

        if None in (fast_now, slow_now, fast_prev, slow_prev):
            return

        pos = self.ctx.get_position(bar.symbol)

        # 金叉买入
        if fast_prev <= slow_prev and fast_now > slow_now:
            if not pos:
                amount = self.ctx.cash * self.position_ratio / bar.close
                if amount > 0:
                    self.ctx.buy(bar.symbol, amount)

        # 死叉平仓
        elif fast_prev >= slow_prev and fast_now < slow_now:
            if pos:
                self.ctx.close_position(bar.symbol)
`,
    params_schema: {
      type: 'object',
      properties: {
        fast_period: {
          type: 'integer',
          title: '快线周期',
          description: '短周期均线的K线数量',
          default: 5,
          minimum: 2,
          maximum: 50,
        },
        slow_period: {
          type: 'integer',
          title: '慢线周期',
          description: '长周期均线的K线数量',
          default: 20,
          minimum: 5,
          maximum: 200,
        },
        position_ratio: {
          type: 'number',
          title: '仓位比例',
          description: '每次买入使用的资金比例（0.1 = 10%）',
          default: 0.9,
          minimum: 0.01,
          maximum: 1.0,
        },
      },
    },
    default_params: {
      fast_period: 5,
      slow_period: 20,
      position_ratio: 0.9,
    },
  },
  {
    id: 'rsi_reversal',
    name: 'rsi_reversal',
    displayName: 'RSI 均值回归',
    description:
      '基于相对强弱指数的均值回归策略。使用 ta.rsi() 计算指标，RSI 超卖时买入，超买时卖出。适合震荡行情。',
    code: `from decimal import Decimal


class RSIReversal(Strategy):
    """RSI 均值回归策略

    使用 ta.rsi() 计算RSI指标（Wilder平滑法），
    当RSI低于超卖线时买入，高于超买线时平仓。
    """

    def on_init(self):
        self.period = self.ctx.params.get("period", 14)
        self.oversold = self.ctx.params.get("oversold", 30)
        self.overbought = self.ctx.params.get("overbought", 70)
        self.position_ratio = Decimal(str(self.ctx.params.get("position_ratio", 0.9)))

    def on_bar(self, bar):
        closes = self.ctx.get_closes(self.period + 1)
        if len(closes) < self.period + 1:
            return

        current_rsi = ta.rsi(closes, self.period)
        if current_rsi is None:
            return

        pos = self.ctx.get_position(bar.symbol)

        if current_rsi < self.oversold and not pos:
            amount = self.ctx.cash * self.position_ratio / bar.close
            if amount > 0:
                self.ctx.buy(bar.symbol, amount)
        elif current_rsi > self.overbought and pos:
            self.ctx.close_position(bar.symbol)
`,
    params_schema: {
      type: 'object',
      properties: {
        period: {
          type: 'integer',
          title: 'RSI 周期',
          description: 'RSI 计算使用的K线数量',
          default: 14,
          minimum: 2,
          maximum: 100,
        },
        oversold: {
          type: 'integer',
          title: '超卖线',
          description: 'RSI 低于此值时买入',
          default: 30,
          minimum: 5,
          maximum: 50,
        },
        overbought: {
          type: 'integer',
          title: '超买线',
          description: 'RSI 高于此值时卖出',
          default: 70,
          minimum: 50,
          maximum: 95,
        },
        position_ratio: {
          type: 'number',
          title: '仓位比例',
          description: '每次买入使用的资金比例（0.1 = 10%）',
          default: 0.9,
          minimum: 0.01,
          maximum: 1.0,
        },
      },
    },
    default_params: {
      period: 14,
      oversold: 30,
      overbought: 70,
      position_ratio: 0.9,
    },
  },
  {
    id: 'buy_and_hold',
    name: 'buy_and_hold',
    displayName: '买入持有',
    description: '最简单的基准策略。在第一根K线买入后一直持有。常用作其他策略的对比基准。',
    code: `from decimal import Decimal


class BuyAndHold(Strategy):
    """买入持有策略

    在第一根K线买入后一直持有，
    不做任何卖出操作。常用作策略回测的基准。
    """

    def on_init(self):
        self.bought = False
        self.position_ratio = Decimal(str(self.ctx.params.get("position_ratio", 0.95)))

    def on_bar(self, bar):
        if not self.bought:
            amount = self.ctx.cash * self.position_ratio / bar.close
            if amount > 0:
                self.ctx.buy(bar.symbol, amount)
                self.bought = True
`,
    params_schema: {
      type: 'object',
      properties: {
        position_ratio: {
          type: 'number',
          title: '仓位比例',
          description: '买入使用的资金比例（0.1 = 10%）',
          default: 0.95,
          minimum: 0.01,
          maximum: 1.0,
        },
      },
    },
    default_params: {
      position_ratio: 0.95,
    },
  },
  {
    id: 'bollinger_bands',
    name: 'bollinger_bands',
    displayName: '布林带突破',
    description:
      '基于布林带的波动率策略。使用 ta.bollinger_bands() 计算上下轨，价格触及下轨时买入，触及上轨时卖出。',
    code: `from decimal import Decimal


class BollingerBands(Strategy):
    """布林带突破策略

    使用 ta.bollinger_bands() 计算上下轨，
    价格触及下轨时买入，触及上轨时平仓。
    """

    def on_init(self):
        self.period = self.ctx.params.get("period", 20)
        self.num_std = Decimal(str(self.ctx.params.get("num_std", 2.0)))
        self.position_ratio = Decimal(str(self.ctx.params.get("position_ratio", 0.9)))

    def on_bar(self, bar):
        closes = self.ctx.get_closes(self.period)
        if len(closes) < self.period:
            return

        bands = ta.bollinger_bands(closes, self.period, self.num_std)
        if bands is None:
            return

        upper, middle, lower = bands
        pos = self.ctx.get_position(bar.symbol)

        if bar.close <= lower and not pos:
            amount = self.ctx.cash * self.position_ratio / bar.close
            if amount > 0:
                self.ctx.buy(bar.symbol, amount)
        elif bar.close >= upper and pos:
            self.ctx.close_position(bar.symbol)
`,
    params_schema: {
      type: 'object',
      properties: {
        period: {
          type: 'integer',
          title: '均线周期',
          description: '布林带中轨（均线）的K线数量',
          default: 20,
          minimum: 5,
          maximum: 100,
        },
        num_std: {
          type: 'number',
          title: '标准差倍数',
          description: '上下轨距离中轨的标准差倍数',
          default: 2.0,
          minimum: 0.5,
          maximum: 4.0,
        },
        position_ratio: {
          type: 'number',
          title: '仓位比例',
          description: '每次买入使用的资金比例（0.1 = 10%）',
          default: 0.9,
          minimum: 0.01,
          maximum: 1.0,
        },
      },
    },
    default_params: {
      period: 20,
      num_std: 2.0,
      position_ratio: 0.9,
    },
  },
]
