import { chromium } from 'playwright'

const BASE = 'http://localhost:5174'
const errors = []
const shotDir = 'C:/Users/Admin/AppData/Local/Temp/claude/c--Users-Admin-Desktop-ARKcrm/a4353bde-e846-4e13-9957-3b2a35e2f1e9/scratchpad'

const browser = await chromium.launch()
const page = await browser.newPage()
page.on('console', (msg) => {
  if (msg.type() === 'error') errors.push(msg.text())
})
page.on('pageerror', (err) => errors.push('PAGEERROR: ' + err.message))

async function shot(name) {
  await page.screenshot({ path: `${shotDir}/${name}.png`, fullPage: true })
}

console.log('--- nav leads list ---')
await page.goto(BASE + '/leads', { waitUntil: 'networkidle' })
await page.waitForTimeout(500)
await shot('01-leads-list')
console.log('title:', await page.title())

console.log('--- open Khazna lead LEAD-00118 ---')
await page.goto(BASE + '/leads/LEAD-00118', { waitUntil: 'networkidle' })
await page.waitForTimeout(500)
await shot('02-lead-detail')

console.log('--- nav deals list (should be empty) ---')
await page.goto(BASE + '/deals', { waitUntil: 'networkidle' })
await page.waitForTimeout(500)
await shot('03-deals-list-empty')

console.log('--- nav deal detail nonexistent id ---')
await page.goto(BASE + '/deals/DEAL-99999', { waitUntil: 'networkidle' })
await page.waitForTimeout(8000)
await shot('04-deal-detail-missing')

console.log('--- nav lead detail nonexistent id (compare against existing behavior) ---')
await page.goto(BASE + '/leads/LEAD-99999', { waitUntil: 'networkidle' })
await page.waitForTimeout(8000)
await shot('05-lead-detail-missing')

console.log('--- errors collected ---')
console.log(JSON.stringify(errors, null, 2))

await browser.close()
