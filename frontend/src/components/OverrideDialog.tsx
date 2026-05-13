import { useEffect, useState } from 'react'
import { useMutation } from '@tanstack/react-query'

import { api, ApiError } from '../api/client'
import type { components } from '../api/generated'
import styles from './OverrideDialog.module.css'

type OverrideOut = components['schemas']['OverrideOut']
type OverrideIn = components['schemas']['OverrideIn']

interface Props {
  submissionId: string
  field: string
  fieldLabel: string
  modelVerdict: 'pass' | 'fail' | 'not_applicable'
  currentOverride: OverrideOut | null
  onClose: () => void
  onSaved: () => void
}

export default function OverrideDialog({
  submissionId,
  field,
  fieldLabel,
  modelVerdict,
  currentOverride,
  onClose,
  onSaved,
}: Props) {
  const [comment, setComment] = useState(currentOverride?.comment ?? '')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const onMutationError = (err: unknown) => {
    if (err instanceof ApiError) setError(err.message)
    else setError(String(err))
  }

  const saveMutation = useMutation({
    mutationFn: (body: OverrideIn) =>
      api.post<OverrideOut>(`/api/submissions/${submissionId}/overrides`, body),
    onSuccess: () => {
      setError(null)
      onSaved()
    },
    onError: onMutationError,
  })

  const revertMutation = useMutation({
    mutationFn: () =>
      api.del<void>(`/api/submissions/${submissionId}/overrides/${field}`),
    onSuccess: () => {
      setError(null)
      onSaved()
    },
    onError: onMutationError,
  })

  const pending = saveMutation.isPending || revertMutation.isPending

  const submit = (verdict: 'pass' | 'fail') => {
    saveMutation.mutate({
      field,
      override_verdict: verdict,
      comment: comment.trim(),
    })
  }

  return (
    <div
      className={styles.backdrop}
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={`Override ${fieldLabel}`}
    >
      <div className={styles.dialog} onClick={(e) => e.stopPropagation()}>
        <h3 className={styles.heading}>Override "{fieldLabel}"</h3>
        <p className={styles.modelSays}>
          Model verdict: <strong>{modelVerdict}</strong>
          {currentOverride && (
            <>
              {' '}
              · current override:{' '}
              <strong>{currentOverride.override_verdict}</strong>
            </>
          )}
        </p>
        <div>
          <label className={styles.label} htmlFor="override-comment">
            Reason (optional)
          </label>
          <textarea
            id="override-comment"
            className={styles.textarea}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            maxLength={2000}
            placeholder="Optional note for the audit trail."
            autoFocus
          />
        </div>
        {error && <p className={styles.error}>{error}</p>}
        <div className={styles.actions}>
          {currentOverride && (
            <button
              type="button"
              className={`${styles.button} ${styles.revertButton}`}
              onClick={() => revertMutation.mutate()}
              disabled={pending}
              title="Delete the override and use the model's original verdict."
            >
              Revert to model verdict
            </button>
          )}
          <span className={styles.actionsSpacer} />
          <button
            type="button"
            className={styles.button}
            onClick={onClose}
            disabled={pending}
          >
            Cancel
          </button>
          <button
            type="button"
            className={`${styles.button} ${styles.failButton}`}
            onClick={() => submit('fail')}
            disabled={pending}
          >
            Mark Fail
          </button>
          <button
            type="button"
            className={`${styles.button} ${styles.passButton}`}
            onClick={() => submit('pass')}
            disabled={pending}
          >
            Mark Pass
          </button>
        </div>
      </div>
    </div>
  )
}
