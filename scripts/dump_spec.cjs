// Bundles the real spec loader — src/lib/spec/index.ts, module split and all —
// and returns what it actually produces.
//
// The alternative was to re-implement spec/module_split.json a second time
// inside the documentation script, which is how a document starts disagreeing
// with the application it documents. This runs the same code the app runs, so
// LIVE_FIELDS.md cannot drift from the loader: if the split changes, the
// document changes with it or the build fails.
//
// Bundled with rolldown, which Vite already depends on. Nothing new installed.
const fs = require('fs')
const os = require('os')
const path = require('path')

const ROOT = path.resolve(__dirname, '..')

async function bundleSpec() {
  const { rolldown } = require('rolldown')

  const entry = path.join(
    os.tmpdir(),
    `arkcrm-spec-entry-${process.pid}.ts`
  )
  fs.writeFileSync(
    entry,
    [
      'export {',
      '  fields, picklists, optionsFor, fieldByRef, sectionsFor, fieldsOf,',
      '  movedRefs, movedRefUsages, newFields, splitErrors, specRefErrors,',
      '} from ' + JSON.stringify(path.join(ROOT, 'src/lib/spec/index.ts').replace(/\\/g, '/')),
      'export { childSpecFor, isChildColumnOnly } from ' +
        JSON.stringify(path.join(ROOT, 'src/lib/spec/childSpec.ts').replace(/\\/g, '/')),
      'export { split, PIPELINE_MODULES } from ' +
        JSON.stringify(path.join(ROOT, 'src/lib/spec/moduleSplit.ts').replace(/\\/g, '/')),
    ].join('\n')
  )

  const out = path.join(os.tmpdir(), `arkcrm-spec-bundle-${process.pid}.cjs`)
  try {
    const build = await rolldown({
      input: entry,
      platform: 'node',
      // The spec layer imports only JSON and its own siblings. `@/types/field`
      // is type-only and erases, so no alias resolution is needed here.
      resolve: { alias: { '@': path.join(ROOT, 'src') } },
    })
    await build.write({ file: out, format: 'cjs' })
    await build.close()

    delete require.cache[require.resolve(out)]
    return require(out)
  } finally {
    for (const f of [entry, out]) {
      try {
        fs.unlinkSync(f)
      } catch {
        /* the temp file may already be gone */
      }
    }
  }
}

module.exports = { bundleSpec }
