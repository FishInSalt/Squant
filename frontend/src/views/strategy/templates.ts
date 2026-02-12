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
    description: '经典趋势跟踪策略。当快线上穿慢线时买入，下穿时卖出。适合趋势行情。',
    code: `from squant.engine.backtest.strategy_base import Strategy
from decimal import Decimal


class DualMA(Strategy):
    """双均线交叉策略

    当短周期均线上穿长周期均线时买入（金叉），
    当短周期均线下穿长周期均线时卖出（死叉）。
    """

    def on_init(self):
        self.fast_period = self.ctx.params.get("fast_period", 5)
        self.slow_period = self.ctx.params.get("slow_period", 20)
        self.position_size = Decimal(str(self.ctx.params.get("position_size", 0.01)))

    def on_bar(self, bar):
        closes = self.ctx.get_closes(self.slow_period)
        if len(closes) < self.slow_period:
            return

        fast_ma = sum(closes[-self.fast_period:]) / self.fast_period
        slow_ma = sum(closes) / self.slow_period
        pos = self.ctx.get_position(bar.symbol)

        if fast_ma > slow_ma and not pos:
            self.ctx.buy(bar.symbol, self.position_size)
        elif fast_ma < slow_ma and pos:
            self.ctx.sell(bar.symbol, pos.amount)
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
        position_size: {
          type: 'number',
          title: '下单数量',
          description: '每次买入的数量',
          default: 0.01,
          minimum: 0.001,
        },
      },
    },
    default_params: {
      fast_period: 5,
      slow_period: 20,
      position_size: 0.01,
    },
  },
  {
    id: 'rsi_reversal',
    name: 'rsi_reversal',
    displayName: 'RSI 均值回归',
    description: '基于相对强弱指数的均值回归策略。RSI 超卖时买入，超买时卖出。适合震荡行情。',
    code: `from squant.engine.backtest.strategy_base import Strategy
from decimal import Decimal


class RSIReversal(Strategy):
    """RSI 均值回归策略

    计算RSI指标，当RSI低于超卖线时买入，
    高于超买线时卖出。
    """

    def on_init(self):
        self.period = self.ctx.params.get("period", 14)
        self.oversold = self.ctx.params.get("oversold", 30)
        self.overbought = self.ctx.params.get("overbought", 70)
        self.position_size = Decimal(str(self.ctx.params.get("position_size", 0.01)))

    def on_bar(self, bar):
        closes = self.ctx.get_closes(self.period + 1)
        if len(closes) < self.period + 1:
            return

        # 计算RSI
        gains = []
        losses = []
        for i in range(1, len(closes)):
            change = closes[i] - closes[i - 1]
            if change > 0:
                gains.append(float(change))
                losses.append(0.0)
            else:
                gains.append(0.0)
                losses.append(float(abs(change)))

        avg_gain = sum(gains[-self.period:]) / self.period
        avg_loss = sum(losses[-self.period:]) / self.period

        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))

        pos = self.ctx.get_position(bar.symbol)

        if rsi < self.oversold and not pos:
            self.ctx.buy(bar.symbol, self.position_size)
        elif rsi > self.overbought and pos:
            self.ctx.sell(bar.symbol, pos.amount)
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
        position_size: {
          type: 'number',
          title: '下单数量',
          description: '每次买入的数量',
          default: 0.01,
          minimum: 0.001,
        },
      },
    },
    default_params: {
      period: 14,
      oversold: 30,
      overbought: 70,
      position_size: 0.01,
    },
  },
  {
    id: 'buy_and_hold',
    name: 'buy_and_hold',
    displayName: '买入持有',
    description: '最简单的基准策略。在第一根K线买入后一直持有。常用作其他策略的对比基准。',
    code: `from squant.engine.backtest.strategy_base import Strategy
from decimal import Decimal


class BuyAndHold(Strategy):
    """买入持有策略

    在第一根K线买入指定数量后一直持有，
    不做任何卖出操作。常用作策略回测的基准。
    """

    def on_init(self):
        self.bought = False
        self.position_size = Decimal(str(self.ctx.params.get("position_size", 0.01)))

    def on_bar(self, bar):
        if not self.bought:
            self.ctx.buy(bar.symbol, self.position_size)
            self.bought = True
`,
    params_schema: {
      type: 'object',
      properties: {
        position_size: {
          type: 'number',
          title: '买入数量',
          description: '一次性买入的数量',
          default: 0.01,
          minimum: 0.001,
        },
      },
    },
    default_params: {
      position_size: 0.01,
    },
  },
  {
    id: 'bollinger_bands',
    name: 'bollinger_bands',
    displayName: '布林带突破',
    description: '基于布林带的波动率策略。价格触及下轨时买入，触及上轨时卖出。适合区间震荡行情。',
    code: `from squant.engine.backtest.strategy_base import Strategy
from decimal import Decimal
import math


class BollingerBands(Strategy):
    """布林带突破策略

    计算布林带上下轨，价格触及下轨时买入，
    触及上轨时卖出。
    """

    def on_init(self):
        self.period = self.ctx.params.get("period", 20)
        self.num_std = self.ctx.params.get("num_std", 2.0)
        self.position_size = Decimal(str(self.ctx.params.get("position_size", 0.01)))

    def on_bar(self, bar):
        closes = self.ctx.get_closes(self.period)
        if len(closes) < self.period:
            return

        # 计算均值和标准差
        float_closes = [float(c) for c in closes]
        mean = sum(float_closes) / len(float_closes)
        variance = sum((x - mean) ** 2 for x in float_closes) / len(float_closes)
        std = math.sqrt(variance)

        upper_band = mean + self.num_std * std
        lower_band = mean - self.num_std * std
        price = float(bar.close)

        pos = self.ctx.get_position(bar.symbol)

        if price <= lower_band and not pos:
            self.ctx.buy(bar.symbol, self.position_size)
        elif price >= upper_band and pos:
            self.ctx.sell(bar.symbol, pos.amount)
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
        position_size: {
          type: 'number',
          title: '下单数量',
          description: '每次买入的数量',
          default: 0.01,
          minimum: 0.001,
        },
      },
    },
    default_params: {
      period: 20,
      num_std: 2.0,
      position_size: 0.01,
    },
  },
]
