import { useState } from 'react'

import type { components } from '../api/generated'
import InlineDiff from './InlineDiff'
import ConfidenceBadge from './ConfidenceBadge'
import OverrideDialog from './OverrideDialog'
import { rowColorClass } from './fieldRowState'
import styles from './FieldRow.module.css'

type Field = components['schemas']['FieldRowOut']
type Confidence = Field['confidence']
type Status = components['schemas']['SubmissionListItem']['status']

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

// Word-diff highlighting is only meaningful on the long-form government
// warning text — the case where a one-word deviation is easy to miss.
const DIFF_FIELDS = new Set(['government_warning_text'])

function capitalize(v: string): string {
  return v.charAt(0).toUpperCase() + v.slice(1)
}

function verdictLabel(field: Field): string {
  if (field.effective_verdict === 'not_applicable') return 'N/A'
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
    return <>true</>
  }
  // Extracted is derived from the verdict — pass = detected correctly.
  return <>{field.effective_verdict === 'pass' ? 'true' : 'false'}</>
}

function renderValue(field: Field, side: 'extracted' | 'expected') {
  if (field.effective_verdict === 'not_applicable') {
    return <span className={styles.notApplicable}>N/A</span>
  }
  if (field.field === 'government_warning_style') {
    return renderBoldFormattingCell(field, side)
  }
  // Domestic submissions: the model often misreads producer city/state as
  // country of origin (e.g. "Long Beach, CA"). The comparator tolerates it
  // and the verdict passes, but the leaked text in the extracted cell is
  // confusing. When there's no expected country, blank the row entirely.
  if (
    field.field === 'country_of_origin' &&
    (field.expected_value == null || field.expected_value === '')
  ) {
    return <span className={styles.empty}>—</span>
  }
  const value = side === 'extracted' ? field.extracted_value : field.expected_value
  if (
    side === 'extracted' &&
    field.effective_verdict === 'fail' &&
    DIFF_FIELDS.has(field.field) &&
    field.diff_extracted &&
    field.diff_extracted.length > 0
  ) {
    return <InlineDiff tokens={field.diff_extracted} />
  }
  if (value == null || value === '') {
    return <span className={styles.empty}>—</span>
  }
  return <>{value}</>
}

interface Props {
  field: Field
  submissionId: string
  status: Status
  displayConfidence?: Confidence
  onOpenImage: () => void
  onOverrideChanged: () => void
}

export default function FieldRow({
  field,
  submissionId,
  status,
  displayConfidence,
  onOpenImage,
  onOverrideChanged,
}: Props) {
  const [showOverrideDialog, setShowOverrideDialog] = useState(false)
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

  const canOverride =
    (status === 'ready_for_review' || status === 'extraction_failed') &&
    field.effective_verdict !== 'not_applicable'

  return (
    <>
      <tr className={rowClass} data-row-state={color}>
        <td className={styles.cellLabel}>{label}</td>
        <td className={styles.cellValue}>{renderValue(field, 'extracted')}</td>
        <td className={styles.cellValue}>{renderValue(field, 'expected')}</td>
        <td className={styles.cellConfidence}>
          <ConfidenceBadge confidence={resolvedConfidence} />
        </td>
        <td className={styles.cellVerdict}>
          <span className={`${styles.verdictPill} ${pillClass(field)}`}>
            {field.override && field.effective_verdict !== 'not_applicable' ? (
              <>
                <span className={styles.pillModelVerdict}>
                  {capitalize(field.override.original_verdict)}
                </span>
                <span className={styles.pillArrow} aria-hidden="true">
                  {' → '}
                </span>
                {verdictLabel(field)}
              </>
            ) : (
              verdictLabel(field)
            )}
          </span>
          {detail && <div className={styles.detail}>{detail}</div>}
        </td>
        <td className={styles.cellActions}>
          <button
            type="button"
            className={styles.linkButton}
            onClick={onOpenImage}
          >
            View image
          </button>
          {canOverride && (
            <button
              type="button"
              className={styles.linkButton}
              onClick={() => setShowOverrideDialog(true)}
            >
              Override
            </button>
          )}
        </td>
      </tr>
      {showOverrideDialog && (
        <OverrideDialog
          submissionId={submissionId}
          field={field.field}
          fieldLabel={label}
          modelVerdict={field.model_verdict}
          currentOverride={field.override ?? null}
          onClose={() => setShowOverrideDialog(false)}
          onSaved={() => {
            setShowOverrideDialog(false)
            onOverrideChanged()
          }}
        />
      )}
    </>
  )
}
