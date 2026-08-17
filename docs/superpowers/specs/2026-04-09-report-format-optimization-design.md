# 日报 & 周报格式优化设计

## 概述

为盘前日报和周度报告增加信息图卡片可视化，同时优化 Markdown 排版结构。目标：在 Obsidian 和手机上都能快速浏览关键数据。

## 方案选择

**方案 A：baoyu-image-cards 卡片系列 + Markdown 排版优化**

- 用 `baoyu-image-cards` 为每类数据生成独立信息图卡片
- 卡片嵌入到优化后的 Markdown 报告中
- 自动集成到现有 cron 流程

## 信息图卡片定义

### 视觉风格

- 简洁现代风（Apple 风格）
- 白底 + 浅灰卡片背景
- 涨跌色：绿色（涨）/ 红色（跌）/ 灰色（平）
- 字体：无衬线、数字加粗突出
- 宽高比：手机友好竖版（3:4）或方形（1:1）
- 格式：WebP

### 日报卡片（4 张）

| # | 卡片名称 | 内容 | 布局 |
|---|---------|------|------|
| 1 | 市场总览 | ES/NQ/YM/GC 价格+涨跌幅、VIX 数值+变化、隔夜区间 | 仪表盘网格，涨绿跌红，箭头指示方向 |
| 2 | 板块强弱 | 11 个板块 ETF 按涨跌排列 | 水平柱状图/热力条，从强到弱渐变色 |
| 3 | 盘前异动 | Top movers 的 symbol、gap%、量比 | 列表卡片，大号 gap 百分比突出显示 |
| 4 | 关键价位 | SPY/QQQ/IWM 的支撑阻力、VWAP、前日高低 | 每个品种一行，价格标注在数轴示意上 |

### 周报卡片（3 张）

| # | 卡片名称 | 内容 | 布局 |
|---|---------|------|------|
| 1 | 周线总览 | 主要指数周区间、VIX 水平、板块轮动方向 | 与日报卡片 1 类似，突出周区间 |
| 2 | 周线关键价位 | ES/NQ/GC/SPY/QQQ 的周阻力/支撑 | 表格或数轴式布局 |
| 3 | 事件风险日历 | 本周经济数据时间、影响星级、操作建议 | 时间线/日历布局 |

## Markdown 排版优化

### 报告结构变化

1. **报告开头插入"数据速览"区** — frontmatter 之后、正文之前，集中嵌入所有信息图卡片：
   ```markdown
   ## 数据速览
   ![市场总览](images/premarket-2026-04-09-overview.webp)
   ![板块强弱](images/premarket-2026-04-09-sectors.webp)
   ![盘前异动](images/premarket-2026-04-09-movers.webp)
   ![关键价位](images/premarket-2026-04-09-levels.webp)
   ```

2. **数据表格折叠** — 原有表格用 Obsidian callout 折叠，保留可搜索/可复制：
   ```markdown
   > [!info]- 详细数据：指数期货 & VIX
   > | 品种 | 现价 | 涨跌幅 | ... |
   ```

3. **AI 分析部分不变** — 长文技术分析维持原样

4. **消息面精简** — 去掉截断的 summary 引用块，只保留标题 + 来源

### 卡片缺失时的降级行为

- 卡片生成失败时不显示"数据速览"区
- 数据表格自动展开（不折叠）

## 文件结构

```
data/exports/
├── premarket-2026-04-09.md              # 最终报告（含图片引用）
├── images/
│   ├── premarket-2026-04-09-overview.webp
│   ├── premarket-2026-04-09-sectors.webp
│   ├── premarket-2026-04-09-movers.webp
│   └── premarket-2026-04-09-levels.webp
├── weekly-2026-04-09.md
├── images/
│   ├── weekly-2026-04-09-overview.webp
│   ├── weekly-2026-04-09-levels.webp
│   └── weekly-2026-04-09-calendar.webp
```

Obsidian 同步时，图片随报告一起复制到 vault 对应目录。

## 自动化集成

### 新流程

```
数据采集 → 渲染 Markdown → AI 分析 → 合并最终报告 → 生成信息图卡片 → 嵌入卡片到报告 → 同步(报告+图片)到 Obsidian
```

### 新增组件

1. **`CardGenerator` 类**（`src/daytrader/premarket/renderers/cards.py`）
   - 接收 `CollectorResult` 数据
   - 为每种卡片类型组装内容文本（中文标题 + 格式化数据）
   - 通过 Claude Code CLI（`claude -p`）调用 `baoyu-image-cards` skill 生成 WebP 图片（与现有 AI 分析的调用方式一致）
   - 返回生成的图片路径列表
   - 每张卡片的 prompt 包含：卡片类型、数据内容、风格指令（简洁现代/白底/涨跌色）

2. **`MarkdownRenderer.render()` 扩展**
   - 新增 `card_images: list[Path]` 参数
   - 有图片时在报告开头插入"数据速览"区
   - 数据表格用 Obsidian callout 折叠
   - 无图片时数据表格自动展开

3. **cron 脚本更新**
   - `premarket-cron.sh` / `weekly-cron.sh` 在合并 AI 分析后调用卡片生成
   - 同步时把 `images/` 目录一起复制到 Obsidian vault

### 容错设计

- 卡片生成失败不阻塞报告生成
- cron 脚本中卡片生成限时 120 秒，超时跳过

### CLI 扩展

```bash
# 单独重新生成某天的卡片
daytrader pre cards --date 2026-04-09
daytrader weekly cards --date 2026-04-09
```

## 适用数据划分

### 信息图卡片（可视化）
- 期货 & VIX 总览
- 板块强弱排行
- 盘前异动 Top movers
- 关键价位（SPY/QQQ/IWM 支撑阻力）
- 周线关键价位汇总
- 事件风险窗口

### 保留纯文字
- 消息面（新闻标题列表）
- AI 技术分析 & 操盘建议
- 周报的上周回顾、宏观展望等叙述性内容
