# 实体关系图

> **关联文档**: [核心表结构](./02-core-tables.md)

## ER 图

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                   Squant ER 图                                   │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌──────────────┐         ┌──────────────┐         ┌──────────────┐            │
│  │   Exchange   │         │   Strategy   │         │  RiskRule    │            │
│  │   Account    │         │              │         │              │            │
│  ├──────────────┤         ├──────────────┤         ├──────────────┤            │
│  │ id           │         │ id           │         │ id           │            │
│  │ exchange     │         │ name         │         │ name         │            │
│  │ name         │         │ version      │         │ type         │            │
│  │ api_key_enc  │         │ code         │         │ params       │            │
│  │ api_secret   │         │ params_def   │         │ enabled      │            │
│  │ passphrase   │         │ status       │         │ created_at   │            │
│  │ testnet      │         │ created_at   │         └──────────────┘            │
│  │ created_at   │         │ updated_at   │                                     │
│  └──────┬───────┘         └──────┬───────┘                                     │
│         │                        │                                              │
│         │ 1                      │ 1                                            │
│         │                        │                                              │
│         ▼ n                      ▼ n                                            │
│  ┌──────────────┐         ┌──────────────┐                                     │
│  │   Balance    │         │ StrategyRun  │                                     │
│  │  (Snapshot)  │         │              │                                     │
│  ├──────────────┤         ├──────────────┤                                     │
│  │ id           │         │ id           │                                     │
│  │ account_id   │◀────┐   │ strategy_id  │                                     │
│  │ currency     │     │   │ account_id   │◀───┐                                │
│  │ free         │     │   │ mode         │    │                                │
│  │ locked       │     │   │ symbol       │    │                                │
│  │ timestamp    │     │   │ timeframe    │    │                                │
│  └──────────────┘     │   │ params       │    │                                │
│                       │   │ status       │    │                                │
│                       │   │ process_id   │    │                                │
│                       │   │ started_at   │    │                                │
│                       │   │ stopped_at   │    │                                │
│                       │   └──────┬───────┘    │                                │
│                       │          │            │                                │
│                       │          │ 1          │                                │
│                       │          │            │                                │
│                       │          ▼ n          │                                │
│                       │   ┌──────────────┐    │                                │
│                       │   │    Order     │    │                                │
│                       │   ├──────────────┤    │                                │
│                       │   │ id           │    │                                │
│                       │   │ run_id       │    │                                │
│                       │   │ account_id   │────┘                                │
│                       │   │ exchange_oid │                                     │
│                       │   │ symbol       │                                     │
│                       │   │ side         │                                     │
│                       │   │ type         │                                     │
│                       │   │ price        │                                     │
│                       │   │ amount       │                                     │
│                       │   │ filled       │                                     │
│                       │   │ status       │                                     │
│                       │   │ created_at   │                                     │
│                       └───│ updated_at   │                                     │
│                           └──────┬───────┘                                     │
│                                  │                                              │
│                                  │ 1                                            │
│                                  │                                              │
│                                  ▼ n                                            │
│                           ┌──────────────┐                                     │
│                           │    Trade     │                                     │
│                           ├──────────────┤                                     │
│                           │ id           │                                     │
│                           │ order_id     │                                     │
│                           │ exchange_tid │                                     │
│                           │ price        │                                     │
│                           │ amount       │                                     │
│                           │ fee          │                                     │
│                           │ fee_currency │                                     │
│                           │ timestamp    │                                     │
│                           └──────────────┘                                     │
│                                                                                 │
│  ═══════════════════════════════════════════════════════════════════════════   │
│                              TimescaleDB 时序表                                  │
│  ═══════════════════════════════════════════════════════════════════════════   │
│                                                                                 │
│  ┌──────────────┐         ┌──────────────┐         ┌──────────────┐            │
│  │    Kline     │         │ RiskTrigger  │         │  EquityCurve │            │
│  │ (Hypertable) │         │ (Hypertable) │         │ (Hypertable) │            │
│  ├──────────────┤         ├──────────────┤         ├──────────────┤            │
│  │ time (PK)    │         │ time (PK)    │         │ time (PK)    │            │
│  │ exchange     │         │ rule_id      │         │ run_id       │            │
│  │ symbol (PK)  │         │ run_id       │         │ equity       │            │
│  │ timeframe(PK)│         │ trigger_type │         │ cash         │            │
│  │ open         │         │ details      │         │ position_val │            │
│  │ high         │         └──────────────┘         └──────────────┘            │
│  │ low          │                                                              │
│  │ close        │                                                              │
│  │ volume       │                                                              │
│  └──────────────┘                                                              │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## 实体关系说明

| 关系 | 说明 |
|------|------|
| ExchangeAccount → StrategyRun | 1:N，一个账户可以运行多个策略 |
| Strategy → StrategyRun | 1:N，一个策略可以多次运行 |
| StrategyRun → Order | 1:N，一次运行可以产生多个订单 |
| Order → Trade | 1:N，一个订单可以多次成交 |
| RiskRule → RiskTrigger | 1:N，一个规则可以多次触发 |
| StrategyRun → EquityCurve | 1:N，一次运行产生多个权益快照 |
