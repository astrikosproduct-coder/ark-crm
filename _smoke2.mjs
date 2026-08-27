import { chromium } from 'playwright'

const BASE = 'http://localhost:5174'
const shotDir = 'C:/Users/Admin/AppData/Local/Temp/claude/c--Users-Admin-Desktop-ARKcrm/a4353bde-e846-4e13-9957-3b2a35e2f1e9/scratchpad'
const errors = []

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } })
page.on('console', (msg) => { if (msg.type() === 'error') errors.push(msg.text()) })
page.on('pageerror', (err) => errors.push('PAGEERROR: ' + err.message))
page.on('dialog', async (d) => { console.log('DIALOG:', d.message()); await d.accept() })

let shotN = 0
async function shot(name) {
  shotN++
  await page.screenshot({ path: `${shotDir}/w${String(shotN).padStart(2, '0')}-${name}.png`, fullPage: true })
}

async function advance(targetStageNum, reason) {
  await page.getByRole('button', { name: /Advance to Stage|Change stage/ }).click()
  await page.waitForTimeout(300)
  const dialog = page.getByRole('dialog')
  if (targetStageNum) {
    await dialog.locator('button[role="combobox"]').click()
    await page.getByRole('option', { name: new RegExp(`^Stage ${targetStageNum} ·`) }).click()
  }
  if (reason) {
    await dialog.locator('textarea').fill(reason)
  }
  await dialog.getByRole('button', { name: /^Advance to Stage \d+$/ }).click()
  await page.waitForTimeout(700)
}

console.log('=== 1. open Khazna lead ===')
await page.goto(BASE + '/leads/LEAD-00118', { waitUntil: 'networkidle' })
await shot('lead-stage3')

console.log('=== 2. advance stage 3 -> 4 ===')
await advance(4, null)
await shot('lead-stage4')

console.log('=== 3. edit stage 4 financials ===')
await page.getByRole('button', { name: 'Edit' }).first().click()
await page.waitForTimeout(300)
await page.getByLabel('ARR (Annual Recurring)').fill('400000')
await page.getByLabel('One-Time Revenue').fill('150000')
await page.getByLabel('3rd-Party One-Time').fill('50000')
await page.getByLabel('3rd-Party Recurring (per year)').fill('20000')
await page.getByLabel('Contract Years').fill('3')
await shot('lead-stage4-filled')
await page.getByRole('button', { name: 'Save' }).click()
await page.waitForTimeout(700)
await shot('lead-stage4-saved')

console.log('=== 4. skip stage 4 -> 7 ===')
await advance(7, 'Fast-tracked for the walkthrough — commercial terms agreed directly with e& Enterprise.')
await shot('lead-stage7')

console.log('errors so far:', JSON.stringify(errors, null, 2))
await browser.close()
