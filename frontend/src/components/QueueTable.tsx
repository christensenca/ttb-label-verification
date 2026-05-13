import { Link } from 'react-router-dom'

import type { components } from '../api/generated'
import styles from './QueueTable.module.css'

type SubmissionListItem = components['schemas']['SubmissionListItem']
type Status = SubmissionListItem['status']

export const STATUS_LABEL: Record<Status, string> = {
  loaded: 'Loaded',
  processing: 'Processing',
  ready_for_review: 'Ready for Review',
  approved: 'Approved',
  rejected: 'Rejected',
  extraction_failed: 'Extraction Failed',
}

const STATUS_COLOR: Record<Status, string> = {
  loaded: '#cfd8dc',
  processing: '#bbdefb',
  ready_for_review: '#fff59d',
  approved: '#c8e6c9',
  rejected: '#ffcdd2',
  extraction_failed: '#ef9a9a',
}

function StatusPill({ status }: { status: Status }) {
  return (
    <span
      className={styles.statusPill}
      style={{ background: STATUS_COLOR[status] }}
    >
      {STATUS_LABEL[status]}
    </span>
  )
}

export default function QueueTable({ items }: { items: SubmissionListItem[] }) {
  if (items.length === 0) {
    return <p>No submissions yet.</p>
  }
  return (
    <table className={styles.table}>
      <colgroup>
        <col className={styles.colThumb} />
        <col className={styles.colBrand} />
        <col className={styles.colSource} />
        <col className={styles.colStatus} />
        <col className={styles.colAction} />
      </colgroup>
      <thead>
        <tr className={styles.headerRow}>
          <th>Thumb</th>
          <th>Brand</th>
          <th>Source</th>
          <th>Status</th>
          <th aria-label="Action" />
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.id} id={`queue-row-${item.id}`} className={styles.row}>
            <td>
              <img
                src={item.thumbnail_url}
                alt={item.brand}
                className={styles.thumb}
                onError={(e) => {
                  e.currentTarget.style.visibility = 'hidden'
                }}
              />
            </td>
            <td>{item.brand}</td>
            <td>{item.is_fixture ? 'Fixture' : 'User'}</td>
            <td>
              <StatusPill status={item.status} />
            </td>
            <td className={styles.action}>
              <Link to={`/items/${item.id}`}>Open →</Link>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
