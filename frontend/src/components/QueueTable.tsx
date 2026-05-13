import { Link } from 'react-router-dom'

import type { components } from '../api/generated'

type SubmissionListItem = components['schemas']['SubmissionListItem']
type Status = SubmissionListItem['status']

const STATUS_LABEL: Record<Status, string> = {
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
      className="status-pill"
      style={{
        background: STATUS_COLOR[status],
        padding: '2px 10px',
        borderRadius: 12,
        fontSize: 12,
        fontWeight: 500,
        color: '#222',
        whiteSpace: 'nowrap',
      }}
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
    <table className="queue-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead>
        <tr>
          <th style={{ textAlign: 'left' }}>Thumb</th>
          <th style={{ textAlign: 'left' }}>Brand</th>
          <th style={{ textAlign: 'left' }}>Source</th>
          <th style={{ textAlign: 'left' }}>Status</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.id}>
            <td>
              <img
                src={item.thumbnail_url}
                alt={item.brand}
                width={48}
                height={48}
                style={{ objectFit: 'cover', borderRadius: 4 }}
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
            <td>
              <Link to={`/items/${item.id}`}>Open →</Link>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
