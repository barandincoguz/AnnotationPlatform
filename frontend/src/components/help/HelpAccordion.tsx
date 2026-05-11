import { Accordion } from '@/components/ui/accordion'
import { HelpSection } from './HelpSection'
import type { HelpSection as HelpSectionData } from '@/lib/trainingSchemas'

interface HelpAccordionProps {
  sections: HelpSectionData[]
}

export function HelpAccordion({ sections }: HelpAccordionProps) {
  if (sections.length === 0) return null
  const sorted = [...sections].sort((a, b) => a.order - b.order)
  const defaultValue = sorted[0] ? [sorted[0].id] : []
  return (
    <Accordion type="multiple" defaultValue={defaultValue} className="w-full">
      {sorted.map((s) => (
        <HelpSection key={s.id} section={s} />
      ))}
    </Accordion>
  )
}
