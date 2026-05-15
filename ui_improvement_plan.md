# VibeNet Control -- Streamlit UI 美化与优化执行计划

> 版本: 1.0 | 日期: 2026-05-15 | 基准文件: `gui.py` (625 行)

---

## 1. 当前 UI 问题清单

### 1.1 视觉设计问题

| # | 问题 | 位置 (gui.py 行号) | 影响 | 严重度 |
|---|------|---------------------|------|--------|
| V1 | **无全局 CSS 主题注入** -- Streamlit 默认白底蓝调，缺乏品牌感 | L25-29 `st.set_page_config` 未配置 `theme` 参数；全文无 `st.markdown("<style>...")` 全局样式块 | 整体观感廉价，无专业工具感 | 高 |
| V2 | **表格 CSS 硬编码散落** -- `CELL_STYLE` 常量 (L328) 仅定义基础边框，颜色分散在 `_real_row_style`/`_random_row_style` 回调中 | L328 `CELL_STYLE = "padding:8px 12px; border:1px solid #ccc;"`；L390-413 行样式函数 | 修改样式需改多处，不同表格的绿色/蓝色配色无统一色板 | 中 |
| V3 | **表格配色陈旧** -- 深灰表头 `#333`、纯色交替行 `#e8f5e9/#c8e6c9`（绿）和 `#e3f2fd/#bbdefb`（蓝），无圆角无阴影 | L339 `background:#333`；L399-402 绿色行；L410-412 蓝色行 | 视觉停留在 2015 年风格 | 中 |
| V4 | **设备卡片无自定义样式** -- 依赖 `st.container(border=True)` 默认灰边框，卡片内部信息无层次 | L443 `st.container(border=True)` | IP/MAC/厂商/状态/速率/按钮堆叠，难以快速扫描 | 高 |
| V5 | **紧急停止区 CSS 嵌入位置不当** -- 唯一的内联 CSS 块放在页面底部 (L554-567)，而非全局 `<head>` 区域 | L554-567 `st.markdown("<style>.emergency-container {...}</style>")` | CSS 加载时序问题；样式管理分散 | 中 |
| V6 | **无配色系统** -- 状态颜色（绿/黄/红）与功能颜色（蓝/紫）无统一色板 | 全文 | 色彩语义模糊，用户需自行推断含义 | 高 |

### 1.2 用户体验问题

| # | 问题 | 位置 | 影响 | 严重度 |
|---|------|------|------|--------|
| E1 | **表格无 hover 高亮** -- 行悬停无视觉反馈 | L376-384 `<tr>` 无 `:hover` CSS | 用户无法快速跟踪当前关注行 | 高 |
| E2 | **表格无响应式设计** -- 6 列表格在小屏幕上会横向溢出 | L338 `<table style='width:100%...'>` 无 `overflow-x:auto` 包裹层 | 移动端/小窗体验差 | 中 |
| E3 | **状态指示仅为 emoji 文本** -- `"🟢 在线"` / `"🟡 测速中"` / `"🔴 已断网"` 缺乏动画增强 | L357-361 表格状态列；L454-459 卡片状态 | 状态变化不够醒目 | 中 |
| E4 | **速率显示格式单调** -- `"↓ 1.5 MB/s  ↑ 0.8 MB/s"` 纯文本无视觉强化 | L366-372 表格速率列；L463-474 卡片速率 | 无法快速判断速率高低 | 中 |
| E5 | **卡片信息密度均一** -- IP/MAC/厂商/状态/速率全部使用相同字号和权重 | L445-474 卡片内容 | 用户无法快速定位关键信息（IP + 状态） | 高 |
| E6 | **按钮无自定义样式** -- 测速/断网/恢复按钮全部使用 Streamlit 默认 `primary`/`secondary` 样式 | L479-533 卡片按钮区 | 危险操作（断网）的警示性不足 | 中 |
| E7 | **侧边栏进度条无自定义** -- 批量测速进度条使用 `st.progress()` 默认样式 | L245 `st.progress(cur / tot)` | 缺乏定制品牌感 | 低 |
| E8 | **自动刷新复选框位置偏下** -- 滚动较长侧边栏后才能看到 | L274-276 | 首次使用者不易发现 | 低 |

### 1.3 功能/代码结构问题

| # | 问题 | 位置 | 影响 | 严重度 |
|---|------|------|------|--------|
| F1 | **CSS 未集中管理** -- 全局样式、表格样式、卡片样式分布在代码各处 | 全文 | 维护困难，改色需全局搜索 | 高 |
| F2 | **表格 HTML 构建函数返回裸字符串** -- `_build_table()` 返回 `"".join(html)` 链式调用 | L331-386 | 难以在中间插入包裹层（如 `overflow-x:auto` div） | 低 |
| F3 | **断网设备行背景色在两种表格中不同** -- 真实设备 `#ffcdd2`，随机设备未定义断网色 | `_real_row_style` L400-401 vs `_random_row_style` L410-412 | 随机化设备断网时无粉红背景提示 | 中 |
| F4 | **紧急停止按钮样式为 `type="secondary"`** -- 警示性不足 | L587 `type="secondary"` | 紧急操作应当视觉突出 | 中 |

---

## 2. 优化方案总览

### 2.1 设计语言: "Cyber-Network Terminal"

- **风格**: 暗色主题 + 霓虹点缀，类似网络运维终端的现代 Web 化表达
- **联想**: Wireshark 的功能性 + Grafana 的美观性
- **核心理念**: 数据密度与可读性并重，状态变化一目了然

### 2.2 配色方案

| 令牌 | 色值 | 用途 |
|------|------|------|
| `--bg-primary` | `#0B1120` | 主背景 (Streamlit main 区域) |
| `--bg-secondary` | `#111827` | 侧边栏/卡片背景 |
| `--bg-surface` | `#1A2332` | 表格行交替色 A / 卡片悬停 |
| `--bg-surface-alt` | `#1F2A3A` | 表格行交替色 B |
| `--border` | `#2D3A4A` | 默认边框 |
| `--text-primary` | `#E2E8F0` | 主文字 |
| `--text-secondary` | `#94A3B8` | 次要文字 (MAC/厂商) |
| `--text-muted` | `#64748B` | 禁用文字 |
| `--accent` | `#00D4AA` | 主强调色 / 在线状态 / 成功 |
| `--accent-glow` | `rgba(0,212,170,0.3)` | 强调色发光阴影 |
| `--warning` | `#F59E0B` | 警告 / 测速中 |
| `--warning-glow` | `rgba(245,158,11,0.3)` | 警告发光 |
| `--danger` | `#EF4444` | 断网 / 停止 / 紧急 |
| `--danger-glow` | `rgba(239,68,68,0.3)` | 危险发光 |
| `--info` | `#3B82F6` | 信息 / 链接 |
| `--random-tag` | `#8B5CF6` | 随机化 MAC 设备标识 |

### 2.3 组件规格

| 组件 | 规格 |
|------|------|
| **表头** | 渐变背景 `#1A2332 -> #111827`, 文字 `--text-primary`, 圆角顶角 8px |
| **表格行** | hover 半透明覆盖 `rgba(0,212,170,0.06)`, 断网行 `rgba(239,68,68,0.12)` |
| **表格容器** | `border-radius: 8px; border: 1px solid var(--border); overflow: hidden;` |
| **设备卡片** | `background: var(--bg-surface); border-radius: 12px; border: 1px solid var(--border); padding: 16px;` |
| **卡片状态指示器** | 8px 圆点 + CSS pulse 动画 (在线=绿脉冲, 测速=黄脉冲, 断网=红常亮) |
| **速率显示** | 下载色 `--accent`, 上传色 `--info`, 等宽字体 |
| **按钮** | 自定义 CSS 类覆盖 Streamlit 默认: `.stButton>button` 选择器 |

### 2.4 字体体系

- 主字体: `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`
- 等宽字体 (IP/MAC/速率): `"SF Mono", "Fira Code", "JetBrains Mono", monospace`
- 表头: `font-weight: 600; font-size: 13px; letter-spacing: 0.05em; text-transform: uppercase;`

---

## 3. 分优先级改进计划

### P0 -- 立即改进（高视觉冲击，低风险，不改核心逻辑）

#### P0-1: 全局 CSS 主题注入

**变更位置**: `gui.py` L29 之后 (紧跟 `st.set_page_config`)

**方案**:
在 `st.set_page_config` 后立即注入一个集中式 `<style>` 块，包含:
- CSS 自定义属性 (`:root` 变量)
- Streamlit 组件覆盖 (侧边栏、按钮、进度条、metric 等)
- 表格/卡片/紧急停止全局样式
- 状态指示器动画 `@keyframes`

**代码量**: ~200 行 CSS，1 个 `st.markdown(..., unsafe_allow_html=True)` 调用

**风险**: 极低 (纯 CSS，不改 Python 逻辑)

---

#### P0-2: 表格全面美化

**变更位置**: `gui.py` L328-418 (CELL_STYLE, _build_table, 行样式函数, 渲染调用)

**改进点**:

1. **表格容器包裹**: 在每个 `<table>` 外侧加 `<div style="overflow-x:auto; border-radius:8px; ...">` 实现响应式滚动
2. **表头重设计**: 使用 CSS 类而非内联 `background:#333`，应用渐变 + uppercase + letter-spacing
3. **行 hover 效果**: 通过全局 CSS 添加 `tr:hover` 规则，使用半透明覆盖层
4. **断网行统一**: 使用 CSS 类 `.row-killed` 替代条件内联背景色
5. **速率颜色编码**: 下载箭头使用 `--accent` 色，上传箭头使用 `--info` 色
6. **随机设备行**: 使用 CSS 类 `.row-random` 降低对比度，与真实设备视觉区分更明显

**具体 CSS 类**:
```css
/* 表格容器 */
.vibenet-table-wrapper {
    overflow-x: auto;
    border-radius: 8px;
    border: 1px solid var(--border);
    margin-bottom: 20px;
}
.vibenet-table { width: 100%; border-collapse: collapse; font-size: 14px; }
.vibenet-table thead th {
    background: linear-gradient(180deg, #1A2332 0%, #111827 100%);
    color: var(--text-primary);
    padding: 12px 14px;
    font-weight: 600;
    font-size: 12px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    text-align: left;
    border-bottom: 2px solid var(--accent);
}
.vibenet-table tbody td {
    padding: 10px 14px;
    border-bottom: 1px solid var(--border);
}
.vibenet-table tbody tr:hover {
    background: rgba(0,212,170,0.06) !important;
}
.vibenet-table .row-real-even { background: var(--bg-surface); }
.vibenet-table .row-real-odd  { background: var(--bg-surface-alt); }
.vibenet-table .row-random     { opacity: 0.75; }
.vibenet-table .row-killed     { background: rgba(239,68,68,0.12) !important; }
.vibenet-table .speed-down     { color: var(--accent); font-weight: 600; }
.vibenet-table .speed-up       { color: var(--info); font-weight: 600; }
```

**代码量**: CSS ~60 行, Python 重构 `_build_table()` ~40 行修改

**风险**: 低 (保持相同的 HTML 结构，仅替换内联样式为 CSS 类)

---

#### P0-3: 设备控制卡片重设计

**变更位置**: `gui.py` L425-545 (`_render_device_cards` 函数)

**改进点**:

1. **卡片自定义 HTML 替代 `st.container(border=True)`**: 使用 `st.markdown` 渲染带 CSS 类的卡片 HTML，而非依赖 Streamlit 默认容器
2. **信息层次**: 
   - 第1层 (最重要): IP 地址 + 状态指示器圆点 — 大号加粗
   - 第2层: MAC 地址 — 等宽小字灰色
   - 第3层: 厂商名 — 小字灰色
   - 第4层: 速率信息 — 等宽彩色
3. **状态指示器**: 8px 圆点 + CSS pulse 动画
4. **按钮区统一**: 两按钮水平排列，应用自定义 CSS 类

**卡片 CSS**:
```css
.vibenet-card {
    background: var(--bg-surface);
    border-radius: 12px;
    border: 1px solid var(--border);
    padding: 16px;
    margin-bottom: 12px;
    transition: border-color 0.2s, box-shadow 0.2s;
}
.vibenet-card:hover {
    border-color: var(--accent);
    box-shadow: 0 0 12px var(--accent-glow);
}
.vibenet-card .card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;
}
.vibenet-card .card-ip {
    font-size: 16px;
    font-weight: 700;
    color: var(--text-primary);
    font-family: monospace;
}
.vibenet-card .card-mac {
    font-size: 12px;
    color: var(--text-muted);
    font-family: monospace;
}
.vibenet-card .card-vendor {
    font-size: 12px;
    color: var(--text-secondary);
    margin-bottom: 10px;
}
.vibenet-card .card-speed {
    font-family: monospace;
    font-size: 13px;
    margin-bottom: 12px;
    padding: 8px 10px;
    background: rgba(0,0,0,0.2);
    border-radius: 6px;
}
```

**状态指示器 CSS**:
```css
.status-dot {
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 50%;
    margin-right: 6px;
}
.status-online  { background: var(--accent); }
.status-testing { background: var(--warning); animation: pulse 1.5s infinite; }
.status-killed  { background: var(--danger); }
@keyframes pulse {
    0%, 100% { opacity: 1; box-shadow: 0 0 0 0 currentColor; }
    50%      { opacity: 0.7; box-shadow: 0 0 6px 2px currentColor; }
}
```

**替代方案考虑**: 由于卡片包含交互按钮 (Streamlit button)，不能完全替换为纯 HTML。应采用**混合方案**:
- 卡片头部信息 (IP/MAC/厂商/状态) 用 `st.markdown` 渲染带 CSS 类的 HTML
- 速率区域用 `st.markdown` 渲染
- 按钮保留 `st.button` 但通过全局 CSS 覆盖样式
- 保持 `st.columns(COLS_PER_ROW)` 布局骨架

**代码量**: CSS ~80 行, Python 重构 `_render_device_cards` ~50 行修改

**风险**: 中低 (按钮逻辑不变，仅重新组织 markdown 渲染并添加 CSS 类)

---

#### P0-4: 紧急停止区强化

**变更位置**: `gui.py` L554-613

**改进点**:
1. 将紧急停止 CSS 移至全局 `<style>` 块 (不再嵌入底部)
2. 强化 `.emergency-container` 样式: 暗红背景 + 边框发光
3. 紧急停止按钮覆盖为红色 `type="primary"` 样式

**更新 CSS**:
```css
.emergency-container {
    border: 2px solid var(--danger);
    border-radius: 12px;
    padding: 20px;
    background: rgba(239,68,68,0.08);
    box-shadow: 0 0 20px var(--danger-glow);
}
.emergency-container .stButton > button {
    background: var(--danger) !important;
    border-color: var(--danger) !important;
    color: #fff !important;
    font-weight: 700;
}
```

**代码量**: CSS ~15 行, 删除分散的 CSS 注入 ~10 行

**风险**: 极低

---

### P1 -- 重要改进

#### P1-1: 侧边栏美化

**变更位置**: `gui.py` L207-276

**改进点**:
1. 扫描按钮保持 `type="primary"`，但覆盖颜色为 `--accent`
2. `st.metric` 使用 CSS 类添加左侧色条
3. 状态区卡片化: 将批量/手动/待命状态封装在带背景色的圆角容器中
4. 进度条自定义: 覆盖 Streamlit 默认进度条颜色为 `--accent`

**CSS**:
```css
/* 侧边栏 metric */
[data-testid="stMetric"] {
    background: var(--bg-surface);
    border-radius: 8px;
    padding: 8px 12px;
    border-left: 3px solid var(--accent);
}
/* 侧边栏进度条 */
[data-testid="stSidebar"] .stProgress > div > div {
    background: var(--accent);
}
/* 侧边栏状态卡片 */
.sidebar-status {
    background: var(--bg-surface);
    border-radius: 8px;
    padding: 12px;
    text-align: center;
    border: 1px solid var(--border);
}
```

**代码量**: CSS ~40 行, 布局调整 ~10 行

**风险**: 低

---

#### P1-2: 表格排序/筛选增强 (视觉层面)

**变更位置**: `gui.py` L396-418

**改进点**:
1. 在表格上方添加汇总统计行 (自定义 HTML): 显示 "在线 X / 测速中 Y / 已断网 Z"
2. 为随机化设备表格添加信息提示横幅

**代码量**: HTML ~20 行

**风险**: 极低

---

#### P1-3: 主标题与副标题美化

**变更位置**: `gui.py` L290-291

**改进点**:
使用 `st.markdown` 渲染自定义标题 HTML，替代 `st.title`:
- 标题带 `--accent` 色发光效果
- 副标题更小、更淡
- 添加分隔线

**代码量**: CSS ~20 行, 替换 2 行

**风险**: 极低

---

### P2 -- 锦上添花

#### P2-1: 速率微型仪表盘

**变更位置**: 卡片速率区域 (L462-474)

**描述**: 在设备卡片中，用 CSS 进度条表示当前速率占峰值的比例，提供直观的速度感知。

**CSS**:
```css
.speed-bar-wrapper {
    height: 4px;
    background: rgba(255,255,255,0.1);
    border-radius: 2px;
    margin-top: 4px;
}
.speed-bar-fill {
    height: 4px;
    border-radius: 2px;
    background: linear-gradient(90deg, var(--info), var(--accent));
    transition: width 0.3s ease;
}
```

**代码量**: CSS ~15 行, HTML 构建 ~10 行

**风险**: 低 (纯 CSS 视觉增强)

---

#### P2-2: 状态脉冲动画增强

**变更位置**: 全局 CSS

**描述**: 
- 测速中设备在表格和卡片中显示呼吸脉冲效果
- 断网设备显示红色常亮闪烁

已有 P0-3 的 `@keyframes pulse` 基础，此处增强为多状态动画。

**风险**: 低

---

#### P2-3: 自动刷新指示器动画

**变更位置**: `gui.py` L274-276

**描述**: 自动刷新复选框旁添加旋转图标 (CSS animation)，表示"监控中"。

**风险**: 低

---

#### P2-4: 工具提示 (Tooltip) 增强

**变更位置**: 卡片按钮区 (L479-533)

**描述**: 为断网/恢复按钮添加自定义 `title` 属性增强 `help` 参数，提供更明确的操作说明。

**风险**: 极低

---

## 4. 具体 CSS/代码方案 (汇总)

### 4.1 全局 CSS 注入位置与结构

在 `gui.py` L29 (`st.set_page_config` 之后) 插入:

```python
# ---------------------------------------------------------------------------
# 全局 CSS 主题
# ---------------------------------------------------------------------------
st.markdown("""
<style>
/* ===== CSS 自定义属性 ===== */
:root {
    --bg-primary: #0B1120;
    --bg-secondary: #111827;
    --bg-surface: #1A2332;
    --bg-surface-alt: #1F2A3A;
    --border: #2D3A4A;
    --text-primary: #E2E8F0;
    --text-secondary: #94A3B8;
    --text-muted: #64748B;
    --accent: #00D4AA;
    --accent-glow: rgba(0,212,170,0.3);
    --warning: #F59E0B;
    --warning-glow: rgba(245,158,11,0.3);
    --danger: #EF4444;
    --danger-glow: rgba(239,68,68,0.3);
    --info: #3B82F6;
    --random-tag: #8B5CF6;
}

/* ===== Streamlit 全局覆盖 ===== */
/* 主背景 */
.stApp {
    background: var(--bg-primary);
}
/* 侧边栏 */
[data-testid="stSidebar"] {
    background: var(--bg-secondary);
    border-right: 1px solid var(--border);
}
/* 侧边栏内部 */
[data-testid="stSidebar"] .stMarkdown,
[data-testid="stSidebar"] .stCaption {
    color: var(--text-secondary);
}
/* 按钮全局 */
.stButton > button {
    border-radius: 8px !important;
    font-weight: 600 !important;
    transition: all 0.2s !important;
}
.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
}
/* Primary 按钮覆盖为 accent 色 */
.stButton > button[kind="primary"] {
    background: var(--accent) !important;
    border-color: var(--accent) !important;
    color: #0B1120 !important;
}
/* Secondary / 危险按钮 */
.stButton > button[kind="secondary"] {
    background: transparent !important;
    border: 1px solid var(--border) !important;
    color: var(--text-primary) !important;
}
/* 分割线 */
hr {
    border-color: var(--border) !important;
}
/* 信息框 */
[data-testid="stInfo"] {
    background: rgba(59,130,246,0.1) !important;
    border-color: rgba(59,130,246,0.3) !important;
}
</style>
""", unsafe_allow_html=True)
```

### 4.2 表格 CSS (追加到全局块)

```css
/* ===== 设备表格 ===== */
.vibenet-table-wrapper {
    overflow-x: auto;
    border-radius: 8px;
    border: 1px solid var(--border);
    margin: 16px 0 24px 0;
    background: var(--bg-primary);
}
.vibenet-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
    color: var(--text-primary);
}
.vibenet-table thead th {
    background: linear-gradient(180deg, #1A2332 0%, #111827 100%);
    padding: 12px 14px;
    font-weight: 600;
    font-size: 11px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    text-align: left;
    border-bottom: 2px solid var(--accent);
    white-space: nowrap;
}
.vibenet-table tbody td {
    padding: 10px 14px;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
}
.vibenet-table tbody tr {
    transition: background 0.15s;
}
.vibenet-table tbody tr:hover {
    background: rgba(0,212,170,0.06) !important;
}
/* 交替行 */
.vibenet-table .row-real-even { background: var(--bg-surface); }
.vibenet-table .row-real-odd  { background: var(--bg-surface-alt); }
/* 随机化设备行 */
.vibenet-table .row-random-even,
.vibenet-table .row-random-odd { 
    opacity: 0.75; 
    background: var(--bg-surface);
}
/* 断网行 */
.vibenet-table .row-killed {
    background: rgba(239,68,68,0.12) !important;
}
.vibenet-table .row-killed td {
    color: var(--danger);
}
/* 速率列颜色 */
.vibenet-table .speed-down { color: var(--accent); font-weight: 600; }
.vibenet-table .speed-up   { color: var(--info); font-weight: 600; }
/* IP 列加粗 */
.vibenet-table .col-ip { font-weight: 600; font-family: monospace; }
/* MAC 列等宽 */
.vibenet-table .col-mac { font-family: monospace; color: var(--text-secondary); }
/* 状态列 */
.vibenet-table .col-status { font-weight: 600; }
```

### 4.3 设备卡片 CSS (追加到全局块)

```css
/* ===== 设备控制卡片 ===== */
.vibenet-card {
    background: var(--bg-surface);
    border-radius: 12px;
    border: 1px solid var(--border);
    padding: 14px 16px;
    margin-bottom: 8px;
    transition: border-color 0.2s, box-shadow 0.2s;
}
.vibenet-card:hover {
    border-color: var(--accent);
    box-shadow: 0 0 16px var(--accent-glow);
}
.vibenet-card .card-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 4px;
}
.vibenet-card .card-ip {
    font-size: 15px;
    font-weight: 700;
    color: var(--text-primary);
    font-family: monospace;
}
.vibenet-card .card-tag {
    font-size: 10px;
    background: var(--random-tag);
    color: #fff;
    padding: 1px 6px;
    border-radius: 4px;
    font-weight: 600;
}
.vibenet-card .card-mac {
    font-size: 11px;
    color: var(--text-muted);
    font-family: monospace;
}
.vibenet-card .card-vendor {
    font-size: 11px;
    color: var(--text-secondary);
    margin-bottom: 8px;
}
.vibenet-card .card-speed-box {
    font-family: monospace;
    font-size: 12px;
    margin: 8px 0;
    padding: 8px 10px;
    background: rgba(0,0,0,0.25);
    border-radius: 6px;
    border-left: 3px solid var(--accent);
}
.vibenet-card .card-speed-box .dl { color: var(--accent); font-weight: 600; }
.vibenet-card .card-speed-box .ul { color: var(--info); font-weight: 600; }

/* 状态指示器 */
.status-indicator {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-weight: 600;
    font-size: 13px;
}
.status-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    display: inline-block;
}
.status-dot.online  { background: var(--accent); }
.status-dot.testing { 
    background: var(--warning); 
    animation: vibenet-pulse 1.5s ease-in-out infinite; 
}
.status-dot.killed  { background: var(--danger); }

@keyframes vibenet-pulse {
    0%, 100% { box-shadow: 0 0 0 0 currentColor; opacity: 1; }
    50%      { box-shadow: 0 0 8px 2px currentColor; opacity: 0.6; }
}

/* 随机化设备卡片 */
.vibenet-card.randomized {
    opacity: 0.8;
    border-color: rgba(139,92,246,0.3);
}
```

### 4.4 紧急停止 CSS (追加到全局块)

```css
/* ===== 紧急停止 ===== */
.emergency-container {
    border: 2px solid var(--danger);
    border-radius: 12px;
    padding: 20px 24px;
    background: rgba(239,68,68,0.06);
    margin: 24px 0;
}
```

### 4.5 标题区 CSS

```css
/* ===== 主标题 ===== */
.vibenet-title {
    font-size: 32px;
    font-weight: 800;
    color: var(--text-primary);
    margin-bottom: 0;
}
.vibenet-title .accent {
    color: var(--accent);
}
.vibenet-subtitle {
    font-size: 14px;
    color: var(--text-muted);
    margin-top: 4px;
    margin-bottom: 24px;
}
```

---

## 5. 改动量估计

| 改进项 | 优先级 | CSS 新增 (行) | Python 修改 (行) | Python 删除 (行) | 风险等级 | 预估工作量 |
|--------|--------|---------------|-------------------|-------------------|----------|-----------|
| P0-1 全局 CSS 主题 | P0 | ~200 | +2 (注入调用) | 0 | 极低 | 30 分钟 |
| P0-2 表格美化 | P0 | ~60 | ~40 (重构 _build_table) | ~10 | 低 | 45 分钟 |
| P0-3 卡片重设计 | P0 | ~80 | ~50 (重构 _render_device_cards) | ~20 | 中低 | 1 小时 |
| P0-4 紧急停止强化 | P0 | ~15 | ~5 | ~10 (移除分散 CSS) | 极低 | 15 分钟 |
| P1-1 侧边栏美化 | P1 | ~40 | ~10 | ~5 | 低 | 30 分钟 |
| P1-2 表格汇总统计 | P1 | ~10 | ~20 | 0 | 极低 | 20 分钟 |
| P1-3 标题美化 | P1 | ~20 | ~5 | ~3 | 极低 | 15 分钟 |
| P2-1 速率仪表盘 | P2 | ~15 | ~10 | 0 | 低 | 20 分钟 |
| P2-2 动画增强 | P2 | ~10 | 0 | 0 | 极低 | 10 分钟 |
| P2-3 自动刷新指示器 | P2 | ~10 | ~5 | 0 | 极低 | 10 分钟 |
| P2-4 Tooltip 增强 | P2 | 0 | ~10 | 0 | 极低 | 10 分钟 |
| **合计** | | **~460 行 CSS** | **~157 行 Python** | **~48 行删除** | | **约 4.5 小时** |

### 净增行数估计

- 当前 `gui.py`: 625 行
- 预计改动后: ~735 行 (+110 行，主要是 CSS 块和 HTML 重构)
- CSS 注入块: ~200 行集中在文件头部
- Python 逻辑重写: 部分函数行数增加 (更结构化的 HTML 生成)，部分精简

---

## 6. 实施顺序建议

```
Phase 1 (Day 1, ~2h):
  1. P0-1 全局 CSS 主题注入       ← 基础设施，后续所有改进依赖此步
  2. P0-4 紧急停止强化            ← 移除分散 CSS，集中管理
  3. P1-3 标题美化                ← 快速验证主题效果

Phase 2 (Day 1, ~1.5h):
  4. P0-2 表格全面美化            ← 最大视觉改善
  5. P1-2 表格汇总统计            ← 与表格美化配套

Phase 3 (Day 2, ~1h):
  6. P0-3 设备控制卡片重设计      ← 第二大视觉改善
  7. P1-1 侧边栏美化              ← 与卡片配套

Phase 4 (Day 2, ~1h):
  8. P2-1 速率微型仪表盘
  9. P2-2 状态脉冲动画增强
  10. P2-3 自动刷新指示器动画
  11. P2-4 Tooltip 增强
```

---

## 7. 约束合规性检查

| 约束 | 合规 | 说明 |
|------|------|------|
| 纯 Streamlit + 内嵌 CSS | 是 | 所有样式通过 `st.markdown("<style>...</style>", unsafe_allow_html=True)` 注入 |
| 表格继续使用 HTML 渲染 | 是 | `_build_table()` 保持 HTML 字符串构建，仅改用 CSS 类替代内联样式 |
| 不修改 core/ 模块 | 是 | 所有改动在 `gui.py` 内，不动 `core/scanner.py`, `core/spoofing.py`, `core/monitor.py` |
| 保持所有现有功能 | 是 | 扫描/测速/断网/恢复/遍历/紧急停止逻辑完全不变 |
| CSS 通过 st.markdown 注入 | 是 | 与现有 L554-567 模式一致 |
| 保持中文界面 | 是 | 所有用户可见文字维持中文 |

---

## 附录 A: 当前表格行样式函数对比

**现状** (分散定义, 无断网色统一):
```python
# L399-402 真实设备
def _real_row_style(idx, is_killed):
    if is_killed: return "#ffcdd2", "#000"
    bg = "#e8f5e9" if idx % 2 == 0 else "#c8e6c9"
    return bg, "#000"

# L410-412 随机设备 (无断网处理!)
def _random_row_style(idx, is_killed):
    bg = "#e3f2fd" if idx % 2 == 0 else "#bbdefb"
    return bg, "#777"
```

**改进后** (统一 CSS 类):
```python
def _row_class(idx, is_killed, is_random):
    if is_killed:
        return "row-killed"
    if is_random:
        return f"row-random-{'even' if idx % 2 == 0 else 'odd'}"
    return f"row-real-{'even' if idx % 2 == 0 else 'odd'}"
```

## 附录 B: 卡片 HTML 模板 (P0-3 重构方向)

**现状** (多个 st.markdown/st.caption 调用，层次模糊):
```python
# L445-474
st.markdown(f"**{ip}**{tag}")
st.caption(f"{mac}")
st.caption(f"{vendor}")
# ... 状态 + 速率分散在多个 st.markdown/st.caption 中
```

**改进后** (单次 st.markdown 渲染结构化 HTML):
```python
with cols[j]:
    # 卡片头部 (IP + 状态 + 随机标签)
    card_html = f"""
    <div class="vibenet-card{' randomized' if is_randomized_section else ''}">
      <div class="card-row">
        <span class="card-ip">{ip}</span>
        {f'<span class="card-tag">随机MAC</span>' if is_randomized_section else ''}
      </div>
      <div class="status-indicator">
        <span class="status-dot {status_class}"></span>
        <span>{status_text}</span>
      </div>
      <div class="card-mac">{mac}</div>
      <div class="card-vendor">{vendor}</div>
    """
    # 速率区域 (条件渲染)
    if speed_html:
        card_html += f'<div class="card-speed-box">{speed_html}</div>'
    card_html += "</div>"
    st.markdown(card_html, unsafe_allow_html=True)
    
    # 按钮保留 st.button (需交互)
    if not is_gateway:
        c1, c2 = st.columns(2)
        with c1: ...  # 测速/停止按钮
        with c2: ...  # 断网/恢复按钮
```
