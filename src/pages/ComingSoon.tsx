import { Construction } from 'lucide-react'

export function ComingSoon({ label }: { label: string }) {
  return (
    <div className="border-border flex flex-col items-center gap-3 rounded-lg border border-dashed py-16 text-center">
      <Construction className="text-muted-foreground size-8" />
      <div>
        <p className="text-foreground font-medium">Coming in this prototype</p>
        <p className="text-muted-foreground mt-1 text-sm">
          {label} hasn't been built yet in this walkthrough.
        </p>
      </div>
    </div>
  )
}
