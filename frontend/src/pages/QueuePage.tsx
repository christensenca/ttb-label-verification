import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '../api/client'
import type { components } from '../api/generated'
import AddSubmissionForm from '../components/AddSubmissionForm'
import QueueTable from '../components/QueueTable'
import styles from './QueuePage.module.css'

type SubmissionListItem = components['schemas']['SubmissionListItem']
type StartOut = components['schemas']['StartOut']

const QUEUE_KEY = ['queue'] as const

export default function QueuePage() {
  const queryClient = useQueryClient()

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
    <div className={styles.page}>
      <section className={styles.card}>
        <div className={styles.cardHeader}>
          <div className={styles.cardHeaderText}>
            <h2>Add submissions</h2>
            <span className={styles.cardSubtitle}>
              Upload a single label with expected values, or batch-upload a CSV
              manifest with matching images.
            </span>
          </div>
        </div>
        <AddSubmissionForm
          onAdded={() => queryClient.invalidateQueries({ queryKey: QUEUE_KEY })}
        />
      </section>

      <section className={styles.card}>
        <div className={styles.cardHeader}>
          <div className={styles.cardHeaderText}>
            <h2>Queue</h2>
            <span className={styles.cardSubtitle}>
              {loadedCount > 0
                ? `${loadedCount} item${loadedCount === 1 ? '' : 's'} ready to run`
                : 'No items waiting to run'}
            </span>
          </div>
          <div className={styles.cardActions}>
            {processingCount > 0 && (
              <span className={styles.statusNote}>
                {processingCount} processing…
              </span>
            )}
            <button
              type="button"
              className={styles.startButton}
              disabled={loadedCount === 0 || startMutation.isPending}
              onClick={() => startMutation.mutate()}
            >
              {startMutation.isPending
                ? 'Running…'
                : loadedCount > 0
                  ? `Run ${loadedCount}`
                  : 'Run'}
            </button>
          </div>
        </div>
        {queueQuery.isLoading && (
          <div className={styles.queueState}>Loading queue…</div>
        )}
        {queueQuery.isError && (
          <div className={`${styles.queueState} ${styles.error}`}>
            Failed to load queue: {String(queueQuery.error)}
          </div>
        )}
        {queueQuery.isSuccess && <QueueTable items={items} />}
      </section>
    </div>
  )
}
