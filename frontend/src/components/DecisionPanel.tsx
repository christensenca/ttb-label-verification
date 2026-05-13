import { useMutation } from '@tanstack/react-query'
import { useMemo, useState } from 'react'

import { api, ApiError } from '../api/client'
import type { components } from '../api/generated'
import ApproveConfirmationModal from './ApproveConfirmationModal'
import styles from './DecisionPanel.module.css'

type DecisionIn = components['schemas']['DecisionIn']
type DecisionOut = components['schemas']['DecisionOut']
type ReviewOut = components['schemas']['ReviewOut']
type Status = components['schemas']['SubmissionListItem']['status']

export interface RejectionCandidate {
  id: string
  field: string
  label: string
  isFailing: boolean
}

interface Props {
  submissionId: string
  status: Status
  review: ReviewOut | null
  /** Every comparison row on the submission, in display order. The reviewer
   * may tick any of them; failing fields are pre-selected when the reject
   * panel opens. */
  candidates: RejectionCandidate[]
  /** id → display label for any comparison row, used to surface persisted
   * rejection reasons. */
  fieldLabelById: Record<string, string>
  onDecided: () => void
}

export default function DecisionPanel({
  submissionId,
  status,
  review,
  candidates,
  fieldLabelById,
  onDecided,
}: Props) {
  const [comment, setComment] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [showRejectPanel, setShowRejectPanel] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [showApproveModal, setShowApproveModal] = useState(false)

  const failingFields = useMemo(
    () => candidates.filter((c) => c.isFailing),
    [candidates],
  )

  const decisionMutation = useMutation({
    mutationFn: (body: DecisionIn) =>
      api.post<DecisionOut>(`/api/submissions/${submissionId}/decision`, body),
    onSuccess: () => {
      setError(null)
      setShowRejectPanel(false)
      setShowApproveModal(false)
      onDecided()
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setError(err.message)
      } else {
        setError(String(err))
      }
    },
  })

  if (review || status === 'approved' || status === 'rejected') {
    const reasonIds = review?.rejection_field_ids ?? []
    const reasonLabels = reasonIds.map(
      (id) => fieldLabelById[id] ?? `field ${id.slice(0, 6)}`,
    )
    const isApproved = review?.decision === 'approved'
    return (
      <section className={`${styles.section} ${styles.locked}`}>
        <h3 className={styles.heading}>Decision recorded</h3>
        <div className={styles.body}>
          {review && (
            <>
              <div className={styles.lockedDecision}>
                <span
                  className={`${styles.decisionPill} ${
                    isApproved
                      ? styles.decisionApproved
                      : styles.decisionRejected
                  }`}
                >
                  {review.decision}
                </span>
              </div>
              {review.comment && (
                <p className={styles.lockedComment}>
                  <span className={styles.lockedCommentLabel}>Comment</span>
                  {review.comment}
                </p>
              )}
              {reasonLabels.length > 0 && (
                <div>
                  <span className={styles.lockedCommentLabel}>
                    Rejection reasons
                  </span>
                  <ul className={styles.reasonList}>
                    {reasonLabels.map((label, i) => (
                      <li key={reasonIds[i]}>{label}</li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>
      </section>
    )
  }

  const canDecide =
    status === 'ready_for_review' || status === 'extraction_failed'
  const hasAnyFailing = failingFields.length > 0

  const toggle = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const submitReject = () => {
    decisionMutation.mutate({
      decision: 'rejected',
      comment: comment.trim() || null,
      rejection_field_ids: Array.from(selectedIds),
    })
  }

  const onApproveClick = () => {
    if (hasAnyFailing) {
      setShowApproveModal(true)
    } else {
      decisionMutation.mutate({
        decision: 'approved',
        comment: comment.trim() || null,
      })
    }
  }

  return (
    <section className={styles.section}>
      <h3 className={styles.heading}>Decision</h3>
      <div className={styles.body}>
        <div>
          <label className={styles.label} htmlFor="decision-comment">
            Comment (optional)
          </label>
          <textarea
            id="decision-comment"
            className={styles.textarea}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            maxLength={2000}
          />
        </div>

        {!showRejectPanel && (
          <div className={styles.actions}>
            <button
              type="button"
              className={`${styles.button} ${styles.primary}`}
              disabled={!canDecide || decisionMutation.isPending}
              onClick={onApproveClick}
            >
              Approve
            </button>
            <button
              type="button"
              className={`${styles.button} ${styles.danger}`}
              disabled={
                !canDecide ||
                candidates.length === 0 ||
                decisionMutation.isPending
              }
              title={
                candidates.length === 0
                  ? 'no fields available'
                  : undefined
              }
              onClick={() => {
                setSelectedIds(new Set(failingFields.map((f) => f.id)))
                setShowRejectPanel(true)
              }}
            >
              Reject{hasAnyFailing ? ` (${failingFields.length})` : ''}
            </button>
          </div>
        )}

        {showRejectPanel && (
          <div className={styles.rejectPanel}>
            <div className={styles.rejectHeader}>
              <h4 className={styles.rejectTitle}>Select rejection reasons</h4>
              <p className={styles.rejectHint}>
                Failing fields are pre-selected. Tick or untick any field — the
                reviewer's judgment is final. At least one reason is required.
              </p>
            </div>
            <ul className={styles.candidateList}>
              {candidates.map((f) => (
                <li key={f.id} className={styles.candidateItem}>
                  <label className={styles.candidateLabel}>
                    <input
                      type="checkbox"
                      checked={selectedIds.has(f.id)}
                      onChange={() => toggle(f.id)}
                    />
                    <span>{f.label}</span>
                    {f.isFailing && (
                      <span className={styles.failingBadge}>Failing</span>
                    )}
                  </label>
                </li>
              ))}
            </ul>
            <div className={styles.actions}>
              <button
                type="button"
                className={`${styles.button} ${styles.dangerSolid}`}
                disabled={
                  selectedIds.size === 0 || decisionMutation.isPending
                }
                onClick={submitReject}
              >
                Submit rejection
              </button>
              <button
                type="button"
                className={styles.button}
                onClick={() => {
                  setShowRejectPanel(false)
                  setSelectedIds(new Set())
                }}
                disabled={decisionMutation.isPending}
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {error && <p className={styles.error}>{error}</p>}
      </div>

      {showApproveModal && (
        <ApproveConfirmationModal
          failingFields={failingFields.map((f) => ({
            id: f.id,
            label: f.label,
          }))}
          pending={decisionMutation.isPending}
          onCancel={() => setShowApproveModal(false)}
          onConfirm={() =>
            decisionMutation.mutate({
              decision: 'approved',
              comment: comment.trim() || null,
            })
          }
        />
      )}
    </section>
  )
}
