/** How long the ring pulses for — matches .ark-field-flash in index.css. */
const FLASH_MS = 1500
const FLASH_CLASS = 'ark-field-flash'

/** The attribute FieldRow stamps on every field it draws. */
export const FIELD_ANCHOR = 'data-field'

/**
 * Scroll a field into view and pulse it.
 *
 * Called after something has already changed what is on screen — a tab switch,
 * a stage selection, an editor opening — so the field is usually not in the DOM
 * yet at the moment of the click. Hence the short poll rather than a single
 * lookup: React has to commit first. It gives up quietly if the field never
 * appears, because failing to animate is not worth an error on a screen the
 * user is already looking at.
 *
 * The focus is deliberately late and `preventScroll`: focusing an element
 * scrolls it into view INSTANTLY, which would cancel the smooth scroll that is
 * the whole point.
 */
export function revealField(apiName: string, timeoutMs = 2000): void {
  const deadline = Date.now() + timeoutMs

  const attempt = () => {
    const el = document.querySelector<HTMLElement>(`[${FIELD_ANCHOR}="${CSS.escape(apiName)}"]`)
    if (!el) {
      if (Date.now() < deadline) window.setTimeout(attempt, 60)
      return
    }

    el.scrollIntoView({ behavior: 'smooth', block: 'center' })

    // Restart the animation even if this field was just flashed.
    el.classList.remove(FLASH_CLASS)
    void el.offsetWidth
    el.classList.add(FLASH_CLASS)
    window.setTimeout(() => el.classList.remove(FLASH_CLASS), FLASH_MS)

    const control = el.querySelector<HTMLElement>('input, textarea, [role="combobox"]')
    window.setTimeout(() => control?.focus({ preventScroll: true }), 400)
  }

  window.setTimeout(attempt, 0)
}
