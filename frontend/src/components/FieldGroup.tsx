import type { components } from '../api/generated'
import FieldRow from './FieldRow'
import styles from './FieldGroup.module.css'

type Group = components['schemas']['FieldGroupOut']
type FieldOut = components['schemas']['FieldRowOut']
type Confidence = FieldOut['confidence']
type Status = components['schemas']['SubmissionListItem']['status']

/**
 * `is_imported` and `government_warning_style` are not extracted as
 * standalone text fields, so the extractor reports `confidence: null`
 * for them. They sit alongside fields that *are* scored
 * (country_of_origin / government_warning_text respectively), so we
 * surface the sibling's confidence to the reviewer.
 */
const INHERITS_FROM: Record<string, string> = {
  is_imported: 'country_of_origin',
  government_warning_style: 'government_warning_text',
}

function effectiveConfidence(
  field: FieldOut,
  byName: Record<string, FieldOut>,
): Confidence {
  if (field.confidence != null) return field.confidence
  const source = INHERITS_FROM[field.field]
  if (source && byName[source]) return byName[source].confidence ?? null
  return null
}

interface Props {
  group: Group
  submissionId: string
  status: Status
  onOpenImage: () => void
  onOverrideChanged: () => void
}

export default function FieldGroup({
  group,
  submissionId,
  status,
  onOpenImage,
  onOverrideChanged,
}: Props) {
  const byName = Object.fromEntries(group.fields.map((f) => [f.field, f]))
  return (
    <section className={styles.group}>
      <h3 className={styles.heading}>{group.name}</h3>
      <table className={styles.table}>
        <colgroup>
          <col className={styles.colField} />
          <col className={styles.colExtracted} />
          <col className={styles.colExpected} />
          <col className={styles.colConfidence} />
          <col className={styles.colVerdict} />
          <col className={styles.colActions} />
        </colgroup>
        <thead>
          <tr className={styles.headerRow}>
            <th>Field</th>
            <th>Extracted</th>
            <th>Expected</th>
            <th>Confidence</th>
            <th>Verdict</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {group.fields.map((f) => (
            <FieldRow
              key={f.id}
              field={f}
              submissionId={submissionId}
              status={status}
              displayConfidence={effectiveConfidence(f, byName)}
              onOpenImage={onOpenImage}
              onOverrideChanged={onOverrideChanged}
            />
          ))}
        </tbody>
      </table>
    </section>
  )
}
