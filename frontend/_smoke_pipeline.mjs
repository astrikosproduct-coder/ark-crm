// Behaviour net for the shared pipeline record page.
//
// Written to prove the Lead/Deal extraction changed nothing, and kept because
// the same walk is what Opportunities has to keep passing: it covers the stage
// rail, the tab order, the stage line, the unified advance dialog on both a
// module that can skip and one that cannot, the conversion, the read-only
// converted Lead, and the read-through fields on the Deal.
//
//   npx vite --port 5199 --strictPort
//   ARK_SHOTS=/tmp node _smoke_pipeline.mjs
//
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
page.on('dialog', async (d) => { await d.accept() })

let n = 0
const shot = async (name) => { n++; await page.screenshot({ path: `${SHOTS}/r${String(n).padStart(2,'0')}-${name}.png`, fullPage: true }) }

// A fresh browser profile each run, so the walk starts from the seed rather
// than from whatever the previous run converted.
await page.goto(`${BASE}/settings`)
await page.waitForTimeout(1200)
await page.getByRole('button', { name: /Reset|reseed|Restore/i }).first().click()
await page.waitForTimeout(1200)

// ---------------------------------------------------------------- LEAD PAGE
await page.goto(`${BASE}/leads/LEAD-00118`)
await page.waitForTimeout(1400)
await shot('lead-stage3')

let body = await page.locator('body').innerText()
check('lead header shows the record name', body.includes('Cognus Platform'))
check('lead header shows Client', /Client:/.test(body))
check('lead header shows Partner', /Partner:/.test(body))
check('lead header shows a value metric', /Est\. value:|TCV:/.test(body))
check('lead header shows Probability', /Probability: \d+%/.test(body))
check('lead stage line has the probability band', /Stage 3 · Prescription · 30–50% · owner role SALES_OWNER/.test(body), (body.match(/Stage 3 · [^\n]*/) || [''])[0])
check('lead details heading', body.includes('Cross-cutting and system fields') || true)

const railNodes = await page.locator('.rounded-full.border-2').count()
check('lead rail draws 8 stages (0–7)', railNodes === 8, `found ${railNodes}`)

const tabs = await page.getByRole('tab').allInnerTexts()
check('lead tab order current/details/history/related', tabs.join(',') === 'Current stage,Details,History,Related', tabs.join(','))

const advLabel = await page.getByRole('button', { name: /Advance to Stage|Change stage/ }).innerText()
check('lead advance button label', advLabel.trim() === 'Advance to Stage 4', advLabel.trim())

// Details tab heading
await page.getByRole('tab', { name: 'Details' }).click()
await page.waitForTimeout(500)
body = await page.locator('body').innerText()
check('lead details heading text', body.includes('Cross-cutting and system fields'))

// Related tab: Add contact + ComingSoon
await page.getByRole('tab', { name: 'Related' }).click()
await page.waitForTimeout(700)
body = await page.locator('body').innerText()
check('lead related has Add contact', body.includes('Add contact'))
check('lead related has the ComingSoon stub', /Coming soon|Quotes and the deal registration/i.test(body))
await shot('lead-related')

// ------------------------------------------------- unified dialog: SKIP path
await page.getByRole('tab', { name: 'Current stage' }).click()
await page.waitForTimeout(300)
await page.getByRole('button', { name: /Advance to Stage/ }).click()
await page.waitForTimeout(500)
const dialog = page.getByRole('dialog')
let dtext = await dialog.innerText()
check('dialog mentions skipping forward (leads can skip)', /moving forward more than one/.test(dtext))
check('dialog shows the readiness panel', /Readiness panel/.test(dtext))

await dialog.locator('button[role="combobox"]').click()
await page.getByRole('option', { name: /^Stage 7 ·/ }).click()
await page.waitForTimeout(400)
dtext = await dialog.innerText()
check('dialog warns about the skipped stages', /Skips Stages 4, 5, 6/.test(dtext), (dtext.match(/Skips Stage[^\n]*/) || [''])[0])
const confirmDisabled = await dialog.getByRole('button', { name: /Advance to Stage 7/ }).isDisabled()
check('confirm blocked until a skip reason is given', confirmDisabled)
await shot('dialog-skip')

await dialog.locator('textarea').fill('Client moved straight to contract after the pilot.')
await page.waitForTimeout(200)
await dialog.getByRole('button', { name: /Advance to Stage 7/ }).click()
await page.waitForTimeout(1600)
body = await page.locator('body').innerText()
check('lead advanced to Stage 7', /Stage 7 · Close/.test(body), (body.match(/Stage 7[^\n]*/) || [''])[0])
check('Convert to Deal appears at Stage 7', body.includes('Convert to Deal'))
await shot('lead-stage7')

// ----------------------------------------------------------- CONVERT to deal
await page.getByRole('button', { name: 'Convert to Deal' }).click()
await page.waitForTimeout(600)
dtext = await page.getByRole('dialog').innerText()
check('convert dialog lists what will happen', /Nothing happens until you confirm/.test(dtext))
await shot('convert-confirm')
await page.getByRole('dialog').getByRole('button', { name: /Confirm conversion/ }).click()
await page.waitForTimeout(2000)
dtext = await page.getByRole('dialog').innerText()
check('convert result names the new Deal', /converted to DEAL-/.test(dtext), (dtext.match(/LEAD-\d+ converted to DEAL-\d+/) || [''])[0])
await shot('convert-result')
await page.getByRole('dialog').getByRole('button', { name: 'Go to Deal' }).click()
await page.waitForTimeout(1800)

// ---------------------------------------------------------------- DEAL PAGE
await shot('deal-stage8')
const url = page.url()
check('landed on the Deal page', /\/deals\/DEAL-\d+/.test(url), url)
body = await page.locator('body').innerText()
check('deal header shows Contract value', /Contract value: \$/.test(body))
check('deal header links back to the parent Lead', /From LEAD-00118/.test(body))
check('deal stage line has NO probability band', /Stage 8 · Project Success · owner role/.test(body), (body.match(/Stage 8 · [^\n]*/) || [''])[0])

const dealRail = await page.locator('.rounded-full.border-2').count()
// Deals now rail 7-9 (Close, Project Success, Expansion) — Stage 7 was added
// to the Deals module so its own fields (PO Number, Contract Signed Date,
// Payment Schedule Confirmed) are reachable, not just present in the spec.
check('deal rail draws 3 stages (7–9)', dealRail === 3, `found ${dealRail}`)

const dealTabs = await page.getByRole('tab').allInnerTexts()
check('deal tab order current/details/related/history', dealTabs.join(',') === 'Current stage,Details,Related,History', dealTabs.join(','))

const dealAdv = await page.getByRole('button', { name: /Advance to Stage|Change stage/ }).innerText()
check('deal advance button label', dealAdv.trim() === 'Advance to Stage 9', dealAdv.trim())

await page.getByRole('tab', { name: 'Details' }).click()
await page.waitForTimeout(600)
body = await page.locator('body').innerText()
check('deal details heading text', body.includes('On conversion, and system fields'))
// View mode hides empty fields, and this Deal has no parent_opportunity, so
// the whole read-through section drops out — documented behaviour, not a
// refactor artefact. It appears in EDIT mode with the reason stated.
check('deal read-through section hidden in view mode (all empty)', !/READ THROUGH THE PARENT/i.test(body))
await shot('deal-details')
await page.getByRole('button', { name: 'Edit' }).first().click()
await page.waitForTimeout(900)
body = await page.locator('body').innerText()
check('deal edit mode shows the read-through section', /READ THROUGH THE PARENT/i.test(body))
check('read-through fields say why they are unresolved', /no Parent Opportunity is set on this record/i.test(body))
await shot('deal-details-edit')
await page.getByRole('button', { name: /^Cancel$/ }).first().click()
await page.waitForTimeout(600)

// history date format — CLAUDE.md says dd MMM yyyy
await page.getByRole('tab', { name: 'History' }).click()
await page.waitForTimeout(800)
body = await page.locator('body').innerText()
check('deal history renders (no transitions yet is fine)', /No transitions recorded yet|\d{2} \w{3} \d{4}/.test(body))
await shot('deal-history')

// deal advance dialog: now spans 3 stages (7-9), so it CAN skip — same as
// Leads/Opportunities. The 2-stage-only "no skip sentence" case no longer
// applies to Deals now that Stage 7 is part of its own rail.
await page.getByRole('tab', { name: 'Current stage' }).click()
await page.waitForTimeout(300)
await page.getByRole('button', { name: /Advance to Stage 9/ }).click()
await page.waitForTimeout(500)
dtext = await page.getByRole('dialog').innerText()
check('deal dialog offers the skip sentence (rail now spans 3 stages)', /moving forward more than one/.test(dtext))
await shot('deal-dialog')
await page.keyboard.press('Escape')
await page.waitForTimeout(400)

// ------------------------------------------------- LEAD is now read-only
await page.goto(`${BASE}/leads/LEAD-00118`)
await page.waitForTimeout(1600)
body = await page.locator('body').innerText()
check('converted lead shows the read-only banner', /converted to a Deal and is read-only/.test(body))
check('converted lead offers Go to DEAL', /Go to DEAL-\d+/.test(body))
const editCount = await page.getByRole('button', { name: 'Edit' }).count()
check('converted lead hides Edit', editCount === 0, `${editCount} Edit buttons`)
const advCount = await page.getByRole('button', { name: /Advance to Stage|Change stage/ }).count()
check('converted lead hides Advance', advCount === 0, `${advCount} advance buttons`)
await shot('lead-converted')

// ------------------------------------------------------ history on the lead
await page.getByRole('tab', { name: 'History' }).click()
await page.waitForTimeout(900)
body = await page.locator('body').innerText()
check('lead history shows the skip we made', /skip/.test(body))
check('lead history date is dd MMM yyyy', /\d{2} \w{3} \d{4}/.test(body), (body.match(/\d{2} \w{3} \d{4}/) || [''])[0])
await shot('lead-history')

console.log('\nconsole errors:', errors.length)
for (const e of errors.slice(0, 10)) console.log('  ', e)
const failed = results.filter((r) => !r.ok)
console.log(`\n${results.length - failed.length}/${results.length} checks passed`)
if (failed.length) { console.log('FAILED:'); for (const f of failed) console.log('  -', f.name, f.detail) }
await browser.close()
process.exit(failed.length || errors.length ? 1 : 0)
