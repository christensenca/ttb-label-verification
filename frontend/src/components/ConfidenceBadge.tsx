import type { components } from '../api/generated'
import styles from './FieldRow.module.css'

type Confidence = components['schemas']['FieldRowOut']['confidence']

const CLASS: Record<NonNullable<Confidence>, string> = {
  hi: styles.confHi,
  med: styles.confMed,
  low: styles.confLow,
}

const LABEL: Record<NonNullable<Confidence>, string> = {
  hi: 'High',
  med: 'Med',
  low: 'Low',
}

export default function ConfidenceBadge({
  confidence,
}: {
  confidence: Confidence
}) {
  if (confidence == null) {
    return <span className={styles.confNone}>—</span>
  }
  return (
    <span className={`${styles.confChip} ${CLASS[confidence]}`}>
      {LABEL[confidence]}
    </span>
  )
}
