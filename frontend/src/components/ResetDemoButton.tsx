import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api } from '../api/client'
import type { components } from '../api/generated'
import styles from './DecisionPanel.module.css'

type AdminResetOut = components['schemas']['AdminResetOut']

export default function ResetDemoButton() {
  const queryClient = useQueryClient()
  const [confirming, setConfirming] = useState(false)

  const resetMutation = useMutation({
    mutationFn: () =>
      api.post<AdminResetOut>('/api/admin/reset', { confirm: true }),
    onSuccess: () => {
      setConfirming(false)
      queryClient.invalidateQueries()
    },
  })

  useEffect(() => {
    if (!confirming) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !resetMutation.isPending) setConfirming(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [confirming, resetMutation.isPending])

  return (
    <>
      <button
        type="button"
        className={`${styles.button} ${styles.danger}`}
        onClick={() => setConfirming(true)}
        disabled={resetMutation.isPending}
      >
        Reset demo
      </button>
      {resetMutation.isError && (
        <span className={styles.error}>
          {(resetMutation.error as Error)?.message ?? 'Reset failed'}
        </span>
      )}
      {confirming && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="reset-demo-heading"
          className={styles.modalBackdrop}
          onClick={(e) => {
            if (e.target === e.currentTarget && !resetMutation.isPending) {
              setConfirming(false)
            }
          }}
        >
          <div className={styles.modal}>
            <h3 id="reset-demo-heading" className={styles.modalHeading}>
              Reset the shared demo?
            </h3>
            <p className={styles.modalBody}>
              This will permanently delete every user-added submission and
              clear all review decisions. The original fixture items will be
              restored to the queue as <strong>Loaded</strong>. This action
              cannot be undone.
            </p>
            <div className={styles.modalActions}>
              <button
                type="button"
                className={styles.button}
                onClick={() => setConfirming(false)}
                disabled={resetMutation.isPending}
              >
                Cancel
              </button>
              <button
                type="button"
                className={`${styles.button} ${styles.dangerSolid}`}
                onClick={() => resetMutation.mutate()}
                disabled={resetMutation.isPending}
              >
                {resetMutation.isPending ? 'Resetting…' : 'Reset demo'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
