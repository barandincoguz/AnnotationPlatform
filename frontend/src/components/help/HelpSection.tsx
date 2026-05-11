import { AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion'
import { MarkdownView } from './MarkdownView'
import type { HelpSection as HelpSectionData } from '@/lib/trainingSchemas'

interface HelpSectionProps {
  section: HelpSectionData
}

export function HelpSection({ section }: HelpSectionProps) {
  return (
    <AccordionItem value={section.id}>
      <AccordionTrigger>{section.title}</AccordionTrigger>
      <AccordionContent>
        <MarkdownView>{section.body}</MarkdownView>
      </AccordionContent>
    </AccordionItem>
  )
}
