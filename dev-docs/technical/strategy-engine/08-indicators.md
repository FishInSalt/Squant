# 技术指标

> **关联文档**: [策略上下文](./04-context.md)

## 1. 支持的指标

| 类别 | 指标 | 函数名 |
|------|------|--------|
| **趋势** | 简单移动平均 | `SMA` |
| | 指数移动平均 | `EMA` |
| | 加权移动平均 | `WMA` |
| | MACD | `MACD` |
| **动量** | RSI | `RSI` |
| | 随机指标 | `STOCH` |
| | CCI | `CCI` |
| | 威廉指标 | `WILLR` |
| **波动** | 布林带 | `BBANDS` |
| | ATR | `ATR` |
| | 标准差 | `STDDEV` |
| **成交量** | OBV | `OBV` |
| | 成交量均线 | `VOLUME_SMA` |

## 2. 使用示例

```python
# 在策略中使用
def on_bar(self, bar):
    closes = self.ctx.get_history("close", 30)

    # 计算指标
    sma = self.ctx.indicator("SMA", closes, 20)
    rsi = self.ctx.indicator("RSI", closes, 14)
    macd, signal, hist = self.ctx.indicator("MACD", closes, 12, 26, 9)
    upper, middle, lower = self.ctx.indicator("BBANDS", closes, 20, 2)
```

## 3. 指标参数说明

### SMA (简单移动平均)

```python
sma = self.ctx.indicator("SMA", data, period)
# period: 周期，如 20
```

### EMA (指数移动平均)

```python
ema = self.ctx.indicator("EMA", data, period)
# period: 周期，如 12
```

### MACD

```python
macd, signal, hist = self.ctx.indicator("MACD", data, fast, slow, signal_period)
# fast: 快线周期，默认 12
# slow: 慢线周期，默认 26
# signal_period: 信号线周期，默认 9
```

### RSI

```python
rsi = self.ctx.indicator("RSI", data, period)
# period: 周期，默认 14
# 返回值: 0-100
```

### BBANDS (布林带)

```python
upper, middle, lower = self.ctx.indicator("BBANDS", data, period, std_dev)
# period: 周期，默认 20
# std_dev: 标准差倍数，默认 2
```

### ATR (平均真实波幅)

```python
atr = self.ctx.indicator("ATR", high, low, close, period)
# 需要传入 high, low, close 三组数据
# period: 周期，默认 14
```

### STOCH (随机指标)

```python
k, d = self.ctx.indicator("STOCH", high, low, close, k_period, d_period)
# k_period: K 线周期，默认 14
# d_period: D 线周期，默认 3
```
