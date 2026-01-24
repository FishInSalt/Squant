# 进程管理

> **关联文档**: [引擎架构](./01-architecture.md), [进程间通信](../architecture/04-ipc.md)

## 1. 进程管理器

```python
import multiprocessing as mp
from typing import Dict, Optional
import uuid
import structlog

logger = structlog.get_logger()

class ProcessManager:
    """策略进程管理器"""

    def __init__(self, redis_client, db_session):
        self.redis = redis_client
        self.db = db_session
        self.processes: Dict[str, mp.Process] = {}
        self.max_restart_attempts = 3  # 最大重启次数

    def spawn(
        self,
        run_id: str,
        strategy_code: str,
        mode: str,  # backtest | paper | live
        config: dict
    ) -> str:
        """启动策略进程"""
        process_id = str(uuid.uuid4())

        process = mp.Process(
            target=strategy_worker,
            args=(process_id, run_id, strategy_code, mode, config),
            daemon=True
        )
        process.start()

        self.processes[process_id] = process

        # 记录进程信息到 Redis
        self.redis.hset(f"squant:process:{process_id}", mapping={
            "run_id": run_id,
            "pid": process.pid,
            "status": "starting",
            "started_at": datetime.utcnow().isoformat()
        })

        return process_id

    def terminate(self, process_id: str, graceful: bool = True) -> bool:
        """终止策略进程"""
        process = self.processes.get(process_id)
        if not process:
            return False

        if graceful:
            # 发送停止命令
            self.redis.publish(f"squant:control:{process_id}", json.dumps({
                "action": "stop"
            }))
            # 等待进程退出
            process.join(timeout=10)

        if process.is_alive():
            process.terminate()
            process.join(timeout=5)

        if process.is_alive():
            process.kill()

        del self.processes[process_id]
        return True

    def monitor(self):
        """监控所有进程健康状态"""
        for process_id, process in list(self.processes.items()):
            # 检查心跳
            heartbeat = self.redis.get(f"squant:process:heartbeat:{process_id}")
            if not heartbeat:
                # 心跳超时，进程可能已死
                if not process.is_alive():
                    self._handle_process_death(process_id)

    def _handle_process_death(self, process_id: str):
        """处理进程死亡"""
        process_info = self.redis.hgetall(f"squant:process:{process_id}")
        run_id = process_info.get("run_id")

        # 更新 Redis 状态
        self.redis.hset(f"squant:process:{process_id}", "status", "error")

        # 清理内存中的进程引用
        if process_id in self.processes:
            del self.processes[process_id]

        if not run_id:
            return

        # 查询策略运行记录
        run = self.db.query(StrategyRun).filter_by(id=run_id).first()
        if not run:
            return

        # 回测模式：标记为失败，不重启
        if run.mode == "backtest":
            run.status = "failed"
            run.error_message = "进程异常退出"
            self.db.commit()
            logger.warning("backtest_process_died", run_id=run_id)
            return

        # 实盘/模拟模式：尝试自动重启
        restart_count = int(process_info.get("restart_count", 0))

        if restart_count >= self.max_restart_attempts:
            # 超过最大重启次数，标记为失败
            run.status = "failed"
            run.error_message = f"进程异常退出，已重启 {restart_count} 次仍失败"
            self.db.commit()
            logger.error("strategy_restart_limit_exceeded",
                        run_id=run_id, restart_count=restart_count)
            # TODO: 发送告警通知
            return

        # 自动重启
        logger.info("strategy_auto_restart", run_id=run_id, attempt=restart_count + 1)
        try:
            new_process_id = self.spawn(
                run_id=run_id,
                strategy_code=run.strategy.code,
                mode=run.mode,
                config=run.config
            )
            # 记录重启次数
            self.redis.hset(f"squant:process:{new_process_id}",
                           "restart_count", restart_count + 1)
        except Exception as e:
            run.status = "failed"
            run.error_message = f"自动重启失败: {e}"
            self.db.commit()
            logger.error("strategy_restart_failed", run_id=run_id, error=str(e))

    async def recover_on_startup(self):
        """系统启动时恢复运行中的策略（NFR-013）"""
        logger.info("strategy_recovery_started")

        # 查询系统重启前处于运行状态的策略
        running_strategies = self.db.query(StrategyRun).filter(
            StrategyRun.status == "running",
            StrategyRun.mode.in_(["paper", "live"])  # 只恢复模拟盘和实盘
        ).all()

        recovered = 0
        failed = 0

        for run in running_strategies:
            try:
                logger.info("recovering_strategy", run_id=str(run.id), mode=run.mode)

                # 启动策略进程
                process_id = self.spawn(
                    run_id=str(run.id),
                    strategy_code=run.strategy.code,
                    mode=run.mode,
                    config=run.config
                )

                # 标记为恢复启动
                self.redis.hset(f"squant:process:{process_id}", "recovered", "true")
                recovered += 1

            except Exception as e:
                logger.error("strategy_recovery_failed",
                           run_id=str(run.id), error=str(e))
                run.status = "failed"
                run.error_message = f"系统重启后恢复失败: {e}"
                failed += 1

        self.db.commit()

        # 处理回测任务：标记为失败（回测不支持恢复）
        interrupted_backtests = self.db.query(StrategyRun).filter(
            StrategyRun.status == "running",
            StrategyRun.mode == "backtest"
        ).all()

        for run in interrupted_backtests:
            run.status = "failed"
            run.error_message = "系统重启，回测中断"

        self.db.commit()

        logger.info("strategy_recovery_completed",
                   recovered=recovered, failed=failed,
                   backtests_interrupted=len(interrupted_backtests))

        return {"recovered": recovered, "failed": failed}
```

## 2. 策略 Worker

```python
def strategy_worker(
    process_id: str,
    run_id: str,
    strategy_code: str,
    mode: str,
    config: dict
):
    """策略进程入口"""

    # 设置资源限制
    set_resource_limits()

    # 连接 Redis
    redis = Redis(...)

    # 创建上下文
    if mode == "backtest":
        context = BacktestContext(config)
    elif mode == "paper":
        context = PaperContext(config, redis)
    else:
        context = LiveContext(config, redis)

    # 加载策略
    strategy = load_strategy(strategy_code, context)

    # 心跳线程
    heartbeat_thread = start_heartbeat(redis, process_id)

    # 订阅控制命令
    pubsub = redis.pubsub()
    pubsub.subscribe(f"squant:control:{process_id}")

    try:
        # 初始化
        strategy.on_init()
        strategy.on_start()

        # 主循环
        if mode == "backtest":
            run_backtest(strategy, context, config)
        else:
            run_realtime(strategy, context, pubsub)

    except Exception as e:
        strategy.on_error(e)
        redis.hset(f"squant:process:{process_id}", mapping={
            "status": "error",
            "error": str(e)
        })
    finally:
        strategy.on_stop()
        heartbeat_thread.stop()
```

## 3. 系统启动恢复机制

> **满足需求**: NFR-013 "系统重启后自动恢复运行中的策略"

### 3.1 恢复流程

```
┌─────────────────────────────────────────────────────────────┐
│                     系统启动流程                             │
├─────────────────────────────────────────────────────────────┤
│  1. 初始化数据库连接                                         │
│  2. 初始化 Redis 连接                                        │
│  3. 创建 ProcessManager                                      │
│  4. 调用 recover_on_startup()  ◄── 恢复策略                  │
│  5. 启动 API 服务                                            │
│  6. 启动进程监控定时任务                                     │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 集成到 FastAPI 启动

```python
# squant/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时
    process_manager = ProcessManager(redis_client, db_session)

    # 恢复运行中的策略
    recovery_result = await process_manager.recover_on_startup()
    logger.info("startup_complete", **recovery_result)

    # 启动进程监控（每 10 秒检查一次）
    monitor_task = asyncio.create_task(
        run_process_monitor(process_manager, interval=10)
    )

    app.state.process_manager = process_manager

    yield

    # 关闭时
    monitor_task.cancel()
    # 优雅停止所有策略进程
    for process_id in list(process_manager.processes.keys()):
        process_manager.terminate(process_id, graceful=True)

app = FastAPI(lifespan=lifespan)
```

### 3.3 恢复策略说明

| 运行模式 | 系统重启后行为 | 说明 |
|---------|--------------|------|
| `live` | 自动恢复 | 实盘策略必须恢复，避免持仓无人管理 |
| `paper` | 自动恢复 | 模拟盘恢复以保持测试连续性 |
| `backtest` | 标记失败 | 回测无法恢复中间状态，需重新运行 |

### 3.4 进程崩溃自动重启

| 场景 | 行为 | 最大重试 |
|-----|------|---------|
| 进程异常退出 | 自动重启 | 3 次 |
| 超过重试次数 | 标记失败 + 告警 | - |
| 心跳超时 | 检测后触发重启 | 3 次 |

### 3.5 监控日志示例

```json
{"event": "strategy_recovery_started", "timestamp": "2025-01-24T10:00:00Z"}
{"event": "recovering_strategy", "run_id": "abc-123", "mode": "live"}
{"event": "recovering_strategy", "run_id": "def-456", "mode": "paper"}
{"event": "strategy_recovery_completed", "recovered": 2, "failed": 0, "backtests_interrupted": 1}
```
