import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '../api/client'
import type { components } from '../api/generated'
import DecisionPanel, { type RejectionCandidate } from '../components/DecisionPanel'
import ExtractionFailedBanner from '../components/ExtractionFailedBanner'
import FieldGroup from '../components/FieldGroup'
import ImageLightbox from '../components/ImageLightbox'
import { STATUS_LABEL } from '../components/QueueTable'
import ReviewToolbar from '../components/ReviewToolbar'

type Detail = components['schemas']['SubmissionDetailOut']

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

export default function ReviewPage() {
  const { id } = useParams<{ id: string }>()
  const queryClient = useQueryClient()
  const [lightboxOpen, setLightboxOpen] = useState(false)

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

  const candidates = useMemo<RejectionCandidate[]>(() => {
    if (!detail) return []
    const out: RejectionCandidate[] = []
    for (const group of detail.groups ?? []) {
      for (const f of group.fields) {
        // not_applicable rows aren't reviewable — drop them from the picker.
        if (f.effective_verdict === 'not_applicable') continue
        out.push({
          id: f.id,
          field: f.field,
          label: FIELD_LABELS[f.field] ?? f.field,
          isFailing: f.effective_verdict === 'fail',
        })
      }
    }
    return out
  }, [detail])

  const fieldLabelById = useMemo<Record<string, string>>(() => {
    if (!detail) return {}
    const map: Record<string, string> = {}
    for (const group of detail.groups ?? []) {
      for (const f of group.fields) {
        map[f.id] = FIELD_LABELS[f.field] ?? f.field
      }
    }
    return map
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
      <ReviewToolbar currentId={detail.id} />
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
          flexDirection: 'column',
          alignItems: 'center',
          background: '#fafafa',
          border: '1px solid #ddd',
          borderRadius: 4,
          padding: 12,
        }}
      >
        <button
          type="button"
          onClick={() => setLightboxOpen(true)}
          style={{
            border: 'none',
            background: 'transparent',
            padding: 0,
            cursor: 'zoom-in',
          }}
          title="Open at readable size"
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
        </button>
        <span style={{ fontSize: 12, color: '#666', marginTop: 6 }}>
          Click image to enlarge
        </span>
      </figure>
      <div className="fields-pane">
        {stillProcessing && (
          <p>This submission is still processing. Polling for updates…</p>
        )}
        {!stillProcessing &&
          (detail.groups ?? []).map((g) => (
            <FieldGroup
              key={g.name}
              group={g}
              submissionId={detail.id}
              status={detail.status}
              onOpenImage={() => setLightboxOpen(true)}
              onOverrideChanged={() =>
                queryClient.invalidateQueries({ queryKey: ['submission', id] })
              }
            />
          ))}
        {!stillProcessing && (
          <DecisionPanel
            submissionId={detail.id}
            status={detail.status}
            review={detail.review ?? null}
            candidates={candidates}
            fieldLabelById={fieldLabelById}
            onDecided={() => {
              queryClient.invalidateQueries({ queryKey: ['submission', id] })
              queryClient.invalidateQueries({ queryKey: ['queue'] })
            }}
          />
        )}
      </div>
      {lightboxOpen && (
        <ImageLightbox
          src={detail.image_url}
          alt={detail.expected_values.brand}
          caption={detail.expected_values.brand}
          onClose={() => setLightboxOpen(false)}
        />
      )}
    </section>
  )
}
