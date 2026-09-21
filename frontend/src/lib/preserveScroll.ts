/**
 * Hold the reader's place across a swap of one large subtree for another.
 *
 * Pressing Edit unmounts a whole read-only form and mounts an editor in its
 * place. For the one commit in which that happens the document is briefly
 * shorter than the scroll offset, so the browser clamps the offset — and
 * because the element it was anchored to has just been removed, scroll
 * anchoring cannot put it back. Measured on a Stage 0 lead: scrollY went
 * 601 -> 0 on the first frame after the click, and stayed there even once the
 * taller edit form had finished mounting.
 *
 * Restoring in a layout effect gets it back before the browser paints, so
 * there is no visible jump. The few frames afterwards are for content that
 * settles late — a lookup resolving its label, a child table mounting rows —
 * any of which can lengthen the page after the first restore and would
 * otherwise leave the reader a few hundred pixels off.
 */
const SETTLE_FRAMES = 3

export function restoreScroll(y: number): void {
  window.scrollTo(0, y)

  let frames = 0
  const again = () => {
    // Only if something moved it: re-asserting an offset that already holds
    // would fight a reader who has started scrolling within these ~50ms.
    if (Math.abs(window.scrollY - y) > 1) window.scrollTo(0, y)
    if (++frames < SETTLE_FRAMES) requestAnimationFrame(again)
  }
  requestAnimationFrame(again)
}
