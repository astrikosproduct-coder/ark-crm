import * as React from 'react'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { XIcon } from 'lucide-react'

import { cn } from '@/lib/utils'

/**
 * A side drawer. The same Radix Dialog the modal uses, anchored to an edge and
 * full height rather than centred — so focus trapping, Esc and the scroll lock
 * all behave exactly as they already do everywhere else.
 */
const Sheet = DialogPrimitive.Root
const SheetTrigger = DialogPrimitive.Trigger
const SheetClose = DialogPrimitive.Close

function SheetContent({
  className,
  children,
  side = 'right',
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Content> & { side?: 'right' | 'left' | 'top' }) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="data-[state=open]:animate-fade-in data-[state=closed]:animate-fade-out fixed inset-0 z-50 bg-black/60" />
      <DialogPrimitive.Content
        data-slot="sheet-content"
        className={cn(
          'bg-popover text-popover-foreground fixed z-50 flex w-full max-w-sm flex-col gap-5 p-6 shadow-lg',
          side === 'right' &&
            'data-[state=open]:animate-slide-in-right data-[state=closed]:animate-slide-out-right inset-y-0 right-0 border-l',
          side === 'left' &&
            'data-[state=open]:animate-slide-in-left data-[state=closed]:animate-slide-out-left inset-y-0 left-0 border-r',
          // From the top: drops down from the top edge, as tall as it needs.
          side === 'top' &&
            'data-[state=open]:animate-slide-in-top data-[state=closed]:animate-slide-out-top top-0 max-h-[85vh] rounded-b-lg border border-t-0',
          className
        )}
        {...props}
      >
        {children}
        <DialogPrimitive.Close
          className="text-muted-foreground hover:text-foreground absolute top-5 right-5 rounded-sm transition-colors"
          aria-label="Close"
        >
          <XIcon className="size-4" />
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  )
}

function SheetHeader({ className, ...props }: React.ComponentProps<'div'>) {
  return <div className={cn('flex flex-col gap-1.5', className)} {...props} />
}

function SheetTitle({ className, ...props }: React.ComponentProps<typeof DialogPrimitive.Title>) {
  return (
    <DialogPrimitive.Title
      className={cn('text-record-title leading-none font-bold', className)}
      {...props}
    />
  )
}

function SheetDescription({
  className,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Description>) {
  return (
    <DialogPrimitive.Description
      className={cn('text-muted-foreground text-sm', className)}
      {...props}
    />
  )
}

export { Sheet, SheetTrigger, SheetClose, SheetContent, SheetHeader, SheetTitle, SheetDescription }
