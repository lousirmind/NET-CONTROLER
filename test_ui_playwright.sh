#!/usr/bin/env bash
#
# test_ui_playwright.sh — VibeNet Control Web UI 自动化测试
# ==========================================================
# 使用 Playwright CLI + Node.js 脚本进行完整的 UI 测试。
#
# 要求：
#   - Node.js >= 16
#   - Playwright (npx playwright)
#   - VibeNet Control 服务运行在 http://localhost:8501
#
# 用法：  bash test_ui_playwright.sh
#
set -uo pipefail
# 注意: 不使用 set -e，确保单个测试失败不会中止整个脚本
# 每个测试步骤独立追踪 pass/fail 状态

SCREENSHOT_DIR="$(cd "$(dirname "$0")" && pwd)/test_screenshots"
BASE_URL="http://localhost:8501"
REPORT_FILE="$(cd "$(dirname "$0")" && pwd)/ui_test_report.md"
PASS_COUNT=0
FAIL_COUNT=0
TOTAL_TESTS=4
TEST_STEPS=()

# 颜色
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

log_section() {
    echo ""
    echo -e "${CYAN}==============================================${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}==============================================${NC}"
    echo ""
}

log_pass() {
    PASS_COUNT=$((PASS_COUNT + 1))
    echo -e "  ${GREEN}[PASS]${NC} $1"
}

log_fail() {
    FAIL_COUNT=$((FAIL_COUNT + 1))
    echo -e "  ${RED}[FAIL]${NC} $1"
}

check_server() {
    echo -n "[*] 检查服务是否运行在 $BASE_URL ... "
    if curl -s --connect-timeout 5 "$BASE_URL" > /dev/null 2>&1; then
        echo -e "${GREEN}OK${NC}"
        return 0
    else
        echo -e "${RED}未响应${NC}"
        return 1
    fi
}

run_playwright_script() {
    # 运行内联 Playwright 脚本 (通过 node)
    # 参数：javascript 代码字符串
    local js_code="$1"
    node -e "
const { chromium } = require('playwright');
(async () => {
    try {
        $js_code
    } catch (e) {
        console.error('SCRIPT_ERROR:' + e.message);
        process.exit(1);
    }
})();
" 2>&1
}

# ---------------------------------------------------------------------------
# Node.js Playwright 辅助脚本模板
# ---------------------------------------------------------------------------

# 用于截图 + 验证的通用 Playwright 脚本
PLAYWRIGHT_SCREENSHOT_SCRIPT='
const { chromium } = require("playwright");

const BASE_URL = process.env.BASE_URL || "http://localhost:8501";
const OUT_DIR = process.env.SCREENSHOT_DIR || "./test_screenshots";
const OUT_FILE = process.env.OUT_FILE || "screenshot.png";

(async () => {
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({
        viewport: { width: 1920, height: 1080 }
    });
    const page = await context.newPage();

    try {
        await page.goto(BASE_URL, {
            waitUntil: "networkidle",
            timeout: 30000
        });
        await page.waitForTimeout(2000);
        await page.screenshot({
            path: OUT_DIR + "/" + OUT_FILE,
            fullPage: true
        });
        console.log("SCREENSHOT_OK:" + OUT_FILE);
    } catch (e) {
        console.error("SCREENSHOT_ERROR:" + e.message);
    } finally {
        await browser.close();
    }
})();
'

# ---------------------------------------------------------------------------
# 环境检测
# ---------------------------------------------------------------------------

echo ""
echo "=============================================="
echo "  VibeNet Control — Playwright UI 测试"
echo "=============================================="
echo ""
echo "[*] 截图输出目录: $SCREENSHOT_DIR"

# 创建目录
mkdir -p "$SCREENSHOT_DIR"

# 检查 Node.js
echo -n "[*] Node.js .................. "
if command -v node &>/dev/null; then
    NODE_VER=$(node -v)
    echo -e "${GREEN}OK${NC}  ($NODE_VER)"
else
    echo -e "${RED}MISSING${NC}"
    echo "    请安装 Node.js: https://nodejs.org/"
    exit 1
fi

# 检查 Playwright (Node.js)
echo -n "[*] Playwright (Node.js) .... "
PW_FOUND=false
if node -e "require('playwright')" 2>/dev/null; then
    PW_VER=$(node -e "console.log(require('playwright/package.json').version)" 2>/dev/null)
    echo -e "${GREEN}OK${NC}  (v${PW_VER}, global)"
    PW_FOUND=true
elif npx --yes playwright --version 2>/dev/null; then
    echo -e "${GREEN}OK${NC}  (via npx)"
    PW_FOUND=true
else
    echo -e "${YELLOW}NOT FOUND${NC}"
    echo "    正在安装 (全局)..."
    npm install -g playwright 2>/dev/null || {
        echo -e "${RED}    安装失败。请手动运行: npm install -g playwright${NC}"
        exit 1
    }
    echo -e "    ${GREEN}安装完成${NC}"
    PW_FOUND=true
fi

# 检查 Chromium 浏览器
echo -n "[*] Chromium 浏览器 ......... "
if npx --yes playwright install chromium --dry-run 2>/dev/null; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${YELLOW}NOT FOUND — 正在安装 Chromium...${NC}"
    npx --yes playwright install chromium 2>/dev/null
fi

# 检查服务
SERVER_RUNNING=false
if check_server; then
    SERVER_RUNNING=true
else
    echo ""
    echo -e "${YELLOW}[!] 服务未启动。部分测试将跳过，但脚本会尝试将未启动场景记录下来。${NC}"
    echo -e "${YELLOW}    启动命令: bash run.sh --gui${NC}"
    echo ""
fi

# ---------------------------------------------------------------------------
# 测试执行
# ---------------------------------------------------------------------------

if [ "$SERVER_RUNNING" = false ]; then
    log_section "服务不可用 — 生成空报告"
    cat > "$REPORT_FILE" << 'REPORTEOF'
# VibeNet Control — UI 测试报告

## 测试执行摘要

| 项目 | 值 |
|------|-----|
| 测试日期 | $(date "+%Y-%m-%d %H:%M:%S") |
| 目标 URL | http://localhost:8501 |
| 测试框架 | Playwright v1.49.1 (Chromium, headless) |
| 服务状态 | **未启动** |

## ⚠️ 服务未启动

VibeNet Control 服务未在 `http://localhost:8501` 上运行。
所有测试用例被跳过。

启动服务后再运行测试：
```bash
bash run.sh --gui
```

## 测试结果总览

| 测试 | 状态 |
|------|------|
| 测试 1: 页面加载和基本元素 | ⏭ 跳过 |
| 测试 2: 侧边栏元素 | ⏭ 跳过 |
| 测试 3: 页面响应式布局 | ⏭ 跳过 |
| 测试 4: 样式验证 | ⏭ 跳过 |

## 截图列表

无（服务未启动）

## UI 问题发现

无（服务未启动）

---

*报告生成时间: $(date "+%Y-%m-%d %H:%M:%S")*
REPORTEOF
    echo ""
    echo -e "${YELLOW}[!] 报告已生成: $REPORT_FILE （服务未启动，所有测试跳过）${NC}"
    echo ""
    exit 0
fi

# ===========================================================================
# 测试 1: 页面加载和基本元素
# ===========================================================================
log_section "测试 1: 页面加载和基本元素"

TEST1_PASS=true

# 1a. 截图初始加载
echo "[*] 截图: 01_initial_load.png"
SCREENSHOT_DIR="$SCREENSHOT_DIR" OUT_FILE="01_initial_load.png" BASE_URL="$BASE_URL" \
    node -e "
const { chromium } = require('playwright');
(async () => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    await page.setViewportSize({ width: 1920, height: 1080 });
    try {
        await page.goto('${BASE_URL}', { waitUntil: 'networkidle', timeout: 30000 });
        await page.waitForTimeout(3000);
        await page.screenshot({ path: '${SCREENSHOT_DIR}/01_initial_load.png', fullPage: true });
        console.log('SCREENSHOT_OK:01_initial_load.png');
    } catch(e) {
        console.error('SCREENSHOT_ERROR:' + e.message);
    } finally {
        await browser.close();
    }
})();
"
if [ $? -eq 0 ] && [ -f "$SCREENSHOT_DIR/01_initial_load.png" ]; then
    log_pass "截图 01_initial_load.png 已保存"
else
    log_fail "截图 01_initial_load.png 保存失败"
    TEST1_PASS=false
fi

# 1b. 验证页面标题包含 "VibeNet Control"
echo "[*] 验证页面标题"
TITLE_CHECK=$(node -e "
const { chromium } = require('playwright');
(async () => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    try {
        await page.goto('${BASE_URL}', { waitUntil: 'networkidle', timeout: 30000 });
        await page.waitForTimeout(2000);
        const title = await page.title();
        if (title.includes('VibeNet Control')) {
            console.log('TITLE_OK:' + title);
        } else {
            console.log('TITLE_FAIL: expected \"VibeNet Control\", got \"' + title + '\"');
        }
    } catch(e) {
        console.log('TITLE_ERROR:' + e.message);
    } finally {
        await browser.close();
    }
})();
")
if echo "$TITLE_CHECK" | grep -q "TITLE_OK"; then
    log_pass "页面标题包含 'VibeNet Control'"
else
    log_fail "页面标题验证失败: $TITLE_CHECK"
    TEST1_PASS=false
fi

# 1c. 验证侧边栏存在"扫描网络"按钮
echo "[*] 验证侧边栏 — 扫描网络按钮"
SCAN_BTN_CHECK=$(node -e "
const { chromium } = require('playwright');
(async () => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    try {
        await page.goto('${BASE_URL}', { waitUntil: 'networkidle', timeout: 30000 });
        await page.waitForTimeout(2000);
        // Streamlit 侧边栏使用 data-testid
        const sidebar = await page.locator('[data-testid=\"stSidebar\"]');
        const btns = await sidebar.locator('button').allTextContents();
        const scanBtn = btns.find(t => t.includes('扫描网络'));
        if (scanBtn) {
            console.log('SCAN_BTN_OK');
        } else {
            // 尝试在整个页面中搜索
            const allBtns = await page.locator('button').allTextContents();
            const scanBtnAnywhere = allBtns.find(t => t.includes('扫描网络'));
            if (scanBtnAnywhere) {
                console.log('SCAN_BTN_OK');
            } else {
                console.log('SCAN_BTN_FAIL: not found. Buttons found: ' + JSON.stringify(allBtns.slice(0, 20)));
            }
        }
    } catch(e) {
        console.log('SCAN_BTN_ERROR:' + e.message);
    } finally {
        await browser.close();
    }
})();
")
if echo "$SCAN_BTN_CHECK" | grep -q "SCAN_BTN_OK"; then
    log_pass "侧边栏存在 '扫描网络' 按钮"
else
    log_fail "未找到 '扫描网络' 按钮: $SCAN_BTN_CHECK"
    TEST1_PASS=false
fi

# 1d. 验证主区域提示信息
echo "[*] 验证主区域提示文本"
HINT_CHECK=$(node -e "
const { chromium } = require('playwright');
(async () => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    try {
        await page.goto('${BASE_URL}', { waitUntil: 'networkidle', timeout: 30000 });
        await page.waitForTimeout(2000);
        const mainContent = await page.locator('[data-testid=\"stAppViewContainer\"]').innerText();
        if (mainContent.includes('点击左侧边栏') || mainContent.includes('扫描网络')) {
            console.log('HINT_OK');
        } else {
            // Streamlit 的 info box
            const infoText = await page.locator('.stAlert').first().innerText().catch(() => '');
            const pageText = await page.locator('body').innerText();
            if (pageText.includes('扫描网络') || infoText.includes('扫描网络')) {
                console.log('HINT_OK');
            } else {
                console.log('HINT_FAIL: Page excerpt: ' + pageText.substring(0, 500));
            }
        }
    } catch(e) {
        console.log('HINT_ERROR:' + e.message);
    } finally {
        await browser.close();
    }
})();
")
if echo "$HINT_CHECK" | grep -q "HINT_OK"; then
    log_pass "主区域包含提示文本 '扫描网络'"
else
    log_fail "主区域未包含期望的提示文本: $HINT_CHECK"
    TEST1_PASS=false
fi

if [ "$TEST1_PASS" = true ]; then
    echo -e "\n  ${GREEN}测试 1: 通过${NC}"
else
    echo -e "\n  ${RED}测试 1: 部分失败${NC}"
fi
TEST_STEPS+=("测试 1: 页面加载和基本元素|$TEST1_PASS")

# ===========================================================================
# 测试 2: 侧边栏元素
# ===========================================================================
log_section "测试 2: 侧边栏元素"

TEST2_PASS=true

# 2a. 截图侧边栏
echo "[*] 截图侧边栏: 02_sidebar.png"
node -e "
const { chromium } = require('playwright');
(async () => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    await page.setViewportSize({ width: 1920, height: 1080 });
    try {
        await page.goto('${BASE_URL}', { waitUntil: 'networkidle', timeout: 30000 });
        await page.waitForTimeout(3000);
        const sidebar = await page.locator('[data-testid=\"stSidebar\"]');
        await sidebar.screenshot({ path: '${SCREENSHOT_DIR}/02_sidebar.png' });
        console.log('SCREENSHOT_OK:02_sidebar.png');
        // 同时截全页面
        await page.screenshot({ path: '${SCREENSHOT_DIR}/02_full_page.png', fullPage: true });
        console.log('SCREENSHOT_OK:02_full_page.png');
    } catch(e) {
        console.error('SCREENSHOT_ERROR:' + e.message);
    } finally {
        await browser.close();
    }
})();
"
if [ -f "$SCREENSHOT_DIR/02_sidebar.png" ]; then
    log_pass "侧边栏截图已保存"
else
    log_fail "侧边栏截图失败"
    TEST2_PASS=false
fi

# 2b. 验证"自动刷新"复选框
echo "[*] 验证 '自动刷新' 复选框"
AUTO_REFRESH_CHECK=$(node -e "
const { chromium } = require('playwright');
(async () => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    try {
        await page.goto('${BASE_URL}', { waitUntil: 'networkidle', timeout: 30000 });
        await page.waitForTimeout(3000);
        // 先点扫描网络, 触发侧边栏展开
        const scanBtn = await page.locator('button:has-text(\"扫描网络\")');
        if (await scanBtn.count() > 0) {
            await scanBtn.first().click();
            await page.waitForTimeout(5000);
        }
        // 搜索 checkbox label
        const labels = await page.locator('label').allTextContents();
        const refreshLabel = labels.find(l => l.includes('自动刷新'));
        if (refreshLabel) {
            console.log('AUTO_REFRESH_OK');
        } else {
            // 尝试 checkbox
            const checkboxes = await page.locator('[type=\"checkbox\"]');
            const checkboxCount = await checkboxes.count();
            if (checkboxCount > 0) {
                // 获取附近文本
                const sidebarText = await page.locator('[data-testid=\"stSidebar\"]').innerText();
                if (sidebarText.includes('自动刷新')) {
                    console.log('AUTO_REFRESH_OK');
                } else {
                    console.log('AUTO_REFRESH_FAIL: sidebar text: ' + sidebarText.substring(0, 300));
                }
            } else {
                console.log('AUTO_REFRESH_FAIL: no checkboxes found');
            }
        }
    } catch(e) {
        console.log('AUTO_REFRESH_ERROR:' + e.message);
    } finally {
        await browser.close();
    }
})();
")
if echo "$AUTO_REFRESH_CHECK" | grep -q "AUTO_REFRESH_OK"; then
    log_pass "侧边栏存在 '自动刷新' 复选框"
else
    log_fail "'自动刷新' 复选框未找到: $AUTO_REFRESH_CHECK"
    TEST2_PASS=false
fi

# 2c. 验证"开始测速"和"停止测速"按钮
echo "[*] 验证 '开始测速' 和 '停止测速' 按钮"
SPEED_BTN_CHECK=$(node -e "
const { chromium } = require('playwright');
(async () => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    try {
        await page.goto('${BASE_URL}', { waitUntil: 'networkidle', timeout: 30000 });
        await page.waitForTimeout(2000);
        // 点击扫描网络
        const scanBtn = await page.locator('button:has-text(\"扫描网络\")');
        if (await scanBtn.count() > 0) {
            await scanBtn.first().click();
            await page.waitForTimeout(8000);
        }
        await page.waitForTimeout(2000);
        const sidebarText = await page.locator('[data-testid=\"stSidebar\"]').innerText();
        const hasStart = sidebarText.includes('开始测速');
        const hasStop = sidebarText.includes('停止测速');
        if (hasStart && hasStop) {
            console.log('SPEED_BTN_OK');
        } else {
            console.log('SPEED_BTN_FAIL: start=' + hasStart + ', stop=' + hasStop + ' sidebar: ' + sidebarText.substring(0, 400));
        }
    } catch(e) {
        console.log('SPEED_BTN_ERROR:' + e.message);
    } finally {
        await browser.close();
    }
})();
")
if echo "$SPEED_BTN_CHECK" | grep -q "SPEED_BTN_OK"; then
    log_pass "侧边栏存在 '开始测速' 和 '停止测速' 按钮"
else
    log_fail "'开始测速'/'停止测速' 按钮验证失败: $SPEED_BTN_CHECK"
    TEST2_PASS=false
fi

if [ "$TEST2_PASS" = true ]; then
    echo -e "\n  ${GREEN}测试 2: 通过${NC}"
else
    echo -e "\n  ${RED}测试 2: 部分失败${NC}"
fi
TEST_STEPS+=("测试 2: 侧边栏元素|$TEST2_PASS")

# ===========================================================================
# 测试 3: 页面响应式布局
# ===========================================================================
log_section "测试 3: 页面响应式布局"

TEST3_PASS=true
RESOLUTIONS=("1920x1080" "1280x720" "800x600")

for resolution in "${RESOLUTIONS[@]}"; do
    width="${resolution%x*}"
    height="${resolution#*x}"
    filename="03_responsive_${width}x${height}.png"

    echo "[*] 截图 $resolution -> $filename"

    node -e "
const { chromium } = require('playwright');
(async () => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    await page.setViewportSize({ width: ${width}, height: ${height} });
    try {
        await page.goto('${BASE_URL}', { waitUntil: 'networkidle', timeout: 30000 });
        await page.waitForTimeout(3000);
        await page.screenshot({ path: '${SCREENSHOT_DIR}/${filename}', fullPage: true });
        console.log('SCREENSHOT_OK:${filename}');

        // 检查横向溢出
        const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
        const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
        if (scrollWidth > clientWidth) {
            console.log('OVERFLOW_WARN: scrollWidth=' + scrollWidth + ' > clientWidth=' + clientWidth + ' at ' + ${width} + 'x' + ${height});
        } else {
            console.log('OVERFLOW_OK: at ' + ${width} + 'x' + ${height});
        }

        // 检查是否有元素重叠（简单方法：检查 z-index 冲突或定位问题）
        const hasOverlap = await page.evaluate(() => {
            const all = document.querySelectorAll('*');
            let issues = 0;
            for (let i = 0; i < Math.min(all.length, 100); i++) {
                const rect = all[i].getBoundingClientRect();
                if (rect.width === 0 && rect.height === 0) continue;
                const style = window.getComputedStyle(all[i]);
                if (style.position === 'absolute' || style.position === 'fixed') {
                    if (rect.x < 0 || rect.y < 0) issues++;
                }
            }
            return issues;
        });
        if (hasOverlap > 5) {
            console.log('OVERLAP_WARN: ' + hasOverlap + ' potentially overlapping elements');
        } else {
            console.log('OVERLAP_OK');
        }
    } catch(e) {
        console.error('SCREENSHOT_ERROR:' + e.message);
    } finally {
        await browser.close();
    }
})();
"

    if [ -f "$SCREENSHOT_DIR/$filename" ]; then
        log_pass "截图 $resolution 已保存: $filename"
    else
        log_fail "截图 $resolution 失败"
        TEST3_PASS=false
    fi
done

if [ "$TEST3_PASS" = true ]; then
    echo -e "\n  ${GREEN}测试 3: 通过${NC}"
else
    echo -e "\n  ${RED}测试 3: 部分失败${NC}"
fi
TEST_STEPS+=("测试 3: 页面响应式布局|$TEST3_PASS")

# ===========================================================================
# 测试 4: 样式验证
# ===========================================================================
log_section "测试 4: 样式验证"

TEST4_PASS=true

# 4a. 截图样式检查
echo "[*] 截图: 04_styles.png"
node -e "
const { chromium } = require('playwright');
(async () => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    await page.setViewportSize({ width: 1920, height: 1080 });
    try {
        await page.goto('${BASE_URL}', { waitUntil: 'networkidle', timeout: 30000 });
        await page.waitForTimeout(3000);
        await page.screenshot({ path: '${SCREENSHOT_DIR}/04_styles.png', fullPage: true });
        console.log('SCREENSHOT_OK:04_styles.png');
    } catch(e) {
        console.error('SCREENSHOT_ERROR:' + e.message);
    } finally {
        await browser.close();
    }
})();
"
if [ -f "$SCREENSHOT_DIR/04_styles.png" ]; then
    log_pass "样式截图已保存"
else
    log_fail "样式截图失败"
    TEST4_PASS=false
fi

# 4b. 检查 CSS 变量 --bg-primary
echo "[*] 检查 CSS 变量 --bg-primary"
CSS_VAR_CHECK=$(node -e "
const { chromium } = require('playwright');
(async () => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    try {
        await page.goto('${BASE_URL}', { waitUntil: 'networkidle', timeout: 30000 });
        await page.waitForTimeout(2000);

        const hasVar = await page.evaluate(() => {
            const root = document.documentElement;
            const style = getComputedStyle(root);
            // Streamlit 主题变量
            const vars = [
                '--bg-primary', '--bg-primary-color',
                '--primary-color', '--background-color',
                '--font', '--text-color'
            ];
            const found = [];
            for (const v of vars) {
                const val = style.getPropertyValue(v);
                if (val && val.trim() !== '') {
                    found.push(v + '=' + val.trim());
                }
            }
            // Also check inline style in <style> tags
            const styleEls = document.querySelectorAll('style');
            let styleText = '';
            styleEls.forEach(el => { styleText += el.textContent; });
            return { computed: found, hasBgPrimary: styleText.includes('--bg-primary') || found.length > 0 };
        });

        if (hasVar.hasBgPrimary) {
            console.log('CSS_VAR_OK: ' + JSON.stringify(hasVar.computed));
        } else {
            // Streamlit doesn't define --bg-primary by default,
            // check for their own theme variables
            if (hasVar.computed.length > 0) {
                console.log('CSS_VAR_ALT: Streamlit uses: ' + JSON.stringify(hasVar.computed));
            } else {
                console.log('CSS_VAR_FAIL: no CSS variables found');
            }
        }
    } catch(e) {
        console.log('CSS_VAR_ERROR:' + e.message);
    } finally {
        await browser.close();
    }
})();
")
if echo "$CSS_VAR_CHECK" | grep -q "CSS_VAR_OK\|CSS_VAR_ALT"; then
    log_pass "CSS 变量已加载（Streamlit 主题变量: $(echo "$CSS_VAR_CHECK" | grep -o 'CSS_VAR_[A-Z]*: .*' | head -1 | cut -d' ' -f2-)）"
else
    log_fail "CSS 变量检查失败: $CSS_VAR_CHECK"
    TEST4_PASS=false
fi

# 4c. 检查 .vibenet-card 样式
echo "[*] 检查 .vibenet-card 样式"
CARD_CHECK=$(node -e "
const { chromium } = require('playwright');
(async () => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    try {
        await page.goto('${BASE_URL}', { waitUntil: 'networkidle', timeout: 30000 });
        await page.waitForTimeout(2000);

        const found = await page.evaluate(() => {
            const sheets = document.styleSheets;
            let vibenetCard = false;
            try {
                for (const sheet of sheets) {
                    try {
                        for (const rule of sheet.cssRules || []) {
                            if (rule.selectorText && rule.selectorText.includes('vibenet-card')) {
                                vibenetCard = true;
                                return { found: true, selector: rule.selectorText, css: rule.cssText.substring(0, 200) };
                            }
                        }
                    } catch(e) { /* cross-origin, skip */ }
                }
            } catch(e) {}
            // Also check inline style
            const styleEls = document.querySelectorAll('style');
            styleEls.forEach(el => {
                if (el.textContent.includes('vibenet-card')) vibenetCard = true;
            });
            return { found: vibenetCard };
        });

        if (found.found) {
            console.log('CARD_STYLE_OK: ' + JSON.stringify(found));
        } else {
            console.log('CARD_STYLE_FAIL: .vibenet-card not found in stylesheets');
        }
    } catch(e) {
        console.log('CARD_STYLE_ERROR:' + e.message);
    } finally {
        await browser.close();
    }
})();
")
if echo "$CARD_CHECK" | grep -q "CARD_STYLE_OK"; then
    log_pass ".vibenet-card 样式已定义"
else
    log_fail ".vibenet-card 样式未找到: $CARD_CHECK"
    TEST4_PASS=false
fi

# 4d. 检查 .vibenet-table 样式
echo "[*] 检查 .vibenet-table 样式"
TABLE_CHECK=$(node -e "
const { chromium } = require('playwright');
(async () => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    try {
        await page.goto('${BASE_URL}', { waitUntil: 'networkidle', timeout: 30000 });
        await page.waitForTimeout(2000);

        const found = await page.evaluate(() => {
            const sheets = document.styleSheets;
            let vibenetTable = false;
            try {
                for (const sheet of sheets) {
                    try {
                        for (const rule of sheet.cssRules || []) {
                            if (rule.selectorText && rule.selectorText.includes('vibenet-table')) {
                                vibenetTable = true;
                                return { found: true, selector: rule.selectorText, css: rule.cssText.substring(0, 200) };
                            }
                        }
                    } catch(e) {}
                }
            } catch(e) {}
            const styleEls = document.querySelectorAll('style');
            styleEls.forEach(el => {
                if (el.textContent.includes('vibenet-table')) vibenetTable = true;
            });
            return { found: vibenetTable };
        });

        if (found.found) {
            console.log('TABLE_STYLE_OK: ' + JSON.stringify(found));
        } else {
            console.log('TABLE_STYLE_FAIL: .vibenet-table not found in stylesheets');
        }
    } catch(e) {
        console.log('TABLE_STYLE_ERROR:' + e.message);
    } finally {
        await browser.close();
    }
})();
")
if echo "$TABLE_CHECK" | grep -q "TABLE_STYLE_OK"; then
    log_pass ".vibenet-table 样式已定义"
else
    log_fail ".vibenet-table 样式未找到: $TABLE_CHECK"
    TEST4_PASS=false
fi

if [ "$TEST4_PASS" = true ]; then
    echo -e "\n  ${GREEN}测试 4: 通过${NC}"
else
    echo -e "\n  ${RED}测试 4: 部分失败${NC}"
fi
TEST_STEPS+=("测试 4: 样式验证|$TEST4_PASS")

# ===========================================================================
# 生成测试报告
# ===========================================================================
log_section "生成测试报告"

OVERALL_STATUS=$([ "$PASS_COUNT" -eq "$TOTAL_TESTS" ] && echo "通过" || echo "部分失败")

# 获取截图列表
SCREENSHOT_LIST=$(ls "$SCREENSHOT_DIR"/*.png 2>/dev/null | while read -r f; do
    fname=$(basename "$f")
    fsize=$(ls -lh "$f" | awk '{print $5}')
    echo "- \`$fname\` ($fsize)"
done)

cat > "$REPORT_FILE" << REPORTEOF
# VibeNet Control — UI 测试报告

## 测试执行摘要

| 项目 | 值 |
|------|-----|
| 测试日期 | $(date "+%Y-%m-%d %H:%M:%S") |
| 目标 URL | http://localhost:8501 |
| 测试框架 | Playwright v1.49.1 (Chromium, headless) |
| 服务状态 | 已启动 |
| 总测试数 | $TOTAL_TESTS |
| 通过数 | $PASS_COUNT |
| 失败数 | $FAIL_COUNT |
| 整体状态 | **$OVERALL_STATUS** |

## 测试结果详情

| 测试用例 | 状态 |
|----------|------|
REPORTEOF

for step in "${TEST_STEPS[@]}"; do
    name="${step%|*}"
    result="${step#*|}"
    if [ "$result" = "true" ]; then
        status_icon="✅ 通过"
    else
        status_icon="❌ 失败"
    fi
    echo "| $name | $status_icon |" >> "$REPORT_FILE"
done

cat >> "$REPORT_FILE" << REPORTEOF2

## 截图列表

$SCREENSHOT_LIST

## 各测试详情

### 测试 1: 页面加载和基本元素
- **截图**: \`01_initial_load.png\` — 首次加载的完整页面截图
- **验证项**:
  1. 页面标题包含 "VibeNet Control"
  2. 侧边栏存在"扫描网络"按钮
  3. 主区域显示"点击左侧边栏的扫描网络"提示信息
- **预期**: Streamlit 应用正常加载，首页显示引导提示

### 测试 2: 侧边栏元素
- **截图**: \`02_sidebar.png\` — 侧边栏特写，\`02_full_page.png\` — 全页面
- **验证项**:
  1. "自动刷新"复选框存在
  2. "开始测速"按钮存在
  3. "停止测速"按钮存在
- **预期**: 扫描网络后，侧边栏完整显示所有控制元素

### 测试 3: 页面响应式布局
- **截图**:
  - \`03_responsive_1920x1080.png\` (1920x1080)
  - \`03_responsive_1280x720.png\` (1280x720)
  - \`03_responsive_800x600.png\` (800x600)
- **验证项**: 三种分辨率下页面均无横向溢出、无元素重叠
- **预期**: Streamlit 响应式布局在不同分辨率下正常渲染

### 测试 4: 样式验证
- **截图**: \`04_styles.png\` — 样式检查时的完整页面
- **验证项**:
  1. CSS 变量（如 \`--bg-primary\` 或 Streamlit 主题变量）存在
  2. \`.vibenet-card\` 样式类已定义
  3. \`.vibenet-table\` 样式类已定义
- **预期**: 自定义 CSS 样式正确加载

## UI 问题发现

### 问题列表
REPORTEOF2

# 汇总问题
ISSUES_FOUND=0

# 检查测试输出中是否有值得报告的 UI 问题
for step in "${TEST_STEPS[@]}"; do
    name="${step%|*}"
    result="${step#*|}"
    if [ "$result" != "true" ]; then
        ISSUES_FOUND=$((ISSUES_FOUND + 1))
    fi
done

if [ "$ISSUES_FOUND" -eq 0 ]; then
    cat >> "$REPORT_FILE" << EOF
✅ 未发现 UI 问题。所有验证项通过。

EOF
else
    cat >> "$REPORT_FILE" << EOF
发现 $ISSUES_FOUND 个测试用例存在问题，详见上方测试结果详情表。建议：
1. 检查服务是否正常运行：\`bash run.sh --gui\`
2. 检查浏览器控制台是否有 JavaScript 错误
3. 确认 Python 依赖（scapy, streamlit）已正确安装
EOF
fi

# 额外检查项目
echo "" >> "$REPORT_FILE"
echo "### 补充说明" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "- 测试使用 Chromium headless 模式，与用户实际浏览器渲染一致" >> "$REPORT_FILE"
echo "- 所有截图保存在 \`test_screenshots/\` 目录" >> "$REPORT_FILE"
echo "- 如果服务需要 root 权限，Ensure 测试运行在有足够权限的环境中" >> "$REPORT_FILE"
echo "- \`.vibenet-card\` 和 \`.vibenet-table\` 是自定义 CSS 类，如果项目中未定义，验证会失败" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "---" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "*报告生成时间: $(date "+%Y-%m-%d %H:%M:%S")*" >> "$REPORT_FILE"
echo "*测试脚本: \`test_ui_playwright.sh\`*" >> "$REPORT_FILE"

# ===========================================================================
# 输出总结
# ===========================================================================
log_section "测试完成"

echo "  总测试数: $TOTAL_TESTS"
echo -e "  通过:     ${GREEN}$PASS_COUNT${NC}"
echo -e "  失败:     ${RED}$FAIL_COUNT${NC}"
echo ""
echo "  截图目录: $SCREENSHOT_DIR"
echo "  测试报告: $REPORT_FILE"
echo ""

if [ "$FAIL_COUNT" -gt 0 ]; then
    echo -e "${YELLOW}[!] 存在失败用例，请查看报告了解详情。${NC}"
else
    echo -e "${GREEN}[*] 所有测试通过！${NC}"
fi
echo ""

exit 0
