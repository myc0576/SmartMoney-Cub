---
name: goal-loop
description: Explicit end-to-end goal loop. Freezes scope and Definition of Done (DoD), iterates through execution and deterministic verification, and requires independent evaluation against external signals before allowing task completion.
---

# Goal Loop (端到端目标驱动闭环)

## 核心法则 (The Iron Contract)

```
目标与验收标准一旦冻结，禁止单方面降级或私自删减。
禁止大模型自我宣称“完成”，一切以外部确定性信号为唯一裁决依据。
```

当面临困难、报错或未预期边界时，严禁通过“删除需求”、“标记为已知问题”或“自行宣布已满足主要功能”来绕过未完成的验收标准。

---

## 5 步循环状态机 (The 5-Step Loop)

```
 [1. FREEZE_SCOPE] ---> [2. EXECUTE] ---> [3. EXTERNAL_VERIFY]
          ^                                    |
          |             (未全过, 轮次 < 5)      v
          +---------- [5. REFLECT & REPAIR] <-- [4. INDEPENDENT_EVAL]
                                                       | (全部通过)
                                                       v
                                                 [6. COMPLETE]
```

### 1. FREEZE_SCOPE (目标与准则冻结)
在触碰任何业务代码之前，必须先在回复或规划中明确且不可更改地输出以下四项：
- **Goal (目标)**: 一句话说明本次任务的核心交付物。
- **Non-Goals (非目标)**: 明确排除的边界，防止需求膨胀。
- **Definition of Done (DoD 验收清单)**: 具体、可验证、客观的布尔检查列表（格式必须为 `- [ ] 准则描述 (验证手段: 真实命令/文件/断言)`）。
- **Max Iterations**: 默认上限 5 轮。

### 2. EXECUTE (委派执行)
- 围绕未完成的 DoD 进行最小化、原子化的代码修改或文件编写。
- 严禁随意篡改测试用例或断言文件来迎合有缺陷的代码（只读测试原则）。

### 3. EXTERNAL_VERIFY (外部客观信号捕获)
- 执行项目对应的确定性验证命令（编译、测试、Lint、安全审查、Doctor 命令）。
- 完整读取标准输出（stdout）、错误输出（stderr）和返回码（exit code）。
- **禁止在没有最新执行输出的情况下假设状态。**

### 4. INDEPENDENT_EVAL (独立审查与打勾)
以冷酷的第三方验收者视角，逐项核对第 1 步冻结的 DoD：
- 每项通过必须附带具体的外部证据（例如：测试通过数、命令返回码 0、具体生成的产物路径）。
- 只要有任意一项未满足，严禁给出最终完成报告。

### 5. REFLECT & REPAIR (反思与有界修复)
若验收未通过：
- **诊断根因**: 提取真实报错堆栈，定位代码缺陷。
- **禁忌表 (Tabu Check)**: 检查新方案是否与前几轮尝试过的失败方案雷同。严禁在两个错误方案之间来回振荡。
- **记录账本**: 简记当前轮次教训，调整策略后重新进入 EXECUTE。
- **有界熔断**: 若连续 3 轮卡在同一阻塞点，或达到最大轮次上限（5 轮），必须立即停止盲目试错，带着确凿的失败现场与证据向人类求助。

---

## 常见失控红线 (Red Flags - 立即终止自省)

- 出现“这个功能通常不影响主流程，先交付”等推脱词。
- 出现“我检查了代码逻辑，应该没有问题了”而没有实际执行验证命令。
- 因为测试报错，私自把测试里的断言注释掉或改成假通过。
- 方案 A 报错改方案 B，方案 B 报错又改回方案 A。

