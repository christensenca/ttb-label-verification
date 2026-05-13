import { useEffect } from 'react'

import styles from './DecisionPanel.module.css'

export interface FailingFieldRef {
  id: string
  label: string
}

interface Props {
  failingFields: FailingFieldRef[]
  onConfirm: () => void
  onCancel: () => void
  pending?: boolean
}

export default function ApproveConfirmationModal({
  failingFields,
  onConfirm,
  onCancel,
  pending = false,
}: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !pending) onCancel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onCancel, pending])

  const count = failingFields.length
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="approve-confirm-heading"
      className={styles.modalBackdrop}
      onClick={(e) => {
        if (e.target === e.currentTarget && !pending) onCancel()
      }}
    >
      <div className={styles.modal}>
        <h3 id="approve-confirm-heading" className={styles.modalHeading}>
          Approve with {count} failing field{count === 1 ? '' : 's'}?
        </h3>
        <p className={styles.modalBody}>
          The following field{count === 1 ? '' : 's'} still{' '}
          {count === 1 ? 'has' : 'have'} an effective verdict of{' '}
          <strong>fail</strong>. Approving will record the decision anyway.
        </p>
        <ul className={styles.modalList}>
          {failingFields.map((f) => (
            <li key={f.id}>{f.label}</li>
          ))}
        </ul>
        <div className={styles.modalActions}>
          <button
            type="button"
            className={styles.button}
            onClick={onCancel}
            disabled={pending}
          >
            Cancel
          </button>
          <button
            type="button"
            className={`${styles.button} ${styles.primary}`}
            onClick={onConfirm}
            disabled={pending}
          >
            Approve anyway
          </button>
        </div>
      </div>
    </div>
  )
}
