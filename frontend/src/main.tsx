import './index.css'
import { loadPublishedSpec } from '@/lib/spec/source'

// The register first, then the app. Every module that reads fields,
// picklists or stages reads them when it loads, so the published copy has to
// be in place before the first of them is imported — hence the dynamic
// import. Falls back to the built-in copy on any failure. See
// lib/spec/source.ts.
void loadPublishedSpec()
  .then(() => import('./boot'))
  .then(({ render }) => render())
