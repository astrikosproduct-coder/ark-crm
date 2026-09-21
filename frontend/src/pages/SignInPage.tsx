import { startSignIn, useAuth } from '@/lib/auth'
import { Button } from '@/components/ui/button'

/**
 * The only screen an unauthenticated visitor can reach, at /login. Any other
 * address a signed-out visitor opens is replaced with /login (see AuthGate).
 *
 * There is no username or password field, and there never will be: this
 * application does not hold credentials. Microsoft Entra authenticates the
 * person and tells us who they are; ARK CRM decides what they may do, from the
 * roles an administrator assigned.
 */
export function SignInPage() {
  const error = new URLSearchParams(window.location.search).get('error')

  return (
    // The picture is public/login-bg.jpg, served at /login-bg.jpg. An inline
    // style, not a Tailwind url() class, so the build never tries to resolve
    // it: if the file is missing the page still renders, on the slate ground
    // underneath. The gradient keeps the card readable on any photograph.
    <div
      className="relative flex min-h-screen items-center justify-center bg-slate-900 bg-cover bg-center px-4"
      style={{ backgroundImage: `url(${LOGIN_BACKGROUND})` }}
    >
      <div aria-hidden className="absolute inset-0 bg-gradient-to-br from-slate-950/70 via-slate-900/40 to-slate-950/70" />

      <div className="relative w-full max-w-sm rounded-xl bg-white p-8 shadow-2xl">
        <img src={encodeURI('/Astrikos logo.png')} alt="Astrikos" className="h-12 w-auto" />
        <h1 className="mt-4 text-xl font-semibold text-slate-900">ARK CRM</h1>
        
        {error && (
          <p role="alert" className="mt-6 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
            Microsoft could not sign you in ({error}). Try again; if it keeps happening, tell an
            administrator.
          </p>
        )}

        <Button className="mt-8 w-full" onClick={startSignIn}>
          Sign in with Microsoft
        </Button>

        <p className="mt-4 text-center text-xs text-slate-400">
          Use your Astrikos work account.
        </p>
      </div>
    </div>
  )
}

/** Drop the picture at frontend/public/login-bg.jpg. */
const LOGIN_BACKGROUND = '/login-bg.png'

/**
 * Signed in, recognised, and allowed nothing yet.
 *
 * Everyone in the Astrikos tenant can authenticate — so authenticating is not
 * access. A new arrival lands here with no roles and sees no data at all until
 * an administrator grants them one.
 */
export function PendingAccessPage() {
  const { user, signOut } = useAuth()

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-md rounded-lg border bg-white p-8 shadow-sm">
        <h1 className="text-lg font-semibold text-slate-900">Access pending</h1>
        <p className="mt-3 text-sm text-slate-600">
          You are signed in as <span className="font-medium">{user?.email}</span>, but no role has
          been assigned to your account yet.
        </p>
        <p className="mt-3 text-sm text-slate-600">
          An administrator needs to grant you access in Administration. You will see the pipeline
          as soon as they do — refresh this page after they confirm.
        </p>

        <div className="mt-6 flex gap-2">
          <Button variant="outline" onClick={() => window.location.reload()}>
            Refresh
          </Button>
          <Button variant="ghost" onClick={() => void signOut()}>
            Sign out
          </Button>
        </div>
      </div>
    </div>
  )
}
