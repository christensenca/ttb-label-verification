import { useEffect, useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { api } from '../api/client'
import type { components } from '../api/generated'
import styles from './ReviewToolbar.module.css'

type SubmissionListItem = components['schemas']['SubmissionListItem']

export default function ReviewToolbar({ currentId }: { currentId: string }) {
  const navigate = useNavigate()

  const queueQuery = useQuery<SubmissionListItem[]>({
    queryKey: ['queue'],
    queryFn: () => api.get<SubmissionListItem[]>('/api/submissions'),
  })

  const { index, prevId, nextId, total } = useMemo(() => {
    const items = queueQuery.data ?? []
    const idx = items.findIndex((i) => i.id === currentId)
    return {
      index: idx,
      prevId: idx > 0 ? items[idx - 1].id : undefined,
      nextId: idx >= 0 && idx < items.length - 1 ? items[idx + 1].id : undefined,
      total: items.length,
    }
  }, [queueQuery.data, currentId])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
      const t = document.activeElement
      if (t) {
        const tag = t.tagName
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
        if ((t as HTMLElement).isContentEditable) return
      }
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const target = e.key === 'ArrowLeft' ? prevId : nextId
      if (!target) return
      e.preventDefault()
      navigate(`/items/${target}`, { state: { focusId: target } })
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [prevId, nextId, navigate])

  const position = index >= 0 ? index + 1 : null

  return (
    <nav className={styles.toolbar} aria-label="Review navigation">
      <div className={styles.left}>
        <Link
          to="/"
          state={{ focusId: currentId }}
          className={`${styles.btn} ${styles.back}`}
        >
          ← Back to queue
        </Link>
      </div>
      <div className={styles.right}>
        {prevId ? (
          <Link
            to={`/items/${prevId}`}
            state={{ focusId: prevId }}
            className={styles.btn}
            aria-label="Previous item"
          >
            ← Prev
          </Link>
        ) : (
          <button type="button" className={styles.btn} disabled aria-label="Previous item">
            ← Prev
          </button>
        )}
        <span className={styles.counter}>
          {position && total ? `Item ${position} of ${total}` : '—'}
        </span>
        {nextId ? (
          <Link
            to={`/items/${nextId}`}
            state={{ focusId: nextId }}
            className={styles.btn}
            aria-label="Next item"
          >
            Next →
          </Link>
        ) : (
          <button type="button" className={styles.btn} disabled aria-label="Next item">
            Next →
          </button>
        )}
      </div>
    </nav>
  )
}
