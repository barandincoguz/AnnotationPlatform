import type { AuditDiscrepancy } from '@/api/queries/annotations'

export function discrepancyKey(discrepancy: AuditDiscrepancy, index: number): string {
  const reference = discrepancy.model_reference ?? discrepancy.human_reference
  return [
    index,
    discrepancy.kind,
    discrepancy.kanun_no,
    discrepancy.madde,
    reference?.fikra ?? '',
    reference?.bent ?? '',
    reference?.source_text ?? '',
  ].join(':')
}
