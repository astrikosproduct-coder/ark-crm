import {
  LayoutDashboard,
  Target,
  Briefcase,
  Handshake,
  Building2,
  Users,
  Network,
  Package,
  FileText,
  ShieldCheck,
  ClipboardCheck,
  Paperclip,
  Settings,
  SquarePen,
  Stethoscope,
  type LucideIcon,
} from 'lucide-react'

export interface ModuleDef {
  key: string
  label: string
  icon: LucideIcon
  built: boolean
}

export const MODULES: ModuleDef[] = [
  { key: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, built: false },
  { key: 'leads', label: 'Leads', icon: Target, built: true },
  { key: 'opportunities', label: 'Opportunities', icon: Briefcase, built: true },
  { key: 'deals', label: 'Deals', icon: Handshake, built: true },
  { key: 'accounts', label: 'Accounts', icon: Building2, built: true },
  { key: 'contacts', label: 'Contacts', icon: Users, built: true },
  { key: 'partners', label: 'Partners', icon: Network, built: true },
  { key: 'products', label: 'Products', icon: Package, built: false },
  { key: 'quotes', label: 'Quotes', icon: FileText, built: false },
  { key: 'gates', label: 'Gates', icon: ShieldCheck, built: false },
  { key: 'approvals', label: 'Approvals', icon: ClipboardCheck, built: false },
  { key: 'activities_docs', label: 'Activities & Documents', icon: Paperclip, built: false },
  { key: 'administration', label: 'Administration', icon: Settings, built: false },
]

// Prototype instrumentation rather than product surface: the form engine
// harness and the field-register worklist.
export const TOOLS: ModuleDef[] = [
  { key: 'form-engine', label: 'Form engine', icon: SquarePen, built: true },
  { key: 'spec-health', label: 'Spec health', icon: Stethoscope, built: true },
]

export function moduleFor(key: string | undefined): ModuleDef | undefined {
  return MODULES.find((m) => m.key === key)
}
