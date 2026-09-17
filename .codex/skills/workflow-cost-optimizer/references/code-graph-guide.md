# 代码图谱 (Graphify) 使用指南与实战避坑

## 为什么代码图谱能降低 22.7% Token？

传统基于关键词盲搜（grep / ripgrep）：
1. 搜索 "UserService" -> 返回 20 个文件的匹配行（几千 token 进入 context）。
2. 搜索 "getUserById" -> 返回 8 个文件匹配。
3. 依次 read_file UserService.java (300行) -> 累积进入 context。
4. 经过 3~5 轮探索才能定位真实目标，上下文已经塞满无用代码。

Graphify 建立 AST + 语义依赖关系图谱：
- 一次查询直接输出：定义节点、依赖节点、调用关系、源文件精确行号（L9, L41 等）。
- 探索轮次从 3~5 轮压缩到 1 轮，源头消除无用文件 context 堆积。

## 核心命令

```bash
# 1. 语义图谱精准检索 (推荐方式)
./build/dev-env.sh graph query "AIChatConfig"
# 或直接调用
graphify query "AIChatConfig" --budget 1500

# 2. 查找两个概念或类之间的调用路径
graphify path "AIAssistantViewModel" "RuntimeAIChatClient"

# 3. 解释核心枢纽节点
graphify explain "AgentOrchestrator"

# 4. 增量更新图谱 (已有 post-commit git hook 自动处理，也可手动触发)
./build/dev-env.sh graph update
```

## 项目配置注意事项

- 本项目在根目录配置了 `.graphifyignore`，排除了外部逆向资源 `recon/` 与第三方打包构建物，只保留真实源码（`src/`, `server/`, `replica/`, `web/alpharch-ui/`, `tools/`），提取速度极快（< 15秒）。
- 已通过 `graphify hook install` 在 `.git/hooks/` 安装 post-commit 与 post-checkout 自动化更新钩子。
