# 沙箱安全

> **关联文档**: [引擎架构](./01-architecture.md), [安全设计](../architecture/07-security.md)

## 1. 代码限制 (RestrictedPython)

```python
from RestrictedPython import compile_restricted, safe_globals

# 禁止的内置函数
DISALLOWED_BUILTINS = {
    "eval", "exec", "compile",
    "open", "file",
    "__import__",
    "input", "raw_input",
    "globals", "locals",
    "getattr", "setattr", "delattr",
    "dir", "vars",
}

# 禁止的模块
DISALLOWED_MODULES = {
    "os", "sys", "subprocess", "shutil",
    "socket", "urllib", "requests", "httpx",
    "pickle", "marshal",
    "ctypes", "multiprocessing",
    "importlib", "builtins",
}

def validate_strategy_code(code: str) -> List[str]:
    """校验策略代码安全性"""
    errors = []

    # 1. 语法检查
    try:
        compile_restricted(code, "<strategy>", "exec")
    except SyntaxError as e:
        errors.append(f"语法错误: 行 {e.lineno}: {e.msg}")
        return errors

    # 2. 禁止模块检查
    import ast
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in DISALLOWED_MODULES:
                    errors.append(f"禁止导入模块: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in DISALLOWED_MODULES:
                errors.append(f"禁止导入模块: {node.module}")

    # 3. 禁止危险函数
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in DISALLOWED_BUILTINS:
                    errors.append(f"禁止使用函数: {node.func.id}")

    return errors
```

## 2. 资源限制

```python
import resource
import signal

def set_resource_limits():
    """设置进程资源限制"""

    # CPU 时间限制：单次回调最多 30 秒
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))

    # 内存限制：最多 512MB
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))

    # 文件描述符限制
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))

    # 线程数限制：允许 numpy/pandas 多线程计算
    # 注意：RLIMIT_NPROC 在 Linux 上限制用户的进程+线程总数
    # 设置为 32 允许库使用多线程，同时防止无限创建
    resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))

def timeout_handler(signum, frame):
    raise TimeoutError("策略执行超时")

# 设置超时信号
signal.signal(signal.SIGALRM, timeout_handler)
```

> **注意**: 子进程创建通过容器级别 `pids_limit` 控制更为可靠，参见 [Docker 配置](../deployment/01-docker.md)。

## 3. 安全执行环境

```python
# 允许的内置函数
SAFE_BUILTINS = {
    "abs", "all", "any", "bool", "dict", "enumerate",
    "filter", "float", "frozenset", "int", "isinstance",
    "len", "list", "map", "max", "min", "pow", "range",
    "reversed", "round", "set", "slice", "sorted", "str",
    "sum", "tuple", "zip", "True", "False", "None",
    "Decimal", "print",  # print 会被重定向到日志
}

# 允许的模块
ALLOWED_MODULES = {
    "math",
    "decimal",
    "datetime",
    "collections",
    "itertools",
    "functools",
    "typing",
}

def create_safe_globals(context: StrategyContext) -> dict:
    """创建安全的执行环境"""
    safe_builtins = {k: __builtins__[k] for k in SAFE_BUILTINS if k in __builtins__}

    # 重定向 print 到日志
    safe_builtins["print"] = lambda *args: context.log(" ".join(str(a) for a in args))

    return {
        "__builtins__": safe_builtins,
        "Strategy": Strategy,
        "Bar": Bar,
        "Tick": Tick,
        "Order": Order,
        "Trade": Trade,
        "Decimal": Decimal,
    }
```
