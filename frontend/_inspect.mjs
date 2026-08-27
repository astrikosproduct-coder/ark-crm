import { chromium } from 'playwright'
const BASE = 'http://localhost:5174'
const browser = await chromium.launch()
const page = await browser.newPage()
await page.goto(BASE + '/leads/LEAD-00118', { waitUntil: 'networkidle' })
await page.waitForTimeout(500)
const rec = await page.evaluate(async () => {
  const res = await fetch('/api/leads/LEAD-00118')
  return res.json()
})
console.log(JSON.stringify(rec, null, 2))
await browser.close()
