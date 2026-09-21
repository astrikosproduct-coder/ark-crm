import { useEffect } from 'react'
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
import { AdministrationPage } from '@/pages/AdministrationPage'
import { AccountDetailPage } from '@/pages/AccountDetailPage'
import { AccountsPage } from '@/pages/AccountsPage'
import { ContactDetailPage } from '@/pages/ContactDetailPage'
import { ContactsPage } from '@/pages/ContactsPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { DealDetailPage } from '@/pages/DealDetailPage'
import { DealsPage } from '@/pages/DealsPage'
import { FormEnginePage } from '@/pages/FormEnginePage'
import { LeadCreatePage } from '@/pages/LeadCreatePage'
import { LeadDetailPage } from '@/pages/LeadDetailPage'
import { LeadsPage } from '@/pages/LeadsPage'
import { ModuleDetailPage } from '@/pages/ModuleDetailPage'
import { ModulePage } from '@/pages/ModulePage'
import { NewRegistrationPage } from '@/pages/NewRegistrationPage'
import { OpportunityCreatePage } from '@/pages/OpportunityCreatePage'
import { OpportunityDetailPage } from '@/pages/OpportunityDetailPage'
import { OpportunitiesPage } from '@/pages/OpportunitiesPage'
import { PartnerDetailPage } from '@/pages/PartnerDetailPage'
import { PartnersPage } from '@/pages/PartnersPage'
import { RegistrationDetailPage } from '@/pages/RegistrationDetailPage'
import { RecordCreatePage } from '@/pages/RecordCreatePage'
import { SpecHealthPage } from '@/pages/SpecHealthPage'
import { FeedbackPage } from '@/pages/FeedbackPage'


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

          {/* The one module served by FastAPI + PostgreSQL rather than MSW. */}
          <Route path="administration" element={<AdministrationPage />} />

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
