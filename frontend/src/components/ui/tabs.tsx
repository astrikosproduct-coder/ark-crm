import * as TabsPrimitive from '@radix-ui/react-tabs'

import { cn } from '@/lib/utils'

/**
 * Two tab looks, because the reference has two: an underline row for a screen
 * whose tabs ARE the screen (Administration's editors), and a rounded segmented
 * control for the Overview / Timeline switch on a record — ARK_brand_UI.md
 * §3.3 and §3.6. The variant is passed to the list and to each trigger.
 */
export type TabsVariant = 'underline' | 'pill'

function Tabs({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Root>) {
  return <TabsPrimitive.Root data-slot="tabs" className={cn('flex flex-col', className)} {...props} />
}

function TabsList({
  className,
  variant = 'underline',
  ...props
}: React.ComponentProps<typeof TabsPrimitive.List> & { variant?: TabsVariant }) {
  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      className={cn(
        'flex items-center',
        variant === 'pill'
          ? 'border-border bg-card inline-flex w-fit gap-1 rounded-full border p-1'
          : 'border-border gap-1 border-b',
        className
      )}
      {...props}
    />
  )
}

function TabsTrigger({
  className,
  variant = 'underline',
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Trigger> & { variant?: TabsVariant }) {
  return (
    <TabsPrimitive.Trigger
      data-slot="tabs-trigger"
      className={cn(
        'text-muted-foreground text-sm font-medium transition-colors outline-none disabled:pointer-events-none disabled:opacity-50',
        variant === 'pill'
          ? 'data-[state=active]:bg-primary data-[state=active]:text-primary-foreground hover:text-foreground rounded-full px-5 py-1.5 font-semibold'
          : 'data-[state=active]:border-primary data-[state=active]:text-foreground -mb-px border-b-2 border-transparent px-3 py-2',
        className
      )}
      {...props}
    />
  )
}

function TabsContent({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Content>) {
  return <TabsPrimitive.Content data-slot="tabs-content" className={cn('pt-4', className)} {...props} />
}

export { Tabs, TabsList, TabsTrigger, TabsContent }
