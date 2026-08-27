import { NavLink } from 'react-router-dom'

import { MODULES, TOOLS } from '@/lib/modules'
import { cn } from '@/lib/utils'

export function Sidebar() {
  return (
    <nav className="border-border bg-background flex w-56 shrink-0 flex-col gap-0.5 border-r px-2 py-3">
      {MODULES.map((mod) => (
        <NavLink
          key={mod.key}
          to={`/${mod.key}`}
          className={({ isActive }) =>
            cn(
              'flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors',
              isActive
                ? 'bg-secondary text-secondary-foreground'
                : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
            )
          }
        >
          <mod.icon className="size-4 shrink-0" />
          <span className="truncate">{mod.label}</span>
        </NavLink>
      ))}

      <div className="mt-4 border-t pt-3">
        <p className="px-3 pb-1 text-xs font-medium text-muted-foreground">Prototype tools</p>
        {TOOLS.map((tool) => (
          <NavLink
            key={tool.key}
            to={`/${tool.key}`}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-secondary text-secondary-foreground'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
              )
            }
          >
            <tool.icon className="size-4 shrink-0" />
            <span className="truncate">{tool.label}</span>
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
