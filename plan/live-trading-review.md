# 实盘交易模块代码审查 — 修复计划

审查日期: 2026-03-13
分支: cc/fix-live-trading-issues

## Critical（必须修复 — 可能导致资金损失或系统故障）

### C-1: emergency_close 平仓成交未走 _record_fill 路径
- **文件**: `src/squant/engine/live/engine.py` ~L778
- **问题**: 紧急平仓的市价单成交后，本地仓位/现金状态未更新，导致与交易所实际状态脱节
- **修复**: 在 `_wait_single` 中 FILLED 时创建临时 LiveOrder 并调用 `_record_fill()` 更新本地状态
- **测试**: `test_emergency_close_fill_updates_local_state`, `test_emergency_close_polled_fill_updates_local_state`
- **状态**: [x] 已修复

### C-2: 余额同步使用 available 而非 total
- **文件**: `src/squant/engine/live/engine.py` L1240, L1254; `src/squant/services/live_trading.py` L1285
- **问题**: 有挂单时 `available` 不含 frozen 部分，导致虚假的持仓不一致告警；恢复时用 `available` 覆盖 `_cash` 会直接丢失冻结资金
- **修复**: 引擎和服务层均改为使用 `balance.total`（available + frozen）
- **测试**: `test_balance_sync_uses_total_not_available_for_quote/base`, `TestReconcilePositionsUsesTotal`
- **状态**: [x] 已修复

### C-3: ExchangeConnectionError 名称冲突
- **文件**: `src/squant/services/live_trading.py` L79
- **问题**: 服务层定义的同名异常与 `infra.exchange.exceptions` 的不同类，API 层和全局异常处理器捕获的不是同一个类型
- **修复**: 重命名为 `LiveExchangeConnectionError`，保留向后兼容别名，更新所有 import
- **测试**: `TestExchangeConnectionErrorRename` (3 tests)
- **状态**: [x] 已修复

### C-4: stop 端点缺少状态防护
- **文件**: `src/squant/services/live_trading.py` L816
- **问题**: 不检查 run 当前状态，对已停止/错误状态的会话调用 stop 会覆盖原有 error_message
- **修复**: 添加状态检查，仅允许 RUNNING/PENDING/INTERRUPTED 状态被停止（for_shutdown=True 时跳过检查）
- **测试**: `TestStopStatusGuard` (8 tests)
- **状态**: [x] 已修复

### C-5: emergency_close API 未捕获 LiveTradingError
- **文件**: `src/squant/api/v1/live_trading.py` L185
- **问题**: 交易所异常直接变成 500，而非语义明确的错误响应
- **修复**: 添加 `except LiveTradingError` (400) 和 `except Exception` (500) 处理
- **测试**: `test_emergency_close_live_trading_error`, `test_emergency_close_unexpected_error`
- **状态**: [x] 已修复

### C-6: realized_pnl 求和缺少 None 防护
- **文件**: `src/squant/engine/live/engine.py`
- **问题**: 如果某条 trade 的 realized_pnl 为 None，求和会抛出 TypeError
- **修复**: 改为 `sum((t.pnl for t in ctx._trades if t.pnl is not None), Decimal("0"))`
- **测试**: `test_bar_update_event_handles_none_pnl`
- **状态**: [x] 已修复

## Major（应该修复 — 可靠性或正确性问题）

### M-1: 超时订单误判为 CANCELLED
- **文件**: `src/squant/engine/live/engine.py` L1399
- **问题**: `_reconcile_timed_out_orders` 在 open_orders 未找到时直接标记 CANCELLED，但订单可能已 FILLED
- **修复**: 新增 `_reconcile_missing_timed_out_order()` 方法，通过 `get_order()` 查询最终状态后再决定
- **测试**: `TestReconcileTimedOutOrdersFilledCheck` (3 tests)
- **状态**: [x] 已修复

### M-2: 熔断冷却后重置 consecutive_losses
- **文件**: `src/squant/engine/risk/models.py` L303
- **问题**: 策略系统性亏损时，每次冷却结束后需重新积累 N 次亏损才能再次熔断
- **修复**: 删除 `self.consecutive_losses = 0`，冷却结束后保留亏损计数
- **测试**: `test_consecutive_losses_preserved_after_cooldown` 等 3 tests
- **状态**: [x] 已修复

### M-3: DMS 超时 60s 对大周期 K 线不适用
- **文件**: `src/squant/engine/live/engine.py` L334
- **问题**: 5m/1h K 线下，K 线间隔远大于 60s，DMS 会频繁误触发取消订单
- **修复**: 改为 `max(60_000, timeframe_seconds * 2 * 1000)`，复用 `_TIMEFRAME_SECONDS` 映射
- **测试**: `test_dms_timeout_default_1m/5m/1h/minimum_60s`
- **状态**: [x] 已修复

### M-4: resume 失败未更新 DB 状态为 ERROR
- **文件**: `src/squant/services/live_trading.py` L1609
- **问题**: 恢复失败后状态仍为 INTERRUPTED，用户无法得知恢复失败
- **修复**: 在 except 块中添加 `run_repo.update(run.id, status=RunStatus.ERROR, error_message=...)`
- **测试**: `TestResumeFailureUpdatesDB`
- **状态**: [x] 已修复

### M-5: get_run 未校验 run.mode
- **文件**: `src/squant/services/live_trading.py` L1656
- **问题**: 实盘 API 端点可以获取到回测/模拟交易的 run 记录
- **修复**: 在 get_run 中添加 `if run.mode != RunMode.LIVE: raise SessionNotFoundError`
- **测试**: `TestGetRunModeValidation` (3 tests)
- **状态**: [x] 已修复

### M-6: 恢复时订单对账用 avg_price 代替增量成交价
- **文件**: `src/squant/services/live_trading.py` L1173
- **问题**: 部分成交后崩溃再恢复，增量部分使用全部成交均价记录 fill，PnL 计算不精确
- **修复**: 添加文档注释说明精度折衷 + 日志记录近似值使用（ExchangeAdapter 无 get_order_trades 方法）
- **测试**: `TestReconcileOrdersAvgPriceComment`
- **状态**: [x] 已修复

### M-7: start 中 adapter.connect() 失败后 adapter 未关闭
- **文件**: `src/squant/services/live_trading.py` L369
- **问题**: 如果连接部分成功，adapter 资源会泄漏
- **修复**: 在 except 块中添加 `await adapter.close()`
- **测试**: `TestStartAdapterCloseOnFailure`
- **状态**: [x] 已修复

### M-8: 订单事件持久化失败时无限重试堆积
- **文件**: `src/squant/engine/live/engine.py` L1085
- **问题**: `_pending_order_events` 持续失败时无上限，内存无限增长
- **修复**: 添加 `_MAX_PENDING_ORDER_EVENTS = 1000` 上限，超出时丢弃最旧事件
- **测试**: `test_pending_events_bounded_on_persist_failure`, `test_pending_events_discard_oldest_on_overflow`
- **状态**: [x] 已修复

### M-9: _batch_tickers_loop 重连逻辑与其他 loop 不一致
- **文件**: `src/squant/infra/exchange/ccxt/provider.py` L678
- **问题**: 独立的错误计数和阈值（10 vs 5），与共享的 `_handle_loop_error` 行为不同
- **修复**: 重构为使用共享的 `_handle_loop_error()` 和 `_mark_success()`，统一所有 loop 行为
- **测试**: `TestBatchTickersLoopErrorHandling` (4 tests)
- **状态**: [x] 已修复

### M-10: 服务层直接访问引擎私有属性
- **文件**: `src/squant/services/live_trading.py` — `_reconcile_orders()`, `_reconcile_positions()`
- **问题**: 直接操作 `engine._live_orders`、`engine._exchange_order_map`、`engine.context._cash`、`engine._record_fill()`
- **决定**: 记录为技术债务，暂不重构。对账逻辑仅在 resume 路径使用，频率极低。未来引擎有较大改动时重构为方案 A（将对账逻辑移入引擎内部）
- **状态**: [x] 已标注技术债务（docstring 中添加了 M-10 说明）

## Minor（建议修复 — 代码质量和维护性）

### m-1: symbol/timeframe 参数缺少格式校验
- **文件**: `src/squant/schemas/live_trading.py` L59, L64
- **修复**: 添加 `@field_validator` — symbol 匹配 `^[A-Z0-9]+/[A-Z0-9]+$`，timeframe 限定 13 种有效值
- **测试**: 43 tests in `test_live_trading_validation.py`
- **状态**: [x] 已修复

### m-2: _fire_notification 的 create_task 未持有引用
- **文件**: `src/squant/engine/live/engine.py` L148
- **修复**: 添加模块级和实例级 `_background_tasks: set[Task]`，所有 create_task 后注册 done callback
- **测试**: `TestBackgroundTaskGCProtection` (2 tests)
- **状态**: [x] 已修复

### m-3: parse_ws_order_update 硬编码 OKX 格式
- **文件**: `src/squant/engine/live/order_sync.py`（已删除）
- **评估结果**: 整个 order_sync.py 是死代码，无任何业务代码引用。已在 PR #50 中删除
- **状态**: [x] 已删除（PR #50）

### m-4: zombie 订单标记 REJECTED 但策略未收到 on_order_done 通知
- **文件**: `src/squant/engine/live/engine.py` L1505
- **修复**: 在 `_cleanup_stale_orders` 中将 zombie 订单对应的 SimulatedOrder 移至 completed_orders
- **测试**: `TestZombieOrderNotification`
- **状态**: [x] 已修复

### m-5: API 错误格式不一致
- **文件**: `src/squant/api/v1/live_trading.py`
- **问题**: HTTPException 返回 `{"detail": ...}` 而非 `{"code", "message", "data"}`
- **修复**: 经验证，`main.py` 全局异常处理器已自动转换格式，无需改动
- **测试**: `TestApiErrorFormatConsistency` (5 tests) 验证了一致性
- **状态**: [x] 已确认无需修改

### m-6: emergency_close 返回 status "closed" 不在 schema 定义的有效值中
- **文件**: `src/squant/services/live_trading.py`
- **修复**: 将 `"status": "closed"` 改为 `"status": "completed"`
- **测试**: `TestEmergencyCloseStatusValue` (2 tests)
- **状态**: [x] 已修复

### m-7: _order_poll_min_interval(30s)、_balance_check_interval(300s) 硬编码
- **文件**: `src/squant/engine/live/engine.py` L311, L322
- **修复**: 在 RiskConfig 中添加 `order_poll_interval` 和 `balance_check_interval` 字段，引擎从配置读取
- **测试**: `TestConfigurableIntervals` (3 tests)
- **状态**: [x] 已修复

## 测试覆盖关键缺口（后续补充）

### T-1: LiveTradingService.start() 成功路径完全无测试
- **优先级**: 最高
- **补充**: `TestStartSuccessPath` (9 tests) — 完整启动流程、会话限制、熔断检查、重复启动、异常清理
- **状态**: [x] 已补充

### T-2: LiveTradingService.resume() 完整流程未覆盖
- **优先级**: 最高
- **补充**: `TestResumeSuccessPath` (14 tests) — 完整恢复流程、warmup、delta 同步、多种失败清理路径
- **状态**: [x] 已补充

### T-3: resume_live_trading API 端点无测试
- **优先级**: 最高
- **补充**: `TestResumeLiveTrading` (7 tests) — 成功恢复、自定义 warmup_bars、5 种异常映射
- **状态**: [x] 已补充

### T-4: Private WS / Dead Man's Switch 相关方法全部未覆盖
- **优先级**: 高
- **补充**: `TestPrivateWebSocket` (6 tests) + `TestDeadManSwitch` (9 tests) — 启停、降级、心跳、错误处理
- **状态**: [x] 已补充

### T-5: _trigger_global_circuit_breaker() 无直接测试
- **优先级**: 高
- **补充**: `TestTriggerGlobalCircuitBreaker` (4 tests) — Redis 写入、stop_all 调用、降级处理
- **状态**: [x] 已补充

### T-6: process_candle 中总亏损限额自动停止逻辑未覆盖
- **优先级**: 高
- **补充**: `TestTotalLossLimitAutoStop` (4 tests) — 超限自动停止、错误信息、风控状态更新
- **状态**: [x] 已补充
