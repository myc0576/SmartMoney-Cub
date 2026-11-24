# Worktree 清理审计

2026-11-23 · 主工作树 `HEAD` 为 `74d14bd`。`origin/main` 为 `8d83d37`，以 `git ls-remote --heads origin main` 核对，本地 `main` 指向同一提交。安全声明为 `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`。

## 架构化与工程化判断

每个现存目标分别运行 `git cherry -v`、`git log --oneline` 和 `git diff` 对比两条基线。下表的「独有」是相对两条基线均为 `+` 的非合并补丁数，SHA 差额包含 merge。是否已被取代还要看内容层面的差异。清理仅涉及独立 checkout，分支间仍保留合并和依赖关系。归档标签均为本地轻量标签，由 `git cat-file -t` 与 `git rev-parse` 核对类型和完整目标 SHA。

删除命令从主仓库根目录解释，仅供核验和备份后的人工操作。标签能恢复提交，不包含 checkout 的暂存、未跟踪或忽略数据。标记 `has-unique-work` 的项须先保留有价值的工作，并核对忽略目录中的运行数据。在同一 tip 已被另一活跃分支覆盖的情况下，仍记录它相对基线的差异。

| Worktree（相对主仓库根） | 分支 · tip | 独有补丁；SHA 差额 HEAD / origin/main | 判定与证据 | 轻量归档标签 | 清理命令 |
| --- | --- | ---: | --- | --- | --- |
| `../orca/workspaces/.orca-preparing/77307-…` | 任务描述为 detached、locked | — | 当前 Git worktree 清单无该项，父目录为空。无可定位 tip | — | 无现存 checkout |
| `../orca/workspaces/Smartmoney-Cub/t09-executors` | `task/t09-executors` · `cdd36c4` | 25；36 / 37 | **has-unique-work**。执行器适配器与沙箱实现仅在当前开发栈，tip 已含于 unified-workbench。有忽略的 `state/` 与评测产物 | `archive/task-t09-executors-20261123` | `git worktree remove ../orca/workspaces/Smartmoney-Cub/t09-executors` |
| `../orca/workspaces/Smartmoney-Cub/t10-dsh` | `task/t10-dsh` · `f1efc45` | 30；43 / 44 | **has-unique-work**。T09 与 T14b 合流尚在开发栈。与 t11-bot 同 tip，已含于 unified-workbench，checkout 干净且无忽略内容，可优先考虑释放 checkout | `archive/task-t10-dsh-20261123` | `git worktree remove ../orca/workspaces/Smartmoney-Cub/t10-dsh` |
| `../orca/workspaces/Smartmoney-Cub/t11-bot` | `task/t11-bot` · `f1efc45` | 30；43 / 44 | **has-unique-work**。同 t10-dsh 的分支树，未见单独 bot 提交。有忽略的 `state/` 与评测产物 | `archive/task-t11-bot-20261123` | `git worktree remove ../orca/workspaces/Smartmoney-Cub/t11-bot` |
| `../orca/workspaces/Smartmoney-Cub/t12-release-tests` | `task/t12-release-tests` · `5d0b4e7` | 32；43 / 44 | **has-unique-work**。独立的 T12b 尾部 8 提交未含于 unified-workbench，含发布落盘、回滚并发保护和评估回归。有忽略的 `state/` 与评测产物 | `archive/task-t12-release-tests-20261123` | `git worktree remove ../orca/workspaces/Smartmoney-Cub/t12-release-tests` |
| `../orca/workspaces/Smartmoney-Cub/t14-react` | `task/t14-react` · `849edb7` | 26；37 / 38 | **has-unique-work**。T14b UI/E2E 已含于 unified-workbench，尚未进两条基线。Git 可见脏项只有 `node_modules` 与 `gui/node_modules`，可丢弃；先保留需留存的忽略状态和报告 | `archive/task-t14-react-20261123` | `git worktree remove --force ../orca/workspaces/Smartmoney-Cub/t14-react` |
| `.agent-workspaces/readme-safety-readonly-6473b07a25ba` | `agent/readme-safety-readonly-6473b07a25ba` · `e71627a` | 1；5 / 1 | **has-unique-work**（worktree）。唯一补丁给英文 README 加四行双语声明，执行权限语义已由两条基线的契约覆盖，源分支同 tip 已推送。忽略的 `state/` 含两个文件，另有评测产物，先核对并保留需要的数据 | `archive/agent-readme-safety-readonly-6473b07a25ba-20261123` | `git worktree remove .agent-workspaces/readme-safety-readonly-6473b07a25ba` |
| `.agent-workspaces/unified-workbench` | `codex/unified-workbench` · `708cad7` | 32；45 / 46 | **has-unique-work**。集中保留任务/知识/方法工作台、T14b、T09，其两个独有尾部提交记录 T09 验收和 T12b 进展。有忽略的 `state/` 与评测产物 | `archive/codex-unified-workbench-20261123` | `git worktree remove .agent-workspaces/unified-workbench` |

相对 `HEAD` / `origin/main`，七条分支分别无 `git cherry` 的 `-` 项。五条 `task/*` 和 `codex/unified-workbench` 在 `origin` 上无同名分支。全量 diff 证明大部分开发栈带有两条基线均无的实现，不能按提交年龄或 SHA 数直接判定已合并。保留优先级为 **主工作树现有变更 → unified-workbench 集成 tip → T12b 独立进展 → 其余重复 checkout**。开发栈的执行器属于代码任务执行接口，重新集成仍须满足市场和执行只读的仓库契约。

## 本地分支分组

`git for-each-ref refs/heads` 实测 **31 条本地分支**。另有 34 条远端跟踪 refs（包含远端默认分支符号引用）。任务给出的 64 条无法在当前仓库按本地 head 口径复现。以下覆盖全部现存本地 heads。Merged 以 `origin/main` 的 Git 祖先关系为准。Active 包括主分支、当前维护分支和本月开发栈。Stale 是其余历史分支，保留补丁统计供复核。

- **Merged（8）**：`codex/convergence-1.0`、`codex/dsh-review-agent`、`codex/dsh-workbench-opt`、`codex/front-door-journal-and-e2e`、`codex/gui-ia-optimization`、`codex/jev-ecosystem`、`codex/plugin-marketplace-real-install`、`codex/trader-product-v1`。
- **Stale（5）**：`codex/dsh-rebuild`（`cherry +5`）、`codex/official-plugin-market-typesafe`（`+1`）、`fix/restore-readme-visuals-flow-and-integrations`（`+1`）、`codex/readme-gateway-banner-link`（`-1`，补丁等价）、`codex/readme-official-gateway`（`-1`，补丁等价）。
- **Active（18）**：`main`、`codex/benchmark-v2-maintenance`、`agent/readme-safety-readonly-6473b07a25ba`、`codex/unified-workbench`、`task/t02-core`、`task/t03-methods`、`task/t04-knowledge`、`task/t05-knowledge`、`task/t06-graphify`、`task/t07-evolution`、`task/t08-runtime`、`task/t09-executors`、`task/t10-dsh`、`task/t11-bot`、`task/t12-evaluation`、`task/t12-release-tests`、`task/t13-domains`、`task/t14-react`。

本次只建立了上述七个归档标签。提交可用 `git show <tag>` 复查，或在新目录从标签恢复 checkout。worktree、分支、远端和索引保持原状。
