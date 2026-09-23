---
name: frontend-design
description: 负责前端整体审美、现代金融交易与复盘工作台的视觉表现力、高级排版、沉浸式色彩系统与信息层级美学。在构建或重构组件与页面时强制提供专业、精致、非模板化的设计审美指导。
metadata:
  role: aesthetic-lead
  category: design
  priority: 1
---

# Frontend Design (前端视觉与审美指南)

本技能专注于 **界面审美、视觉表现力、排版品味与金融交易界面沉浸感**。
拒绝死板的默认组件堆砌、泛滥的纯灰底白字、以及毫无呼吸感的拥挤报表。

---

## 核心审美哲学 (Aesthetic Principles)

1. **金融专业与现代极简融合 (Pro Trader Modernism)**:
   - 界面整体以 TradingView 级语义化沉浸感为基准，兼具高密度数据承载力与呼吸留白。
   - 避免廉价的 AI 模板感（如大面积无意义渐变、生硬圆角或悬浮卡片乱飞）。
   - 层次分明：背景层（Deep Canvas）、表面层（Surface/Card）、悬浮层（Elevated Modal/Popover）、操作层（Accent Interactive）。

2. **高级色彩与对比控制 (Sophisticated Palette & Contrast)**:
   - 遵循工作区设计令牌 `gui/src/tokens.css`，严禁硬编码 hex/rgb 颜色值。
   - **语义化金融色彩**：
     - 必须使用红涨绿跌/绿涨红跌可切换变量：`--pos` / `--neg`，映射为 `--up` 与 `--down`，保持语义解耦。
     - 核心强调蓝（Accent）：`#2962ff`，用于关键交互动作与聚焦状态。
     - 中性阶梯：高对比度文本（`--color-content-primary`）、次级辅助信息（`--color-content-secondary`）、低权重元数据（`--color-content-tertiary`）。
   - 暗色与亮色严密自洽：暗色下杜绝纯黑（#000）或灰阶发乌；亮色下保证足够的微弱边框（`--color-border-primary`）定义轮廓。

3. **微交互与质感动效 (Tactile Micro-Interactions)**:
   - 悬停（Hover）、激活（Active）、焦点（Focus-visible）均有丝滑微反馈（150ms ~ 200ms ease）。
   - 骨架屏与过渡加载替代死板的整页闪烁，骨架条采用微妙的 shimmer 动效。
   - 状态徽章（Badges）与数值标签（Chips）采用柔和透明度背景（如 `rgba(..., 0.12)`）配高饱和文字。

4. **排版节奏与空间张力 (Typography & Spatial Rhythm)**:
   - 数字必须使用等宽字体特征（Tabular figures: `font-feature-settings: 'tnum'` 或 Geist/JetBrains Mono），确保盈亏、价格、比例列完美垂直对齐。
   - 空间网格系统：严格基于 4px / 8px 基线，统一外边距与内衬（8px / 12px / 16px / 24px）。
   - 视线动线清晰：主指标大字号高对比，辅助标签小字号收敛，形成自然的视线落点。

---

## 审美审查清单 (Aesthetic Checklist)

在任何 UI 组件或页面交付前，逐项核验：
- [ ] 是否存在未定义在 `tokens.css` 中的孤立内联色彩？
- [ ] 数值、价格、盈亏、时间戳是否启用了等宽对齐与易读分段？
- [ ] 卡片间距、按钮内边距是否均匀呼吸，有无紧贴边框的文字拥挤？
- [ ] 按钮与交互控件在暗色模式下是否出现刺眼的「全白」或纯黑边框？
- [ ] 整体界面是否呈现出沉稳、严谨、精密的量化与交易软件气质？

