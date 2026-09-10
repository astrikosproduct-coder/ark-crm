import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

/**
 * The last line of defence against a blank screen.
 *
 * Without this, any error thrown during render unmounts the whole tree and
 * leaves an empty page with nothing to act on — the failure looked to users
 * like "the app went blank and I had to refresh". It now says what happened and
 * offers the reload, instead of leaving people to guess.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ark] render failed:', error, info.componentStack)
  }

  render() {
    const { error } = this.state
    if (!error) return this.props.children

    return (
      <div className="bg-background text-foreground flex min-h-screen items-center justify-center px-6">
        <div className="max-w-md">
          <h1 className="text-page-title font-bold">Something went wrong.</h1>
          <p className="text-muted-foreground mt-2 text-sm">
            The screen could not be drawn. Reloading usually clears it; if it does not, the
            message below is what to report.
          </p>
          <pre className="bg-card mt-4 max-h-40 overflow-auto rounded-md border p-3 font-mono text-xs break-words whitespace-pre-wrap">
            {error.message}
          </pre>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="bg-primary text-primary-foreground text-button hover:bg-primary/90 mt-4 rounded-md px-4 py-2 font-semibold"
          >
            Reload the page
          </button>
        </div>
      </div>
    )
  }
}
