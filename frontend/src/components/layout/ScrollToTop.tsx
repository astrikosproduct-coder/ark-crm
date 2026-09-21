import { useEffect, useState } from 'react'
import { ChevronUpIcon } from 'lucide-react'

/**
 * The round "back to top" control the reference floats over the bottom-right
 * of a long record page. Appears once the page has scrolled a screenful, and
 * is nothing but a scroll — it carries no state and reads no record.
 */
export function ScrollToTop() {
  const [shown, setShown] = useState(false)

  useEffect(() => {
    const onScroll = () => setShown(window.scrollY > 400)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  if (!shown) return null

  return (
    <button
      type="button"
      aria-label="Back to top"
      title="Back to top"
      onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
      className="border-border bg-card text-muted-foreground hover:text-foreground fixed right-6 bottom-6 z-30 flex size-11 items-center justify-center rounded-full border shadow-lg transition-colors"
    >
      <ChevronUpIcon className="size-5" />
    </button>
  )
}
