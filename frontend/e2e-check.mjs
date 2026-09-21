/**
 * 端到端 UI 验证：用真实浏览器走完登录 → 建部署 → 测试台推理 → 监控 → 日志。
 * 截图输出到 /tmp/llmd-shots/。
 */
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'

const BASE = 'http://127.0.0.1:8000'
const OUT = '/tmp/llmd-shots'
mkdirSync(OUT, { recursive: true })

const shot = async (page, name) => {
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true })
  console.log(`  [截图] ${name}.png`)
}

const errors = []

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1500, height: 950 } })

page.on('console', (msg) => {
  if (msg.type() === 'error') errors.push(`console: ${msg.text()}`)
})
page.on('pageerror', (err) => errors.push(`pageerror: ${err.message}`))

// ---------------------------------------------------------------- 登录
console.log('== 登录页 ==')
await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' })
await shot(page, '01-login')

await page.fill('input[placeholder="用户名"]', 'admin')
await page.fill('input[placeholder="密码"]', 'admin123')
// 注意：antd 会在两个汉字间插空格（"登 录"），因此用结构选择器而非文本
await page.click('button[type="submit"]')
await page.waitForURL(`${BASE}/`, { timeout: 15000 })
await page.waitForLoadState('networkidle')
console.log('  登录成功，已跳转总览')

// ---------------------------------------------------------------- 总览
await page.waitForSelector('h4:has-text("平台总览")', { timeout: 10000 })
await page.waitForSelector('.ant-menu-item:has-text("模型仓库")', { timeout: 10000 })
await page.waitForTimeout(1500)
await shot(page, '02-dashboard')

const modelCount = await page.locator('text=模型仓库').first().isVisible()
console.log(`  总览渲染正常: ${modelCount}`)

// ---------------------------------------------------------------- 模型仓库
console.log('== 模型仓库 ==')
await page.click('.ant-menu-item:has-text("模型仓库")')
await page.waitForSelector('text=Qwen2.5-7B-Instruct', { timeout: 10000 })
await page.waitForTimeout(800)
await shot(page, '03-models')
const rows = await page.locator('tbody tr.ant-table-row').count()
console.log(`  模型行数: ${rows}`)

// ---------------------------------------------------------------- 新建部署
console.log('== 新建部署 ==')
await page.click('.ant-menu-item:has-text("部署管理")')
await page.waitForTimeout(1200)
await page.click('button:has-text("新建部署")')
await page.waitForSelector('text=创建并启动', { timeout: 8000 })

const deployName = `ui-check-${Date.now().toString().slice(-6)}`
await page.fill('input[placeholder="qwen7b-prod"]', deployName)

// 选择模型
await page.click('.ant-select:has(.ant-select-selection-placeholder:text("从模型仓库中选择"))')
await page.waitForTimeout(500)
await page.click('.ant-select-item-option:has-text("Qwen2.5-7B-Instruct")')
await page.waitForTimeout(400)
await shot(page, '04-deploy-form')

await page.click('button:has-text("创建并启动")')
await page.waitForSelector(`text=${deployName}`, { timeout: 30000 })
await page.waitForTimeout(2000)
await shot(page, '05-deployments')
console.log(`  部署 ${deployName} 已出现在列表`)

// ---------------------------------------------------------------- 测试台
console.log('== 推理测试台 ==')
await page.click('.ant-menu-item:has-text("推理测试台")')
await page.waitForTimeout(2000)
await page.waitForSelector('textarea', { timeout: 10000 })

const chatInput = page.locator('input[placeholder="输入消息，回车发送"]')
await chatInput.fill('介绍一下这个平台')
await chatInput.press('Enter')

// 等待流式回复出现
await page.waitForTimeout(4000)
await shot(page, '06-playground')
const bubbleText = await page.locator('div[style*="border-radius: 10px"]').last().innerText()
console.log(`  回复长度: ${bubbleText.length} 字符`)
console.log(`  回复摘要: ${bubbleText.slice(0, 60).replace(/\n/g, ' ')}`)

// ---------------------------------------------------------------- 监控详情
console.log('== 部署详情与监控 ==')
await page.click('.ant-menu-item:has-text("部署管理")')
await page.waitForTimeout(1500)
await page.click(`a:has-text("${deployName}")`)
await page.waitForSelector('text=实例信息', { timeout: 10000 })
await page.waitForTimeout(9000) // 等几轮指标采样，让曲线有数据
await shot(page, '07-deployment-detail')

const chartCount = await page.locator('svg.recharts-surface').count()
console.log(`  渲染图表数: ${chartCount}`)

const hasTimeline = await page.locator('.ant-timeline-item').count()
console.log(`  生命周期事件数: ${hasTimeline}`)

// ---------------------------------------------------------------- 日志
console.log('== 请求日志 ==')
await page.click('.ant-menu-item:has-text("请求日志")')
await page.waitForTimeout(2000)
await shot(page, '08-logs')
const logRows = await page.locator('tbody tr.ant-table-row').count()
console.log(`  日志行数: ${logRows}`)

// ---------------------------------------------------------------- API Key
console.log('== API Key ==')
await page.click('.ant-menu-item:has-text("API Key")')
await page.waitForTimeout(1500)
await shot(page, '09-keys')
console.log('  API Key 页渲染完成')

// ---------------------------------------------------------------- 结果
await browser.close()

console.log('\n========================================')
if (errors.length) {
  console.log(`发现 ${errors.length} 个浏览器错误：`)
  for (const e of [...new Set(errors)].slice(0, 15)) console.log('  -', e)
  process.exit(1)
} else {
  console.log('无浏览器控制台错误 —— UI 全流程验证通过')
}
