---
name: ui-ux-pro-max
description: 负责前端 UI/UX 设计规范、交互规则、状态机覆盖、响应式布局边界、无障碍访问性与防呆容错。确保每一个组件和界面具备生产级交互健壮度与严密的 UX 契约。
metadata:
  role: interaction-lead
  category: ux-rules
  priority: 2
---

# UI/UX Pro Max (设计规范与交互规则引擎)

本技能专注于 **界面交互规范、状态机完整性、响应式边界与用户操作体验的严密性**。
任何界面不仅要好看，更必须在全状态（Loading / Error / Empty / Success）、极端数据与各种屏幕宽度下稳定可用。

---

## 核心交互规则 (Core Interaction Rules)

1. **四态完备法则 (The 4-State Integrity Rule)**:
   每个视图、面板与异步数据卡片必须显式处理且测试以下 4 种状态：
   - **加载中 (Loading)**：局部微加载或占位骨架，不阻断全局无关操作，避免整屏无意义 Spinner。
   - **空状态 (Empty State)**：绝不可仅展示空白或空表格！必须包含清晰图标、空状态说明文案以及下一步引导按钮（CTA）。
   - **错误状态 (Error State)**：清晰告知失败原因、分类诊断（如网络/鉴权/配额/服务降级），并提供确定性的「重试」或「配置修复」入口。
   - **就绪状态 (Ready/Populated)**：正常高密度数据渲染。

2. **响应式与侧边栏/抽屉挤压规则 (Responsive & Panel Squeeze Contract)**:
   - **双列与多列自适应**：在右侧复盘助手（Assistant Panel）展开（占用 400px）时，页面主体卡片网格必须平滑自适应（例如由 3~4 列响应式降级为 2 列），严禁水平溢出（Horizontal Scroll / Overflow）。
   - **断点契约**：
     - `< 980px`：折叠辅助侧边栏，转换为抽屉（Drawer）或浮层模式。
     - `980px ~ 1440px`：紧凑桌面布局，收紧间距与表格列宽。
     - `> 1440px`：标准宽屏布局，右侧助手常驻。

3. **防呆设计与破坏性操作保护 (Failsafe & Destructive Guards)**:
   - 具有破坏性或不可逆的操作（如删除记录、重置数据、卸载插件、清空会话）：
     - 必须采用二次确认（Modal 确认对话框）或两步确认机制。
     - 绝对禁止危险操作使用单次无提示点击生效。
   - 表单校验：
     - 提交前进行内联实时校验，错误提示紧贴输入框下方，聚焦时高亮红框。
     - 提交中（Submitting）禁用提交按钮并显示加载旋转动画，防止表单重复提交（Debounce / Single Flight）。

4. **金融量化业务契约防护 (Quant Business Constraints)**:
   - **只读禁令感知**：界面必须醒目标注只读安全声明 `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`，不得伪造真实券商下单入口。
   - **边界关闭感知 (Closed Trust Boundary)**：当连接共享或沙箱受限部署（如后端返回 403 封闭边界时）：
     - 输入框必须禁用并给出明确的不可用提示，而不是让用户输入后点击发送才报异常。
     - 插件与规则等受限视图必须显示「当前环境未开放该服务」，绝不能谎称「没有安装任何插件」或「暂无规则」。
   - **敏感凭证防窥探 (Write-Only Credentials)**：API Key、Secret 等配置只写不读，界面严禁明文回显已保存的真实凭据。

5. **无障碍与按键导航 (Accessibility & Keyboard Nav)**:
   - 支持全键盘快捷键（如 Esc 关闭抽屉/弹窗、Enter 提交输入、Cmd+K 聚焦搜索）。
   - 交互元素具备清晰的 `:focus-visible` 聚焦外边框与语义化 aria 属性（`aria-expanded`、`aria-label`）。

---

## 交付前 UX 检查清单 (UX Verification Checklist)

- [ ] 是否在不同窗口宽度（1200px / 1600px）测试过布局，确认没有意外的横向滚动条？
- [ ] 异步操作失败时，是否有友好的错误重试卡片，而不是崩溃白屏或控制台静默报错？
- [ ] 模态弹框打开时，背景是否有半透明遮罩并阻止页面滚动穿透？按 Esc 是否能正常退出？
- [ ] 数据流为空时，是否展示了引导性空状态？

