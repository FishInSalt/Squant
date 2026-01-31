# Squant测试文档

欢迎来到Squant项目的测试文档中心。本目录包含了完整的测试指南、最佳实践和工具。

## 📚 文档目录

### 核心指南

1. **[TESTING_GUIDE.md](./TESTING_GUIDE.md)** - 综合测试指南
   - 测试分类（单元、集成、E2E）
   - 🚨 **危险操作清单**（必读！）
   - Mock和Fixture最佳实践
   - 测试命名规范
   - 断言技巧
   - 常见测试模式

2. **[INTEGRATION_TESTING.md](./INTEGRATION_TESTING.md)** - 集成测试指南
   - 什么是集成测试
   - 测试环境设置（Docker）
   - 编写集成测试
   - 数据库和Redis测试
   - API集成测试

3. **[TROUBLESHOOTING.md](./TROUBLESHOOTING.md)** - 问题排查指南
   - 13个常见问题及解决方案
   - 系统崩溃事件详细分析
   - 异步测试问题
   - Mock和Fixture问题
   - 数据库和API测试问题

4. **[CI_SETUP.md](./CI_SETUP.md)** - CI/CD集成指南
   - GitHub Actions配置
   - 测试策略和分级执行
   - 覆盖率报告集成
   - 性能优化
   - 故障排查

5. **[TEST_COVERAGE_REPORT.md](./TEST_COVERAGE_REPORT.md)** - 测试覆盖率报告
   - 当前测试状态（1,537个测试，41%覆盖率）
   - 各模块覆盖率详情
   - 关键发现和建议

## 🚀 快速开始

### 新手入门

如果你是第一次为Squant项目编写测试，推荐按以下顺序阅读：

1. **先读**: [TESTING_GUIDE.md](./TESTING_GUIDE.md)
   - 了解测试分类
   - **务必阅读"危险操作清单"**（避免系统崩溃）
   - 学习基本的测试模式

2. **使用模板**: [测试模板](../../../tests/templates/)
   - 使用`service_template.py`编写服务测试
   - 使用`api_template.py`编写API测试
   - 参考`README.md`了解使用方法

3. **运行测试**:
   ```bash
   # 单元测试（快速，不需要外部服务）
   uv run pytest tests/unit -v

   # 集成测试（需要Docker环境）
   ./scripts/test-env.sh start  # 启动测试环境
   ./scripts/test-env.sh test -v  # 运行集成测试
   ```

4. **遇到问题**: 查阅 [TROUBLESHOOTING.md](./TROUBLESHOOTING.md)

### 经验丰富的开发者

如果你已经熟悉pytest和测试，可以直接：

- 使用[测试模板](../../../tests/templates/)快速创建测试文件
- 查看[CI_SETUP.md](./CI_SETUP.md)了解如何集成CI/CD
- 参考[INTEGRATION_TESTING.md](./INTEGRATION_TESTING.md)编写集成测试

## 📊 当前测试状态

**截至2026-01-30**:

| 指标 | 数值 |
|------|------|
| 测试总数 | 1,537个 |
| 整体覆盖率 | 41% |
| 测试文件数 | 64个 |

### 覆盖率分布

- **高覆盖率模块（>90%）**: Models, Schemas, 核心Services, 主要API端点
- **中等覆盖率模块（50-90%）**: 部分Services, 部分API
- **低覆盖率模块（<50%）**: WebSocket, 交易所集成（需要集成测试而非单元测试）

详细信息请查看 [TEST_COVERAGE_REPORT.md](./TEST_COVERAGE_REPORT.md)

## 🛠️ 测试工具

### 命令行工具

```bash
# 单元测试
uv run pytest tests/unit -v

# 集成测试
./scripts/test-env.sh start  # 启动测试环境
./scripts/test-env.sh test -v  # 运行测试
./scripts/test-env.sh stop  # 停止测试环境

# 覆盖率报告
uv run pytest --cov=src/squant --cov-report=html
open htmlcov/index.html

# 只运行失败的测试
uv run pytest --lf

# 调试模式
uv run pytest --pdb -s
```

### 测试模板

位置: `tests/templates/`

- **service_template.py** - 服务层测试模板
- **api_template.py** - API端点测试模板
- **README.md** - 模板使用指南

### 测试环境脚本

位置: `scripts/test-env.sh`

```bash
./scripts/test-env.sh <command>

Commands:
  start         - 启动测试环境 (PostgreSQL + Redis)
  stop          - 停止测试环境
  status        - 查看服务状态
  logs [service] - 查看日志
  reset-db      - 重置数据库
  clear-redis   - 清空Redis
  test [args]   - 运行集成测试
  psql          - 进入PostgreSQL shell
  redis-cli     - 进入Redis CLI
```

## ⚠️ 重要提示

### 🚨 测试安全性

在编写测试时，**务必避免以下操作**：

1. ❌ Mock `asyncio.sleep()` 在包含循环的代码中
2. ❌ 测试包含 `while running` 循环的方法
3. ❌ 调用 WebSocket `run()` 方法
4. ❌ 启动后台异步任务的测试
5. ❌ 依赖真实交易所连接的单元测试

**原因**: 这些操作可能导致无限循环和系统内存溢出崩溃（在本项目中已发生两次）。

详细信息请查看:
- [TESTING_GUIDE.md - 危险操作清单](./TESTING_GUIDE.md#危险操作清单-)
- [TROUBLESHOOTING.md - 问题1: 系统内存溢出崩溃](./TROUBLESHOOTING.md#问题1-测试导致系统内存溢出崩溃)

### ✅ 安全的测试方法

- 测试纯函数和数据转换
- Mock外部API调用（返回值而非异步行为）
- 使用集成测试验证WebSocket和实时功能
- 测试错误处理和边界情况

## 📖 文档导航

### 按角色导航

**我是新开发者**:
1. [TESTING_GUIDE.md](./TESTING_GUIDE.md) - 学习基础
2. [tests/templates/](../../../tests/templates/) - 使用模板
3. [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) - 遇到问题时查阅

**我要写集成测试**:
1. [INTEGRATION_TESTING.md](./INTEGRATION_TESTING.md) - 完整指南
2. [tests/integration/](../../../tests/integration/) - 参考示例

**我要配置CI/CD**:
1. [CI_SETUP.md](./CI_SETUP.md) - CI/CD配置
2. [INTEGRATION_TESTING.md](./INTEGRATION_TESTING.md) - 测试环境设置

**我遇到了测试问题**:
1. [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) - 问题排查
2. [TESTING_GUIDE.md](./TESTING_GUIDE.md) - 最佳实践

### 按任务导航

**编写单元测试**:
- [TESTING_GUIDE.md - 单元测试](./TESTING_GUIDE.md#单元测试-unit-tests)
- [tests/templates/service_template.py](../../../tests/templates/service_template.py)
- [tests/templates/api_template.py](../../../tests/templates/api_template.py)

**编写集成测试**:
- [INTEGRATION_TESTING.md](./INTEGRATION_TESTING.md)
- [tests/integration/](../../../tests/integration/) - 示例

**运行测试**:
- [TESTING_GUIDE.md - pytest命令](./TESTING_GUIDE.md#pytest命令)
- [INTEGRATION_TESTING.md - 运行集成测试](./INTEGRATION_TESTING.md#运行集成测试)

**调试测试**:
- [TESTING_GUIDE.md - 调试技巧](./TESTING_GUIDE.md#调试技巧)
- [TROUBLESHOOTING.md](./TROUBLESHOOTING.md)

**配置CI**:
- [CI_SETUP.md](./CI_SETUP.md)

## 🎯 测试目标

### 当前状态 ✅

- ✅ 1,537个测试覆盖核心业务逻辑
- ✅ 关键模块（Services、Models、API）覆盖率>80%
- ✅ 完整的测试文档和工具
- ✅ Docker化的测试环境
- ✅ 测试模板和最佳实践

### 下一步计划 🚧

按优先级排序：

1. **完善集成测试** (进行中)
   - WebSocket集成测试
   - 交易所API集成测试（使用测试网）

2. **端到端测试框架**
   - 完整业务流程测试
   - 真实场景验证

3. **持续改进**
   - 测试性能优化
   - 覆盖率提升（合理范围内）
   - 文档更新

## 💡 贡献指南

### 添加新测试

1. 选择合适的测试类型（单元/集成/E2E）
2. 使用相应的模板创建测试文件
3. 遵循命名规范：`test_<function>_<scenario>_<expected>`
4. 添加合适的pytest标记（`@pytest.mark.unit`, `@pytest.mark.integration`）
5. 确保测试独立且可重复运行

### 更新文档

如果你发现文档中的问题或有改进建议：

1. 修改相应的Markdown文件
2. 确保示例代码可以运行
3. 更新"最后更新"日期

### 报告问题

- 测试失败：查阅 [TROUBLESHOOTING.md](./TROUBLESHOOTING.md)
- 新问题：添加到 [TROUBLESHOOTING.md](./TROUBLESHOOTING.md)
- Bug：创建GitHub Issue

## 📞 获取帮助

遇到问题时：

1. **查阅文档**：先查看相关文档
2. **查看示例**：参考 `tests/unit/` 和 `tests/integration/` 中的示例
3. **运行诊断**：
   ```bash
   # 检查测试环境
   ./scripts/test-env.sh status

   # 查看详细错误信息
   uv run pytest tests/unit -vv --tb=long
   ```
4. **寻求帮助**：如果以上都无法解决，联系团队

## 📝 更新日志

### 2026-01-30

- ✅ 完成Phase 1: 测试文档和最佳实践
  - 创建 TESTING_GUIDE.md
  - 创建 TROUBLESHOOTING.md
  - 创建测试模板
  - 创建 CI_SETUP.md

- ✅ 完成Phase 2: Docker集成测试环境
  - 创建 docker-compose.test.yml
  - 创建 test-env.sh 脚本
  - 创建集成测试fixtures
  - 创建集成测试示例
  - 创建 INTEGRATION_TESTING.md

- 📊 当前测试状态：1,537个测试，41%覆盖率

### Phase 10 (2026-01-30)
- ✅ WebSocket测试改进（覆盖率16% → 48%）
- 🚨 修复危险测试导致的系统崩溃问题

### Phase 9 (2026-01-30)
- ✅ API端点测试（75个新测试）
- 覆盖率：account 100%, backtest 99%, risk 100%, orders 77%

### Phase 7-8 (2026-01-30)
- ✅ Services层测试（261个测试）
- ✅ Engine和Infrastructure层测试（464个测试）

---

**维护者**: Development Team
**最后更新**: 2026-01-30
**项目**: Squant - 量化交易系统
