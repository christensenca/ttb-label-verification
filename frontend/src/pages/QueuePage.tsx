import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '../api/client'
import type { components } from '../api/generated'
import AddSubmissionForm from '../components/AddSubmissionForm'
import QueueTable from '../components/QueueTable'

type SubmissionListItem = components['schemas']['SubmissionListItem']
type StartOut = components['schemas']['StartOut']

const QUEUE_KEY = ['queue'] as const

export default function QueuePage() {
  const queryClient = useQueryClient()
  const [isAddOpen, setIsAddOpen] = useState(false)

  const queueQuery = useQuery<SubmissionListItem[]>({
    queryKey: QUEUE_KEY,
    queryFn: () => api.get<SubmissionListItem[]>('/api/submissions'),
    refetchInterval: (q) => {
      const items = (q.state.data as SubmissionListItem[] | undefined) ?? []
      return items.some((i) => i.status === 'processing') ? 1500 : false
    },
  })

  const startMutation = useMutation({
    mutationFn: () => api.post<StartOut>('/api/submissions/start'),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: QUEUE_KEY }),
  })

  const items = queueQuery.data ?? []
  const loadedCount = items.filter((i) => i.status === 'loaded').length
  const processingCount = items.filter((i) => i.status === 'processing').length

  return (
    <section className="queue-page">
      <div className="queue-header">
        <h2>Queue</h2>
        <div className="queue-actions">
          <button
            type="button"
            className="add-button"
            onClick={() => setIsAddOpen((v) => !v)}
            aria-expanded={isAddOpen}
          >
            {isAddOpen ? 'Cancel' : 'Add my own…'}
          </button>
          <button
            type="button"
            className="start-button"
            disabled={loadedCount === 0 || startMutation.isPending}
            onClick={() => startMutation.mutate()}
          >
            {startMutation.isPending
              ? 'Starting…'
              : loadedCount > 0
                ? `Start (${loadedCount})`
                : 'Start'}
          </button>
          {processingCount > 0 && (
            <span className="queue-status">{processingCount} processing…</span>
          )}
        </div>
      </div>
      {isAddOpen && (
        <AddSubmissionForm
          onAdded={() => queryClient.invalidateQueries({ queryKey: QUEUE_KEY })}
          onDismiss={() => setIsAddOpen(false)}
        />
      )}
      {queueQuery.isLoading && <p>Loading queue…</p>}
      {queueQuery.isError && (
        <p className="error">Failed to load queue: {String(queueQuery.error)}</p>
      )}
      {queueQuery.isSuccess && <QueueTable items={items} />}
    </section>
  )
}
