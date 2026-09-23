# 开源 Fork、上游贡献与持续维护记忆

本文是 SmartMoney-Cub 的长期开发记忆。凡是涉及 Fork、向第三方项目提交
Pull Request、公开发布、更新生态收录信息或维护上游兼容性，都必须在开始前阅读
本文，并把对应检查项纳入本次任务的 Definition of Done。

安全声明：`READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`

## 已验证的收录记录

以下是历史快照，不替代执行任务时对 GitHub 当前状态的重新核验。

| 项目 | 已验证事实 |
|---|---|
| 核验日期 | 2026-09-22 |
| 上游仓库 | [`kraayenjon/awesome-jev`](https://github.com/kraayenjon/awesome-jev) |
| 个人 Fork | [`myc0576/awesome-jev`](https://github.com/myc0576/awesome-jev)；GitHub 标记为上游仓库的 Fork |
| 贡献分支 | `add-smartmoney-cub` |
| Pull Request | [#9 Add SmartMoney-Cub to Business and vertical apps](https://github.com/kraayenjon/awesome-jev/pull/9) |
| 合并结果 | 2026-09-20 已合并到上游 `main` |
| 上游落点 | README 的 `Business and vertical apps` 已包含 SmartMoney-Cub，并链接到本项目 |
| Fork 同步快照 | 核验时个人 Fork 的 `main` 落后上游 9 个提交；这不影响已合并结果，但说明合并后同步不能省略 |

术语要分清：此次是“Fork 了 `awesome-jev`，随后 SmartMoney-Cub 的收录 PR 被
上游合并”，不是“SmartMoney-Cub 被 Fork”。判断成功至少要分别核验 Fork 关系、
PR 状态和上游默认分支中的最终内容。

## 标准工作流

### 1. 公开前检查

- 阅读目标仓库的 `CONTRIBUTING`、许可证、模板和分类规则，确认项目符合收录范围。
- 只公开仓库本应公开的内容；不得提交真实交易记录、私人自选列表、凭据、Cookie、
  账户标识、租户数据或本地绝对路径。
- 示例、测试和截图使用 toy/offline 数据。涉及 SmartMoney-Cub 能力描述时保留
  `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`，不得暗示选股、荐股或自动交易。
- 对版本、性能、成本和基准数字给出日期与来源；不得把一次快照写成永久事实。
- 先运行项目验证门禁，确保准备公开的提交可复现且没有夹带无关修改。

### 2. 建立并同步 Fork

- 用 GitHub 元数据确认个人仓库的 `isFork` 为真，并核对 `parent` 正是预期上游。
- 远端角色保持清晰：`origin` 指向个人 Fork，`upstream` 指向原始仓库。
- 开始贡献前先获取并同步上游默认分支；不要直接在个人 Fork 的 `main` 上开发。
- 从最新上游默认分支建立单一用途的功能分支，分支名准确描述本次贡献。
- 同步或解决冲突时不得覆盖他人的工作；共享分支禁止无说明的强制推送。

参考检查命令（仓库名和分支名按任务替换）：

```bash
gh repo view OWNER/FORK --json isFork,parent,defaultBranchRef,url
git remote -v
git fetch upstream
git switch main
git merge --ff-only upstream/main
git switch -c add-project-entry
```

### 3. 准备并提交 Pull Request

- 一个 PR 只解决一个清晰问题；提交中不混入格式化、生成物或其他功能改动。
- PR 描述写清项目用途、与上游分类的关系、验证证据、已知限制和维护者披露。
- 所有链接必须指向公开、稳定且正确的页面；项目名、许可证和安全能力描述要准确。
- 提交前运行本项目完整验证，并按上游要求运行它自己的检查。
- 创建 PR 后核对 base 仓库/base 分支与 head Fork/head 分支，避免向错误目标提交。
- CI 或评审失败时修复根因；不得删除断言、弱化安全表述或追加无关提交来换取合并。

### 4. 评审与合并后闭环

- 跟进 CI 和维护者反馈，并在每轮更新后重新检查 PR diff。
- 只有 GitHub 显示 `Merged` 且上游默认分支出现最终内容，才算上游贡献完成。
- 核对上游最终措辞和链接；维护者可能在合并时压缩或调整原文。
- 合并后同步个人 Fork 的默认分支，确认不再因旧提交产生无意义的 ahead/behind 状态。
- 功能分支不再需要时可删除，但删除远端分支属于远端变更，必须在任务授权范围内执行。
- 把 PR 链接、合并日期、上游落点和同步状态写入项目记忆或发布记录。

参考核验命令：

```bash
gh pr view PR_NUMBER --repo UPSTREAM_OWNER/UPSTREAM_REPO \
  --json state,mergedAt,baseRefName,headRefName,url
gh repo view OWNER/FORK --json isFork,parent,defaultBranchRef
gh api repos/UPSTREAM_OWNER/UPSTREAM_REPO/compare/main...OWNER:main \
  --jq '{status,ahead_by,behind_by}'
```

### 5. 后续版本维护

每次准备发布或合并重大变更时，检查公开收录信息是否仍然真实。以下变化通常需要
同步 README、发布说明，必要时再向上游提交更新 PR：

- 仓库重命名、迁移组织、默认分支或公开链接改变；
- 安装方式、最低版本、主要 API 或许可证改变；
- Jev 集成方式、模型标识或公开可复现的基准发生实质变化；
- 安全边界或产品定位改变；任何描述仍必须符合只读执行禁令；
- 上游分类、贡献规则或项目状态发生变化。

小修复不应频繁打扰上游维护者。只有当既有条目已经错误、失效或明显误导时，才提交
更新；PR 中说明“旧描述 → 新事实 → 验证来源”。如果上游仓库归档、迁移或删除条目，
先记录客观状态与原因，再决定是否迁移收录，不能把旧链接继续当作当前背书。

## 常见状态与处理

| 状态 | 含义 | 下一步 |
|---|---|---|
| 个人仓库显示 `forked from` | Fork 创建成功 | 同步上游并创建功能分支 |
| Fork 存在但没有 PR | 只完成了 Fork | 核对 diff 后创建 PR |
| PR 为 Open | 尚未收录 | 跟进 CI、冲突和评审 |
| PR 为 Merged，但 Fork behind | 收录成功，个人 Fork 未同步 | 同步 `main`，再次核对差异 |
| PR 已关闭且未合并 | 上游未接受该版本 | 阅读反馈后修订或停止；不得宣称已收录 |
| 上游 README 有条目但链接失效 | 公开信息已过期 | 修复本项目链接并向上游提交最小更新 |

## 任务完成证据模板

涉及上游贡献的任务最终报告至少包含：

- Fork 仓库、上游仓库及 GitHub 确认的 parent 关系；
- 功能分支和 PR 链接；
- PR 当前状态、合并时间与上游默认分支中的落点；
- Fork 相对上游的 ahead/behind 状态；
- 本项目与上游各自验证命令的退出结果；
- 隐私、许可证和 `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE` 安全复核结果。

没有这些当轮、可复查的外部证据，不得声称 Fork、上游收录或后续同步已经完成。
