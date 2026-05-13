import type { components } from '../api/generated'
import InlineDiff from './InlineDiff'
import ConfidenceBadge from './ConfidenceBadge'
import styles from './FieldRow.module.css'

type Field = components['schemas']['FieldRowOut']

const FIELD_LABELS: Record<string, string> = {
  brand: 'Brand',
  class_type: 'Class / Type',
  alcohol_content: 'Alcohol content',
  net_contents: 'Net contents',
  producer_name: 'Producer name',
  producer_address: 'Producer address',
  is_imported: 'Imported',
  country_of_origin: 'Country of origin',
  government_warning_text: 'Warning text',
  government_warning_style: 'Warning style',
}

const NON_TEXT_FIELDS = new Set(['is_imported', 'government_warning_style'])

export type RowColor = 'green' | 'yellow' | 'red' | 'grey'

/**
 * Tri-state row color per research.md R11 truth table.
 * Non-text fields (is_imported, government_warning_style) have no confidence
 * score — they can only be green or red, never yellow.
 */
export function rowColorClass(field: Field): RowColor {
  if (field.effective_verdict === 'not_applicable') return 'grey'
  if (field.effective_verdict === 'fail') return 'red'
  // effective_verdict === 'pass' below
  const isText = !NON_TEXT_FIELDS.has(field.field)
  if (isText && (field.confidence === 'low' || field.confidence === 'med')) {
    return 'yellow'
  }
  return 'green'
}

function verdictLabel(field: Field): string {
  if (field.effective_verdict === 'not_applicable') return 'Not applicable'
  if (field.override) {
    return field.override.override_verdict === 'pass'
      ? 'Overridden Pass'
      : 'Overridden Fail'
  }
  return field.effective_verdict === 'pass' ? 'Pass' : 'Fail'
}

export default function FieldRow({ field }: { field: Field }) {
  const label = FIELD_LABELS[field.field] ?? field.field
  const color = rowColorClass(field)
  const rowClass = [
    styles.row,
    styles[color],
    field.override ? styles.overridden : '',
  ]
    .filter(Boolean)
    .join(' ')

  const showDiffExtracted =
    field.effective_verdict === 'fail' &&
    field.diff_extracted &&
    field.diff_extracted.length > 0
  const showDiffExpected =
    field.effective_verdict === 'fail' &&
    field.diff_expected &&
    field.diff_expected.length > 0

  return (
    <tr className={rowClass} data-row-state={color}>
      <td className={styles.cellLabel}>{label}</td>
      <td className={styles.cellValue}>
        {showDiffExtracted ? (
          <InlineDiff tokens={field.diff_extracted!} />
        ) : field.extracted_value != null ? (
          field.extracted_value
        ) : (
          <span className={styles.empty}>—</span>
        )}
      </td>
      <td className={styles.cellValue}>
        {showDiffExpected ? (
          <InlineDiff tokens={field.diff_expected!} />
        ) : field.expected_value != null ? (
          field.expected_value
        ) : (
          <span className={styles.empty}>—</span>
        )}
        <ConfidenceBadge field={field.field} confidence={field.confidence ?? null} />
      </td>
      <td className={styles.cellVerdict}>
        <span className={styles.verdictPill}>{verdictLabel(field)}</span>
        {field.override && (
          <span className={styles.originalVerdict}>
            (model said: {field.override.original_verdict})
          </span>
        )}
        <div className={styles.rule}>{field.rule}</div>
      </td>
    </tr>
  )
}
