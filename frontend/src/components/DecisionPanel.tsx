import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'

import { api, ApiError } from '../api/client'
import type { components } from '../api/generated'

type DecisionIn = components['schemas']['DecisionIn']
type DecisionOut = components['schemas']['DecisionOut']
type ReviewOut = components['schemas']['ReviewOut']
type Status = components['schemas']['SubmissionListItem']['status']

interface Props {
  submissionId: string
  status: Status
  review: ReviewOut | null
  failingComparisonIds: string[]
  onDecided: () => void
}

export default function DecisionPanel({
  submissionId,
  status,
  review,
  failingComparisonIds,
  onDecided,
}: Props) {
  const [comment, setComment] = useState('')
  const [error, setError] = useState<string | null>(null)

  const decisionMutation = useMutation({
    mutationFn: (body: DecisionIn) =>
      api.post<DecisionOut>(`/api/submissions/${submissionId}/decision`, body),
    onSuccess: () => {
      setError(null)
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
    return (
      <section
        className="decision-panel decision-panel--locked"
        style={{
          marginTop: 16,
          padding: 12,
          borderTop: '2px solid #ddd',
          background: '#fafafa',
        }}
      >
        <h3>Decision recorded</h3>
        {review && (
          <>
            <p>
              <strong>{review.decision.toUpperCase()}</strong>
            </p>
            {review.comment && <p>Comment: {review.comment}</p>}
            {review.rejection_field_ids && review.rejection_field_ids.length > 0 && (
              <p>
                Rejection reasons: {review.rejection_field_ids.length} field(s) flagged
              </p>
            )}
          </>
        )}
      </section>
    )
  }

  const canDecide =
    status === 'ready_for_review' || status === 'extraction_failed'
  const canReject = canDecide && failingComparisonIds.length > 0

  return (
    <section
      className="decision-panel"
      style={{ marginTop: 16, padding: 12, borderTop: '2px solid #ddd' }}
    >
      <h3>Decision</h3>
      <label style={{ display: 'block', marginBottom: 8 }}>
        Comment (optional)
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          rows={3}
          style={{ width: '100%', display: 'block', marginTop: 4 }}
          maxLength={2000}
        />
      </label>
      <div style={{ display: 'flex', gap: 8 }}>
        <button
          type="button"
          disabled={!canDecide || decisionMutation.isPending}
          onClick={() =>
            decisionMutation.mutate({
              decision: 'approved',
              comment: comment.trim() || null,
            })
          }
        >
          Approve
        </button>
        <button
          type="button"
          disabled={!canReject || decisionMutation.isPending}
          title={
            canReject
              ? undefined
              : 'no failing fields to reject against'
          }
          onClick={() =>
            decisionMutation.mutate({
              decision: 'rejected',
              comment: comment.trim() || null,
              rejection_field_ids: failingComparisonIds,
            })
          }
        >
          Reject ({failingComparisonIds.length})
        </button>
      </div>
      {error && (
        <p className="error" style={{ color: '#c62828', marginTop: 8 }}>
          {error}
        </p>
      )}
    </section>
  )
}
