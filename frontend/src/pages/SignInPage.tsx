import { startSignIn, useAuth } from '@/lib/auth'
import { Button } from '@/components/ui/button'

/**
 * The only screen an unauthenticated visitor can reach.
 *
 * There is no username or password field, and there never will be: this
 * application does not hold credentials. Microsoft Entra authenticates the
 * person and tells us who they are; ARK CRM decides what they may do, from the
 * roles an administrator assigned.
 */
export function SignInPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-sm rounded-lg border bg-white p-8 shadow-sm">
        <h1 className="text-xl font-semibold text-slate-900">ARK CRM</h1>
        <p className="mt-1 text-sm text-slate-500">Astrikos · S!aP commercial pipeline</p>

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
