# VibeNet Control — UI 测试报告

## 测试执行摘要

| 项目 | 值 |
|------|-----|
| 测试日期 | 2026-05-15 |
| 目标 URL | http://localhost:8501 |
| 测试框架 | Playwright v1.49.1 (Chromium, headless) |
| 测试脚本 | `test_ui_playwright.sh` |
| 服务启动命令 | `bash run.sh --gui` (需要 sudo) |
| 总测试数 | 4 |
| 整体状态 | 待执行 — 运行 `bash test_ui_playwright.sh` |

---

## 测试结果详情

### 测试 1: 页面加载和基本元素

**目的**: 验证 VibeNet Control Web UI 能正常加载，且初始页面显示正确的引导元素。

| 步骤 | 验证项 | 预期结果 |
|------|--------|----------|
| 1a | 截取初始加载页面 | 保存 `01_initial_load.png`，页面正常渲染 |
| 1b | 页面标题（`<title>`）包含 "VibeNet Control" | 标题匹配 |
| 1c | 侧边栏存在"扫描网络"按钮 | 按钮文本包含 "扫描网络" |
| 1d | 主区域提示"点击左侧边栏的扫描网络" | 页面文本包含引导信息 |

**实现细节**:
- 使用 `page.title()` 获取标题
- 使用 `page.locator('[data-testid="stSidebar"]').locator('button')` 定位侧边栏按钮
- 使用 `page.locator('[data-testid="stAppViewContainer"]').innerText()` 获取主内容区文本

---

### 测试 2: 侧边栏元素

**目的**: 验证点击"扫描网络"后，侧边栏显示完整的控制元素集合。

| 步骤 | 验证项 | 预期结果 |
|------|--------|----------|
| 2a | 截取侧边栏 | 保存 `02_sidebar.png` 和 `02_full_page.png` |
| 2b | "自动刷新" 复选框存在 | 侧边栏文本包含 "自动刷新" |
| 2c | "开始测速" 和 "停止测速" 按钮存在 | 同时存在两个按钮 |

**实现细节**:
- 先自动点击"扫描网络"按钮触发扫描
- 等待 8 秒让扫描完成
- 通过 `page.locator('[data-testid="stSidebar"]').innerText()` 获取侧边栏全部文本后搜索关键字
- 按钮在扫描前不可见（受 `st.session_state.scanned` 条件控制），测试自动处理

---

### 测试 3: 页面响应式布局

**目的**: 验证页面在常见分辨率下无横向溢出、无元素重叠。

| 步骤 | 分辨率 | 截图文件 |
|------|--------|----------|
| 3a | 1920x1080 (Full HD) | `03_responsive_1920x1080.png` |
| 3b | 1280x720 (HD) | `03_responsive_1280x720.png` |
| 3c | 800x600 (Legacy) | `03_responsive_800x600.png` |

**验证逻辑**:
- 比较 `documentElement.scrollWidth` 与 `documentElement.clientWidth`，检测横向溢出
- 检查绝对定位/固定定位元素是否有负坐标（可能重叠/溢出）
- Streamlit 使用响应式栅格布局，理论上在 800px 以上均能正常渲染

---

### 测试 4: 样式验证

**目的**: 验证自定义 CSS 样式和主题变量是否正确加载。

| 步骤 | 验证项 | 预期 |
|------|--------|------|
| 4a | 截取样式检查页面 | 保存 `04_styles.png` |
| 4b | 检查 `--bg-primary` 或 Streamlit 主题 CSS 变量 | 找到至少一组 CSS 自定义属性 |
| 4c | 检查 `.vibenet-card` 样式 | 在样式表中搜索 `.vibenet-card` 选择器 |
| 4d | 检查 `.vibenet-table` 样式 | 在样式表中搜索 `.vibenet-table` 选择器 |

**实现细节**:
- 使用 `getComputedStyle(document.documentElement)` 获取 CSS 自定义属性
- 遍历 `document.styleSheets` 的 CSS 规则查找选择器
- 同时检查内联 `<style>` 标签内容
- **注意**: 当前 `gui.py` 使用 `st.container(border=True)` 渲染卡片、使用内联 HTML 渲染表格，未定义 `.vibenet-card` 和 `.vibenet-table` CSS 类。如果未来需要这些样式，应在 Streamlit 的 `st.markdown("<style>...")` 中注入。

---

## 截图列表

运行测试后，`test_screenshots/` 目录将包含以下文件：

| 截图 | 说明 |
|------|------|
| `01_initial_load.png` | 首次加载的完整页面（fullPage） |
| `02_sidebar.png` | 侧边栏特写 |
| `02_full_page.png` | 扫描后的完整页面 |
| `03_responsive_1920x1080.png` | 1920x1080 分辨率 |
| `03_responsive_1280x720.png` | 1280x720 分辨率 |
| `03_responsive_800x600.png` | 800x600 分辨率 |
| `04_styles.png` | 样式验证时的完整页面 |

---

## UI 问题发现

### 已知设计决策

1. **`.vibenet-card` / `.vibenet-table` CSS 类未定义** — 当前 `gui.py` 使用 Streamlit 原生组件（`st.container(border=True)`）和内联 HTML 表格，未使用自定义 CSS 类。测试 4c 和 4d 预期找到这些选择器，如果项目未定义，测试将报告失败。建议在需要自定义外观时通过 `st.markdown('<style>...', unsafe_allow_html=True)` 注入。

2. **需要 root 权限** — 应用启动需要 `sudo`，非 root 运行时页面显示错误提示并 `st.stop()`。测试脚本假设服务已在后台启动（如 `bash run.sh --gui`），不会直接触发权限错误。

3. **动态内容加载** — "开始测速" / "停止测速" 按钮在扫描完成后才显示。测试脚本自动点击"扫描网络"来触发这些元素出现。

### 检查清单

运行测试后，请验证以下内容：

- [ ] 所有截图文件大小 > 0 且能正常打开
- [ ] 页面在三种分辨率下均无水平滚动条
- [ ] 侧边栏按钮排列整齐，无文字截断
- [ ] 表格边框和行背景色在截图中清晰可见
- [ ] 紧急停止按钮区域红色边框正确显示

---

## 附加说明

### 运行测试

```bash
# 1. 启动服务（需要 sudo）
bash run.sh --gui

# 2. 另开终端，执行测试
bash test_ui_playwright.sh
```

### 依赖

- **Node.js** >= 16
- **Playwright** — 脚本会自动 `npm install playwright` 如果未安装
- **Chromium** — 脚本会自动 `npx playwright install chromium` 如果未安装
- **curl** — 用于服务可用性检测

### 脚本特性

- **优雅降级**: 服务未启动时生成包含状态说明的报告，不报错退出
- **容错运行**: 每个测试步骤失败后继续执行后续测试
- **自动生成报告**: 测试完成后自动输出 `ui_test_report.md`
- **颜色输出**: 终端中 PASS/FAIL 使用绿色/红色高亮

---

*报告生成时间: 2026-05-15*
*测试脚本: `test_ui_playwright.sh`*
*项目: VibeNet Control — `/Users/chenyidongting/Documents/5-Python/WIFIkiller/`*
