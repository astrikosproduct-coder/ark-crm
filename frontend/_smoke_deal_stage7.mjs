// Verifies: Stage 7 — Close is reachable on the Deals rail with its own
// fields, and payment_milestones relocated from Stage 7/Deals to Stage
// 6/Opportunities renders correctly in its new home and is gone from the old
// one.
//
//   npx vite --port 5199 --strictPort
//   ARK_SHOTS=/tmp node _smoke_deal_stage7.mjs

import { chromium } from 'playwright'

const BASE = process.env.ARK_BASE ?? 'http://localhost:5199'
const SHOTS = process.env.ARK_SHOTS ?? '.'
const errors = []
const results = []
function check(name, ok, detail = '') {
  results.push({ name, ok, detail })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  — ' + detail : ''}`)
}

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1500, height: 1300 } })
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
page.on('pageerror', (e) => errors.push('PAGEERROR: ' + e.message))
page.on('dialog', async (d) => { await d.accept() })

let n = 0
const shot = async (name) => { n++; await page.screenshot({ path: `${SHOTS}/d${String(n).padStart(2,'0')}-${name}.png`, fullPage: true }) }

await page.goto(`${BASE}/settings`)
await page.waitForTimeout(1200)
await page.getByRole('button', { name: /Reset|reseed|Restore/i }).first().click()
await page.waitForTimeout(1200)

// -------------------------------------------------------------- OPPORTUNITY
// LEAD-00122 (Stage 6) -> OPP-00002. Payment Milestones should now be here.
// The seed leaves every Stage 4-6 field blank on both derived Opportunities
// (same sparse-seed limitation noted when the module was registered), and
// VIEW mode hides an all-empty section entirely — so this checks EDIT mode,
// which shows every field including untouched ones.
await page.goto(`${BASE}/opportunities/OPP-00002`)
await page.waitForTimeout(1500)
let body = await page.locator('body').innerText()
check('opportunity at Stage 6', body.includes('Stage 6 · Commercial Evaluation'))
await page.getByRole('button', { name: 'Edit' }).first().click()
await page.waitForTimeout(700)
body = await page.locator('body').innerText()
check('Stage 6 edit form shows Payment Milestones', /Payment Milestones/i.test(body))
check('Stage 6 edit form shows the Add milestone button', /Add milestone/i.test(body))
await shot('opportunity-stage6-payment-milestones')
await page.getByRole('button', { name: /^Cancel$/ }).first().click().catch(() => {})
await page.waitForTimeout(400)

// ------------------------------------------------------------------- DEALS
await page.goto(`${BASE}/deals`)
await page.waitForTimeout(1200)
body = await page.locator('body').innerText()
console.log('  (deals list, no rows expected yet — nothing converts to a Deal in this app run)')
await shot('deals-list')

// Convert a Lead to a Deal via the legacy Stage-7 flow so there is a Deal to
// inspect, exactly like the existing regression net does.
await page.goto(`${BASE}/leads/LEAD-00118`)
await page.waitForTimeout(1200)
await page.getByRole('button', { name: /Advance to Stage/ }).click()
await page.waitForTimeout(500)
let dialog = page.getByRole('dialog')
await dialog.locator('button[role="combobox"]').click()
await page.waitForTimeout(200)
await page.getByRole('option', { name: /^Stage 7 ·/ }).click()
await page.waitForTimeout(300)
await dialog.locator('textarea').fill('Fast-tracked to close.')
await dialog.getByRole('button', { name: /Advance to Stage 7/ }).click()
await page.waitForTimeout(1500)

await page.getByRole('button', { name: 'Convert to Deal' }).click()
await page.waitForTimeout(600)
await page.getByRole('dialog').getByRole('button', { name: /Confirm conversion/ }).click()
await page.waitForTimeout(1800)
await page.getByRole('dialog').getByRole('button', { name: 'Go to Deal' }).click()
await page.waitForTimeout(1500)

const dealUrl = page.url()
check('landed on a Deal page', /\/deals\/DEAL-\d+/.test(dealUrl), dealUrl)
body = await page.locator('body').innerText()
check('deal opens at Stage 8 (legacy conversion, unchanged)', body.includes('Stage 8 · Project Success'))
await shot('deal-stage8-fresh')

// -------------------------------------------------------- STAGE 7 ON THE RAIL
const railNodes = await page.locator('.rounded-full.border-2').count()
check('deal rail now draws 3 stages (7, 8, 9)', railNodes === 3, `found ${railNodes}`)

// Move the Deal BACK to Stage 7 — a reversal — to inspect the Close section.
// At Stage 8 the button reads "Advance to Stage 9" (only >= LAST_STAGE says
// "Change stage"), so match either.
await page.getByRole('button', { name: /Advance to Stage|Change stage/ }).click()
await page.waitForTimeout(500)
dialog = page.getByRole('dialog')
await dialog.locator('button[role="combobox"]').click()
await page.waitForTimeout(200)
await page.getByRole('option', { name: /^Stage 7 ·/ }).click()
await page.waitForTimeout(300)
body = await dialog.innerText()
check('reversal to Stage 7 requires a reason', /Moves backward from Stage 8/.test(body))
await dialog.locator('textarea').fill('Reopening for a contract amendment.')
await dialog.getByRole('button', { name: /Advance to Stage 7/ }).click()
await page.waitForTimeout(1500)

body = await page.locator('body').innerText()
check('deal now shows Stage 7 · Close', body.includes('Stage 7 · Close'), (body.match(/Stage \d[^\n]*/) || [''])[0])
check('ON CONVERSION section still present (register-native Stage 7 section)', /ON CONVERSION/i.test(body))
await shot('deal-stage7-view')

// PO Number / Contract Signed Date / Payment Schedule Confirmed are blank on
// this Deal — ConvertToDealDialog never sets them — and view mode hides an
// all-empty section entirely, same limitation noted for Payment Milestones
// above. Edit mode shows every field, populated or not, which is what proves
// the STAGE 7 — CLOSE section itself is actually reachable now.
await page.getByRole('button', { name: 'Edit' }).first().click()
await page.waitForTimeout(800)
body = await page.locator('body').innerText()
check('Stage 7 edit form shows STAGE 7 — CLOSE section', /STAGE 7 . CLOSE/i.test(body), body.slice(0, 50))
check('Stage 7 edit form shows PO Number', /PO Number/i.test(body))
check('Stage 7 edit form shows Contract Signed Date', /Contract Signed Date/i.test(body))
check('Stage 7 edit form shows Payment Schedule Confirmed', /Payment Schedule Confirmed/i.test(body))
check('Stage 7 edit form does NOT show Payment Milestones (relocated to Opportunities)', !/Payment Milestones/i.test(body))
await shot('deal-stage7-edit')

console.log('\nconsole errors:', errors.length)
for (const e of errors.slice(0, 15)) console.log('  ', e)
const failed = results.filter((r) => !r.ok)
console.log(`\n${results.length - failed.length}/${results.length} checks passed`)
if (failed.length) { console.log('FAILED:'); for (const f of failed) console.log('  -', f.name, f.detail) }
await browser.close()
process.exit(failed.length || errors.length ? 1 : 0)
