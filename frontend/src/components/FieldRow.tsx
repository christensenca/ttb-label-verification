import type { components } from '../api/generated'
import InlineDiff from './InlineDiff'
import ConfidenceBadge from './ConfidenceBadge'
import styles from './FieldRow.module.css'

type Field = components['schemas']['FieldRowOut']
type Confidence = Field['confidence']

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
  government_warning_style: 'Bold formatting',
}

const NON_TEXT_FIELDS = new Set(['is_imported', 'government_warning_style'])

// Word-diff highlighting is only meaningful on the long-form government
// warning text — the case where a one-word deviation is easy to miss.
const DIFF_FIELDS = new Set(['government_warning_text'])

export type RowColor = 'green' | 'yellow' | 'red' | 'grey'

/**
 * Tri-state row color per research.md R11 truth table. No longer rendered as
 * a row background; surfaced as a `data-row-state` attribute for testing.
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

function verdictLabel(field: Field): string {
  if (field.effective_verdict === 'not_applicable') return 'N/A'
  if (field.override) {
    return field.override.override_verdict === 'pass'
      ? 'Overridden Pass'
      : 'Overridden Fail'
  }
  return field.effective_verdict === 'pass' ? 'Pass' : 'Fail'
}

function pillClass(field: Field): string {
  if (field.effective_verdict === 'not_applicable') return styles.pillNa
  return field.effective_verdict === 'pass' ? styles.pillPass : styles.pillFail
}

/**
 * Reviewer-friendly detail line under the verdict pill.
 * Only surfaces a fuzzy-match percentage when the backend gave us one.
 * Everything else stays empty — the verdict pill + row label communicate
 * the rest.
 */
function verdictDetail(field: Field): string {
  if (field.effective_verdict === 'not_applicable') return ''
  if (field.rule === 'extraction failed') return 'No extraction'
  const reason = field.reason ?? ''

  const fuzzyOk = reason.match(/fuzzy match \(([\d.]+)\)/)
  if (fuzzyOk) return `${Math.round(Number(fuzzyOk[1]))}% match`

  const fuzzyBelow = reason.match(/below fuzzy threshold \(([\d.]+) < /)
  if (fuzzyBelow) return `${Math.round(Number(fuzzyBelow[1]))}% match`

  return ''
}

function renderBoldFormattingCell(field: Field, side: 'extracted' | 'expected') {
  // Expected is always "true" (we always expect bold header / regular body).
  if (side === 'expected') {
    return <span className={styles.boolTrue}>true</span>
  }
  // Extracted is derived from the verdict — pass = detected correctly.
  if (field.effective_verdict === 'pass') {
    return <span className={styles.boolTrue}>true</span>
  }
  return <span className={styles.boolFalse}>false</span>
}

function renderValue(field: Field, side: 'extracted' | 'expected') {
  if (field.effective_verdict === 'not_applicable') {
    return <span className={styles.notApplicable}>N/A</span>
  }
  if (field.field === 'government_warning_style') {
    return renderBoldFormattingCell(field, side)
  }
  const value = side === 'extracted' ? field.extracted_value : field.expected_value
  const diffTokens =
    side === 'extracted' ? field.diff_extracted : field.diff_expected
  if (
    field.effective_verdict === 'fail' &&
    DIFF_FIELDS.has(field.field) &&
    diffTokens &&
    diffTokens.length > 0
  ) {
    return <InlineDiff tokens={diffTokens} />
  }
  if (value == null || value === '') {
    return <span className={styles.empty}>—</span>
  }
  return <>{value}</>
}

export default function FieldRow({
  field,
  displayConfidence,
}: {
  field: Field
  displayConfidence?: Confidence
}) {
  const label = FIELD_LABELS[field.field] ?? field.field
  const color = rowColorClass(field)
  const isWarningText = field.field === 'government_warning_text'
  const rowClass = [
    styles.row,
    field.effective_verdict === 'not_applicable' ? styles.muted : '',
    field.override ? styles.overridden : '',
    isWarningText ? styles.warningText : '',
  ]
    .filter(Boolean)
    .join(' ')

  const resolvedConfidence =
    displayConfidence !== undefined ? displayConfidence : field.confidence ?? null
  const detail = verdictDetail(field)

  return (
    <tr className={rowClass} data-row-state={color}>
      <td className={styles.cellLabel}>{label}</td>
      <td className={styles.cellValue}>{renderValue(field, 'extracted')}</td>
      <td className={styles.cellValue}>{renderValue(field, 'expected')}</td>
      <td className={styles.cellConfidence}>
        <ConfidenceBadge confidence={resolvedConfidence} />
      </td>
      <td className={styles.cellVerdict}>
        <span className={`${styles.verdictPill} ${pillClass(field)}`}>
          {verdictLabel(field)}
        </span>
        {field.override && (
          <span className={styles.originalVerdict}>
            (model said: {field.override.original_verdict})
          </span>
        )}
        {detail && <div className={styles.detail}>{detail}</div>}
      </td>
    </tr>
  )
}
