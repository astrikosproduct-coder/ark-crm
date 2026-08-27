import { useParams } from 'react-router-dom'

import { PageLayout } from '@/components/layout/PageLayout'
import { humanize } from '@/lib/format'
import { moduleFor } from '@/lib/modules'
import { Button } from '@/components/ui/button'
import { ComingSoon } from '@/pages/ComingSoon'

export function ModulePage() {
  const { module } = useParams<{ module: string }>()
  const key = module ?? ''
  const label = moduleFor(key)?.label ?? humanize(key)

  return (
    <PageLayout
      title={label}
      actions={<Button disabled>New</Button>}
      tabs={[{ key: 'list', label: 'List', content: <ComingSoon label={label} /> }]}
    />
  )
}
