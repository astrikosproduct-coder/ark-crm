import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    // Pinned, and strict on purpose. Vite silently falls back to 5174 when 5173
    // is busy, and the Entra app registration lists ONE redirect URI — a
    // silent port change makes Microsoft reject every sign-in with an error
    // that does not explain itself. Fail on start instead.
    port: 5173,
    strictPort: true,
    proxy: {
      // Sign-in. Needs a proxy entry AND the passthrough handler in
      // src/mocks/handlers.ts — with only one of the two this silently returns
      // Vite's HTML page instead of reaching FastAPI.
      '/api/auth': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // Administration is the one module backed by a real database. Proxying
      // it here keeps the frontend on a single axios client (baseURL '/api')
      // and a single origin — no CORS, no second API pattern in React.
      // Everything else under /api/ never reaches this proxy, because MSW
      // answers it in the browser first.
      '/api/admin': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // The user directory. Users are a real database resource, so every
      // user-lookup field in the application resolves through here rather than
      // from the mock store. MSW passes /api/users through to this proxy.
      '/api/users': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // Accounts — End Clients and Partners alike. The Partners screen reads
      // this same collection with an account_type filter.
      '/api/accounts': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // Contacts — the external people at those accounts.
      '/api/contacts': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // The three pipeline modules. Phase-1 cutover: Leads, Opportunities and
      // Deals are real tables now, not browser-store collections.
      '/api/leads': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/api/opportunities': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/api/deals': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // Stage transitions — the pipeline's audit trail of every skip and
      // reversal, with its mandatory reason. Round 7's first cutover.
      '/api/transitions': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // Conversions — the audit trail of a Lead becoming an Opportunity or
      // Deal, or an Opportunity becoming a Deal. Round 7's second cutover.
      '/api/conversions': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // The record-level audit trail — every create, update and delete, with
      // the before/after diff the History timeline renders. Read-only: there
      // is no POST, because rows are written from inside the business routers
      // and a client must not be able to write its own history.
      '/api/audit-log': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // Deal registrations — a partner's claim to a deal and its exclusivity
      // window. Round 3, done out of order.
      '/api/registrations': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // Registration conflicts — the adjudication when two partners register
      // the same client and project. Round 3, done out of order.
      '/api/conflicts': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // Pursuit Groups — which of several partners' pursuits of one project
      // counts toward pipeline. See backend/app/pursuits.py.
      '/api/pursuit-groups': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // The management dashboard — read-only aggregates over the live pipeline.
      // See backend/app/routers/dashboard.py.
      // Global search — the header box, every live module in one request.
      '/api/search': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/api/dashboard': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // User feedback — anyone sends, DEVELOPER reads. See backend/app/routers/feedback.py.
      '/api/feedback': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // Excel / CSV import and export. See backend/app/routers/spreadsheets.py.
      '/api/spreadsheets': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
