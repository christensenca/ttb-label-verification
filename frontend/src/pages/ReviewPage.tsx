import { useMemo } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '../api/client'
import type { components } from '../api/generated'
import DecisionPanel from '../components/DecisionPanel'
import ExtractionFailedBanner from '../components/ExtractionFailedBanner'
import FieldGroup from '../components/FieldGroup'

type Detail = components['schemas']['SubmissionDetailOut']

export default function ReviewPage() {
  const { id } = useParams<{ id: string }>()
  const queryClient = useQueryClient()

  const detailQuery = useQuery<Detail>({
    queryKey: ['submission', id],
    queryFn: () => api.get<Detail>(`/api/submissions/${id}`),
    refetchInterval: (q) => {
      const data = q.state.data as Detail | undefined
      return data && (data.status === 'processing' || data.status === 'loaded')
        ? 1500
        : false
    },
    enabled: Boolean(id),
  })

  const detail = detailQuery.data

  const failingComparisonIds = useMemo<string[]>(() => {
    if (!detail) return []
    const ids: string[] = []
    for (const group of detail.groups ?? []) {
      for (const f of group.fields) {
        if (f.effective_verdict === 'fail') {
          ids.push(f.id)
        }
      }
    }
    return ids
  }, [detail])

  if (!id) return <p>Missing submission id.</p>
  if (detailQuery.isLoading) return <p>Loading…</p>
  if (detailQuery.isError) {
    return (
      <p className="error">
        Failed to load submission: {String(detailQuery.error)}
      </p>
    )
  }
  if (!detail) return null

  const stillProcessing =
    detail.status === 'loaded' || detail.status === 'processing'

  return (
    <section className="review-page">
      <p>
        <Link to="/">← Back to queue</Link>
      </p>
      {detail.extraction?.error && (
        <ExtractionFailedBanner error={detail.extraction.error} />
      )}
      <div
        className="review-layout"
        style={{ display: 'grid', gridTemplateColumns: '1fr 1.4fr', gap: 24 }}
      >
        <aside className="image-pane">
          <img
            src={detail.image_url}
            alt={detail.expected_values.brand}
            style={{
              maxWidth: '100%',
              border: '1px solid #ccc',
              borderRadius: 4,
            }}
          />
          <h3 style={{ marginTop: 12 }}>{detail.expected_values.brand}</h3>
          <p style={{ color: '#666', fontSize: 13 }}>
            Status: <strong>{detail.status}</strong>
          </p>
        </aside>
        <div className="fields-pane">
          {stillProcessing && (
            <p>This submission is still processing. Polling for updates…</p>
          )}
          {!stillProcessing &&
            (detail.groups ?? []).map((g) => (
              <FieldGroup key={g.name} group={g} />
            ))}
          {!stillProcessing && (
            <DecisionPanel
              submissionId={detail.id}
              status={detail.status}
              review={detail.review ?? null}
              failingComparisonIds={failingComparisonIds}
              onDecided={() => {
                queryClient.invalidateQueries({ queryKey: ['submission', id] })
                queryClient.invalidateQueries({ queryKey: ['queue'] })
              }}
            />
          )}
        </div>
      </div>
    </section>
  )
}
