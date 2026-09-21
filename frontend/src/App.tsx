import { lazy, useEffect } from 'react'
import {
  createBrowserRouter,
  createRoutesFromElements,
  Navigate,
  Route,
  RouterProvider,
} from 'react-router-dom'

import { AppShell } from '@/components/layout/AppShell'
import { AuthProvider, useAuth } from '@/lib/auth'
import { PendingAccessPage, SignInPage } from '@/pages/SignInPage'
import { useIsDeveloper } from '@/lib/feedback'

/**
 * Every page is loaded the first time it is opened, not with the app.
 *
 * Someone who only works in Leads never downloads Administration, the
 * Dashboard's charts or the spreadsheet import. The shell — sidebar, header,
 * sign-in — is in the first download; AppShell's <Suspense> shows a quiet
 * "Loading…" in the page area while a page's code arrives, once per session.
 * Sign-in and Access pending stay eager: they render before the router exists.
 */
const AdministrationPage = lazy(() => import('@/pages/AdministrationPage').then((m) => ({ default: m.AdministrationPage })))
const AccountDetailPage = lazy(() => import('@/pages/AccountDetailPage').then((m) => ({ default: m.AccountDetailPage })))
const AccountsPage = lazy(() => import('@/pages/AccountsPage').then((m) => ({ default: m.AccountsPage })))
const ContactDetailPage = lazy(() => import('@/pages/ContactDetailPage').then((m) => ({ default: m.ContactDetailPage })))
const ContactsPage = lazy(() => import('@/pages/ContactsPage').then((m) => ({ default: m.ContactsPage })))
const DashboardPage = lazy(() => import('@/pages/DashboardPage').then((m) => ({ default: m.DashboardPage })))
const DealDetailPage = lazy(() => import('@/pages/DealDetailPage').then((m) => ({ default: m.DealDetailPage })))
const DealsPage = lazy(() => import('@/pages/DealsPage').then((m) => ({ default: m.DealsPage })))
const FormEnginePage = lazy(() => import('@/pages/FormEnginePage').then((m) => ({ default: m.FormEnginePage })))
const LeadCreatePage = lazy(() => import('@/pages/LeadCreatePage').then((m) => ({ default: m.LeadCreatePage })))
const LeadDetailPage = lazy(() => import('@/pages/LeadDetailPage').then((m) => ({ default: m.LeadDetailPage })))
const LeadsPage = lazy(() => import('@/pages/LeadsPage').then((m) => ({ default: m.LeadsPage })))
const ModuleDetailPage = lazy(() => import('@/pages/ModuleDetailPage').then((m) => ({ default: m.ModuleDetailPage })))
const ModulePage = lazy(() => import('@/pages/ModulePage').then((m) => ({ default: m.ModulePage })))
const NewRegistrationPage = lazy(() => import('@/pages/NewRegistrationPage').then((m) => ({ default: m.NewRegistrationPage })))
const OpportunityCreatePage = lazy(() => import('@/pages/OpportunityCreatePage').then((m) => ({ default: m.OpportunityCreatePage })))
const OpportunityDetailPage = lazy(() => import('@/pages/OpportunityDetailPage').then((m) => ({ default: m.OpportunityDetailPage })))
const OpportunitiesPage = lazy(() => import('@/pages/OpportunitiesPage').then((m) => ({ default: m.OpportunitiesPage })))
const PartnerDetailPage = lazy(() => import('@/pages/PartnerDetailPage').then((m) => ({ default: m.PartnerDetailPage })))
const PartnersPage = lazy(() => import('@/pages/PartnersPage').then((m) => ({ default: m.PartnersPage })))
const RegistrationDetailPage = lazy(() => import('@/pages/RegistrationDetailPage').then((m) => ({ default: m.RegistrationDetailPage })))
const RecordCreatePage = lazy(() => import('@/pages/RecordCreatePage').then((m) => ({ default: m.RecordCreatePage })))
const SpecHealthPage = lazy(() => import('@/pages/SpecHealthPage').then((m) => ({ default: m.SpecHealthPage })))
const FeedbackPage = lazy(() => import('@/pages/FeedbackPage').then((m) => ({ default: m.FeedbackPage })))

/**
 * Administration is DEVELOPER-only in V1 (21 Sep 2026). Anyone else who types
 * the address lands on the Dashboard rather than on a screen of refusals. The
 * boundary is the server — /api/admin/* answers 403 without the role — and
 * this only keeps the screen from mounting and firing requests it would lose.
 */
function DeveloperOnly({ children }: { children: React.ReactElement }) {
  return useIsDeveloper() ? children : <Navigate to="/dashboard" replace />
}


/**
 * A DATA router, not <BrowserRouter>.
 *
 * The routes themselves are unchanged — createRoutesFromElements takes the same
 * JSX. What the data router adds is useBlocker, which is how an editor with
 * unsaved changes holds a navigation until the user answers for it. The plain
 * router has no way to interrupt a navigation at all.
 */
const router = createBrowserRouter(
  createRoutesFromElements(
    <>
    {/* A signed-in visit to /login has nothing to sign in to. Outside the
        shell, so it does not flash the navigation first. */}
    <Route path="login" element={<Navigate to="/dashboard" replace />} />
    <Route element={<AppShell />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="form-engine" element={<FormEnginePage />} />
          <Route path="spec-health" element={<SpecHealthPage />} />
          <Route path="feedback" element={<FeedbackPage />} />

          {/* DEVELOPER-only in V1 — see DeveloperOnly above. */}
          <Route
            path="administration"
            element={
              <DeveloperOnly>
                <AdministrationPage />
              </DeveloperOnly>
            }
          />

          <Route path="leads" element={<LeadsPage />} />
          <Route path="leads/new" element={<LeadCreatePage />} />
          <Route path="leads/:id" element={<LeadDetailPage />} />

          <Route path="opportunities" element={<OpportunitiesPage />} />
          <Route path="opportunities/new" element={<OpportunityCreatePage />} />
          <Route path="opportunities/:id" element={<OpportunityDetailPage />} />

          <Route path="deals" element={<DealsPage />} />
          <Route path="deals/:id" element={<DealDetailPage />} />

          <Route path="accounts" element={<AccountsPage />} />
          <Route
            path="accounts/new"
            element={
              <RecordCreatePage
                module="accounts"
                collection="accounts"
                basePath="/accounts"
                title="New account"
              />
            }
          />
          <Route path="accounts/:id" element={<AccountDetailPage />} />

          <Route path="contacts" element={<ContactsPage />} />
          <Route
            path="contacts/new"
            element={
              <RecordCreatePage
                module="contacts"
                collection="contacts"
                basePath="/contacts"
                title="New contact"
              />
            }
          />
          <Route path="contacts/:id" element={<ContactDetailPage />} />

          {/* Registrations are nested under partners rather than given a
              top-level route, because a registration has no meaning apart from
              the partner that submitted it. The static segments outrank
              partners/:id, so REG ids and ACC ids cannot collide. */}
          <Route path="partners" element={<PartnersPage />} />
          <Route path="partners/registrations/new" element={<NewRegistrationPage />} />
          <Route path="partners/registrations/:id" element={<RegistrationDetailPage />} />
          <Route path="partners/:id" element={<PartnerDetailPage />} />

          {/* Everything not built yet still resolves, through the generic
              spec-driven screens. */}
      <Route path=":module" element={<ModulePage />} />
      <Route path=":module/:id" element={<ModuleDetailPage />} />
    </Route>
    </>
  )
)

/** The sign-in screen's own address. */
const LOGIN_PATH = '/login'

/**
 * The gate.
 *
 * Nothing behind it renders until identity is known, which is why this sits
 * outside the router rather than inside a route: a signed-out visitor must not
 * reach a screen that would immediately fire data requests, and a user whose
 * access is still pending must not see the shell of an application they cannot
 * use.
 *
 * This is the courtesy layer, NOT the security boundary — that lives on the API
 * (see backend/app/main.py, where every data router carries require_access).
 * Hiding a screen protects nobody on its own.
 */
function AuthGate() {
  const { state } = useAuth()

  // Signed out, the address bar says /login whatever was typed. The address
  // asked for is NOT remembered: a successful sign-in always lands on the
  // Dashboard (backend/app/routers/auth.py::callback). A sign-in error arrives
  // as /login?error=..., and that query is kept so the page can show it.
  useEffect(() => {
    if (state.status === 'signed-out' && window.location.pathname !== LOGIN_PATH) {
      window.history.replaceState(null, '', LOGIN_PATH)
    }
  }, [state.status])

  if (state.status === 'loading') {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-slate-500">
        Signing you in…
      </div>
    )
  }

  if (state.status === 'signed-out') return <SignInPage />
  if (state.user.pending) return <PendingAccessPage />

  return <RouterProvider router={router} />
}

function App() {
  return (
    <AuthProvider>
      <AuthGate />
    </AuthProvider>
  )
}

export default App
