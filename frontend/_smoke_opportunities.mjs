// Behaviour net for the Opportunities module — registered in the UI on top of
// the spec layer, effective-record resolver and PipelineRecordPage that were
// already in place. Covers: sidebar order, the Leads/Opportunities boundary
// (nothing above Stage 3 on Leads, the Kanban columned to match), the
// Opportunities list resolving its read-through columns per row, a detail page
// showing End Client / Customer (Partner / SI) read-only from the parent Lead,
// the /opportunities/new route, and — the part most likely to silently break —
// the SAME seed-derivation function running again as useDataStore's migrate()
// on a simulated returning browser.
//
//   npx vite --port 5199 --strictPort
//   ARK_SHOTS=/tmp node _smoke_opportunities.mjs

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
const page = await browser.newPage({ viewport: { width: 1500, height: 1200 } })
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
page.on('pageerror', (e) => errors.push('PAGEERROR: ' + e.message))
// SettingsPage's Reset button goes through window.confirm() — without this,
// Playwright auto-dismisses it and the reset silently never happens.
page.on('dialog', async (d) => { await d.accept() })

let n = 0
const shot = async (name) => { n++; await page.screenshot({ path: `${SHOTS}/o${String(n).padStart(2,'0')}-${name}.png`, fullPage: true }) }

// Fresh browser profile each run.
await page.goto(`${BASE}/settings`)
await page.waitForTimeout(1200)
await page.getByRole('button', { name: /Reset|reseed|Restore/i }).first().click()
await page.waitForTimeout(1200)

// ------------------------------------------------------------------ SIDEBAR
await page.goto(`${BASE}/dashboard`)
await page.waitForTimeout(800)
const navLabels = await page.locator('nav a span').allInnerTexts()
const leadsIdx = navLabels.indexOf('Leads')
const oppIdx = navLabels.indexOf('Opportunities')
const dealsIdx = navLabels.indexOf('Deals')
check('sidebar has Opportunities between Leads and Deals', leadsIdx >= 0 && oppIdx === leadsIdx + 1 && dealsIdx === oppIdx + 1, navLabels.join(','))
await shot('sidebar')

// -------------------------------------------------------------- LEADS LIST
await page.goto(`${BASE}/leads`)
await page.waitForTimeout(1200)
let body = await page.locator('body').innerText()
check('leads list mentions no stage above 3', ![...body.matchAll(/\b([4-9])\s*·/g)].length, body.slice(0, 200))
await shot('leads-list')

// ---------------------------------------------------------------- KANBAN
await page.getByRole('tab', { name: 'Pipeline' }).click()
await page.waitForTimeout(1000)
body = await page.locator('body').innerText()
const cols = [...body.matchAll(/^(\d) · (Connect|Demo Presentation|POC \/ Pilot|Prescription|RFP \/ RFI|Technical Evaluation|Commercial Evaluation|Close)$/gm)]
check('kanban shows exactly stages 0-3', cols.map((m) => m[1]).join(',') === '0,1,2,3', cols.map((m) => m[1]).join(','))
await shot('leads-kanban')

// ------------------------------------------------------- OPPORTUNITIES LIST
await page.goto(`${BASE}/opportunities`)
await page.waitForTimeout(1500)
body = await page.locator('body').innerText()
check('opportunities page title', body.includes('Opportunities'))
const rowCount = await page.locator('table tbody tr').count()
check('opportunities list shows 2 derived records', rowCount === 2, `found ${rowCount} rows`)
check('opportunities list resolves names, not blank', body.includes('Mazzant') || body.includes('KIM'), body.slice(0, 400).replace(/\n+/g, ' | '))
await shot('opportunities-list')

// -------------------------------------------------------- OPPORTUNITY DETAIL
const firstRow = page.locator('table tbody tr').first()
await firstRow.click()
await page.waitForTimeout(1500)
const url = page.url()
check('navigated to an opportunity detail page', /\/opportunities\/OPP-\d+/.test(url), url)
body = await page.locator('body').innerText()
check('detail shows Stage 4 in the stage line', body.includes('Stage 4 · RFP / RFI'), (body.match(/Stage \d[^\n]*/) || [''])[0])
check('header shows Client resolved through the parent Lead', /Client: \w/.test(body), (body.match(/Client: \S+/) || [''])[0])
const fromLink = await page.getByRole('button', { name: /From LEAD-/ }).count()
check('detail header links back to the parent Lead', fromLink > 0)
await shot('opportunity-detail')

// End Client / Customer (Partner / SI) live in the READ THROUGH THE PARENT
// section, which renders on the Details tab, not Current stage.
await page.getByRole('tab', { name: 'Details' }).click()
await page.waitForTimeout(700)
body = await page.locator('body').innerText()
check('details tab shows End Client (read-through)', /End Client/i.test(body))
// LEAD-00119 (this record's parent) has customer_partner_si: null in the seed,
// and view mode hides empty fields — so its ABSENCE here is correct, not a
// bug. The second Opportunity (from LEAD-00122, which does have a partner) is
// checked below instead.
check('details tab shows the read-through section heading', /READ THROUGH THE PARENT/i.test(body))
const readOnlyBroken = body.includes('Not resolved') && body.includes('no Parent Lead')
check('read-through fields resolved (no "Not resolved" warning)', !readOnlyBroken)
await shot('opportunity-details')

// -------------------------------------------------------------- SECOND ROW
await page.goto(`${BASE}/opportunities`)
await page.waitForTimeout(1200)
const secondRow = page.locator('table tbody tr').nth(1)
await secondRow.click()
await page.waitForTimeout(1500)
body = await page.locator('body').innerText()
check('second opportunity shows Stage 6 in the stage line', body.includes('Stage 6 · Commercial Evaluation'), (body.match(/Stage \d[^\n]*/) || [''])[0])
check('second opportunity header resolves both Client and Partner', /Client: ADNOC/.test(body) && /Partner: /.test(body), (body.match(/Client:[^\n]*/) || [''])[0])
await shot('opportunity-detail-2')

await page.getByRole('tab', { name: 'Details' }).click()
await page.waitForTimeout(700)
body = await page.locator('body').innerText()
check('second opportunity details shows Customer (Partner / SI) resolved', body.includes('Customer (Partner / SI)') && body.includes('Orange Business Services'))
await shot('opportunity-detail-2-details')

// ------------------------------------------------------- CREATE PAGE ROUTE
await page.goto(`${BASE}/opportunities/new`)
await page.waitForTimeout(1000)
body = await page.locator('body').innerText()
check('opportunity create page loads', body.includes('New opportunity'))
check('create page explains it is not the normal path', /normally reached by converting/i.test(body))
await shot('opportunity-create')

// ------------------------------------------------- RETURNING BROWSER MIGRATION
// Simulate a browser that persisted data under version 3 (pre-split): force
// LEAD-00119 back to an "old" Stage 4 / OPEN shape and drop the derived
// collections entirely, then reload so useDataStore's migrate() has to run
// deriveOpportunitiesFromLeads on this PERSISTED state — the same function
// buildSeedData() already ran once, called from the other place it is called.
await page.goto(`${BASE}/dashboard`)
await page.evaluate(() => {
  const raw = localStorage.getItem('arkcrm-data')
  const parsed = JSON.parse(raw)
  const lead119 = parsed.state.data.leads.find((l) => l.id === 'LEAD-00119')
  lead119.project_stage = '4_RFP_RFI'
  lead119.lead_status = 'OPEN'
  delete parsed.state.data.opportunities
  delete parsed.state.data.conversions
  parsed.version = 3
  localStorage.setItem('arkcrm-data', JSON.stringify(parsed))
})
await page.reload()
await page.waitForTimeout(1800)

body = await page.locator('body').innerText()
check('app does not crash migrating a simulated v3 snapshot', errors.length === 0, errors.slice(0, 3).join(' | '))

await page.goto(`${BASE}/leads/LEAD-00119`)
await page.waitForTimeout(1200)
body = await page.locator('body').innerText()
check('migrated LEAD-00119 is frozen at Stage 3', body.includes('3 · Prescription'))
check('migrated LEAD-00119 banner names the Opportunity, not "a Deal"', /converted to an Opportunity/.test(body), (body.match(/converted to[^\n.]*/) || [''])[0])
const oppButton = await page.getByRole('button', { name: /Go to OPP-/ }).count()
check('migrated LEAD-00119 links to its new Opportunity', oppButton > 0)
await shot('migrated-lead')

await page.goto(`${BASE}/opportunities`)
await page.waitForTimeout(1200)
const migratedRows = await page.locator('table tbody tr').count()
check('migration produced an Opportunity for the previously-persisted Stage-4 lead', migratedRows >= 1, `${migratedRows} rows`)
await shot('migrated-opportunities')

console.log('\nconsole errors:', errors.length)
for (const e of errors.slice(0, 15)) console.log('  ', e)
const failed = results.filter((r) => !r.ok)
console.log(`\n${results.length - failed.length}/${results.length} checks passed`)
if (failed.length) { console.log('FAILED:'); for (const f of failed) console.log('  -', f.name, f.detail) }
await browser.close()
process.exit(failed.length || errors.length ? 1 : 0)
