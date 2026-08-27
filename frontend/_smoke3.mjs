import { chromium } from 'playwright'

const BASE = 'http://localhost:5174'
const shotDir = 'C:/Users/Admin/AppData/Local/Temp/claude/c--Users-Admin-Desktop-ARKcrm/a4353bde-e846-4e13-9957-3b2a35e2f1e9/scratchpad'
const errors = []

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1400, height: 1100 } })
page.on('console', (msg) => { if (msg.type() === 'error') errors.push(msg.text()) })
page.on('pageerror', (err) => errors.push('PAGEERROR: ' + err.message))
page.on('dialog', async (d) => { await d.accept() })

let shotN = 0
async function shot(name) {
  shotN++
  await page.screenshot({ path: `${shotDir}/x${String(shotN).padStart(2, '0')}-${name}.png`, fullPage: true })
}

async function advance(targetStageNum, reason) {
  await page.getByRole('button', { name: /Advance to Stage|Change stage/ }).click()
  await page.waitForTimeout(300)
  const dialog = page.getByRole('dialog')
  if (targetStageNum) {
    await dialog.locator('button[role="combobox"]').click()
    await page.getByRole('option', { name: new RegExp(`^Stage ${targetStageNum} ·`) }).click()
  }
  if (reason) await dialog.locator('textarea').fill(reason)
  await dialog.getByRole('button', { name: /^Advance to Stage \d+$/ }).click()
  await page.waitForTimeout(700)
}

console.log('=== fix pre-existing seed data quirks (currency label, partial date) — unrelated to this feature ===')
await page.goto(BASE + '/leads/LEAD-00118', { waitUntil: 'networkidle' })
await page.evaluate(async () => {
  await fetch('/api/leads/LEAD-00118', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ currency: 'USD', expected_close_month: '2027-04-01' }),
  })
})

console.log('=== reload, advance 3 -> 4 ===')
await page.goto(BASE + '/leads/LEAD-00118', { waitUntil: 'networkidle' })
await advance(4, null)

console.log('=== fill stage 4 financials and save ===')
await page.getByRole('button', { name: 'Edit' }).first().click()
await page.waitForTimeout(300)
await page.getByLabel('ARR (Annual Recurring)').fill('400000')
await page.getByLabel('One-Time Revenue').fill('150000')
await page.getByLabel('3rd-Party One-Time').fill('50000')
await page.getByLabel('3rd-Party Recurring (per year)').fill('20000')
await page.getByLabel('Contract Years').fill('3')
await page.getByRole('button', { name: 'Save' }).click()
await page.waitForTimeout(700)
await shot('stage4-after-save')
const stillEditing = await page.getByRole('button', { name: 'Save' }).count()
console.log('still in edit mode after save attempt?', stillEditing > 0)

console.log('=== skip 4 -> 7 ===')
await advance(7, 'Fast-tracked for the walkthrough — commercial terms agreed directly with e& Enterprise.')
await shot('stage7')

console.log('=== click Convert to Deal ===')
await page.getByRole('button', { name: 'Convert to Deal' }).click()
await page.waitForTimeout(400)
await shot('convert-confirm-step')

console.log('=== confirm conversion ===')
await page.getByRole('dialog').getByRole('button', { name: 'Confirm conversion' }).click()
await page.waitForTimeout(1200)
await shot('convert-result-step')

const resultText = await page.getByRole('dialog').innerText()
console.log('--- result dialog text ---')
console.log(resultText)

console.log('=== close result dialog (Close, stay on lead) ===')
await page.getByRole('dialog').getByRole('button', { name: 'Close' }).click()
await page.waitForTimeout(500)
await shot('lead-after-convert-readonly')

console.log('errors so far:', JSON.stringify(errors, null, 2))
await browser.close()
