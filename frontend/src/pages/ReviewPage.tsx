import { useMemo } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '../api/client'
import type { components } from '../api/generated'
import DecisionPanel from '../components/DecisionPanel'
import ExtractionFailedBanner from '../components/ExtractionFailedBanner'
import FieldGroup from '../components/FieldGroup'
import { STATUS_LABEL } from '../components/QueueTable'

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
      <header
        style={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          marginBottom: 12,
        }}
      >
        <h2 style={{ margin: 0 }}>{detail.expected_values.brand}</h2>
        <span style={{ color: '#666', fontSize: 13 }}>
          Status: <strong>{STATUS_LABEL[detail.status]}</strong>
        </span>
      </header>
      <figure
        style={{
          margin: '0 0 20px',
          display: 'flex',
          justifyContent: 'center',
          background: '#fafafa',
          border: '1px solid #ddd',
          borderRadius: 4,
          padding: 12,
        }}
      >
        <img
          src={detail.image_url}
          alt={detail.expected_values.brand}
          style={{
            maxWidth: '100%',
            maxHeight: 380,
            objectFit: 'contain',
            borderRadius: 2,
          }}
        />
      </figure>
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
    </section>
  )
}
