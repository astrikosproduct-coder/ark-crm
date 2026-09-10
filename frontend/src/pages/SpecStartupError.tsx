/**
 * The one spec problem that stops the prototype rather than degrading.
 *
 * Rendered instead of the app, in place of the blank page a module-scope throw
 * would give. Everything else the spec can get wrong — a formula that will not
 * compile, a list column naming a field that no longer exists — fails open and
 * is reported on Spec Health, because a missing value is visibly missing. A
 * reference to a duplicated api_name is different: it would resolve to a real
 * field, just not the one that was meant, and the screen would look right.
 */
export function SpecStartupError({ errors }: { errors: string[] }) {
  return (
    <div className="bg-background text-foreground min-h-screen px-6 py-10">
      <div className="mx-auto max-w-3xl">
        <p className="text-destructive text-sm font-semibold tracking-wide uppercase">
          Spec did not load
        </p>
        <h1 className="text-page-title mt-1 font-bold">
          {errors.length} reference{errors.length === 1 ? '' : 's'} in spec/extensions.json cannot
          be resolved
        </h1>
        <p className="text-muted-foreground mt-2 text-sm">
          Each one names an api_name that the register defines in more than one section of the same
          module, without saying which is meant. The prototype will not guess: a screen built on
          the wrong field of a pair looks entirely correct, which is the one failure nobody would
          catch by looking. Qualify the reference with its section and reload.
        </p>

        <ul className="mt-6 space-y-3">
          {errors.map((message) => (
            <li key={message} className="border-destructive/40 bg-destructive/5 rounded-lg border p-3">
              <p className="font-mono text-sm break-words">{message}</p>
            </li>
          ))}
        </ul>

        <p className="text-muted-foreground mt-6 text-sm">
          The full list of duplicated api_names is on the Spec Health page once the app loads, and
          in spec/README.md.
        </p>
      </div>
    </div>
  )
}
