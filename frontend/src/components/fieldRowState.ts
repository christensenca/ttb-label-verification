import type { components } from '../api/generated'

type Field = components['schemas']['FieldRowOut']

const NON_TEXT_FIELDS = new Set(['is_imported', 'government_warning_style'])

export type RowColor = 'green' | 'yellow' | 'red' | 'grey'

/**
 * Tri-state row color per research.md R11 truth table. Surfaced as a
 * `data-row-state` attribute for testing.
 */
export function rowColorClass(field: Field): RowColor {
  if (field.effective_verdict === 'not_applicable') return 'grey'
  if (field.effective_verdict === 'fail') return 'red'
  const isText = !NON_TEXT_FIELDS.has(field.field)
  if (isText && (field.confidence === 'low' || field.confidence === 'med')) {
    return 'yellow'
  }
  return 'green'
}
