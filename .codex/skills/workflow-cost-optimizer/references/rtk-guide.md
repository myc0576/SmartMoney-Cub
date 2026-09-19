# RTK (Rust Token Killer) CLI 压缩代理指南

## 核心机制

RTK 是一个在命令执行与 Agent 读取之间拦截过滤的 Rust 单二进制代理（<10ms 开销）。
针对高频长输出命令自动裁剪冗余信息：
- `git status`: 压缩率约 30%，聚合状态。
- `npm test` / `pytest`: 仅输出失败用例堆栈，折叠成功计数，压缩率 70%~90%。
- `docker ps` / `ps aux`: 裁剪掉无用空白与非关键列，压缩率可达 90% 以上。

## 使用方式

在所有 shell 命令前加上 `rtk` 前缀：
```bash
rtk git status
rtk git diff --stat
rtk npm test
rtk ls -la src/
```

查看 Token 节省效果：
```bash
./build/dev-env.sh rtk gain
# 或
rtk gain
```

## 避坑指南

1. **不可重写命令**：对输出即为必须完整内容的数据（如需要解析其完整 JSON 结构由代码消费），使用 `rtk proxy <cmd>` 或原生命令。
2. **退出码透传**：RTK 保证 100% 忠实透传原始命令退出码，门禁与自动化断言不受任何影响。
