import type { components } from '../api/generated'

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

export const STATUS_COLOR: Record<Status, string> = {
  loaded: '#cfd8dc',
  processing: '#bbdefb',
  ready_for_review: '#fff59d',
  approved: '#c8e6c9',
  rejected: '#ffcdd2',
  extraction_failed: '#ef9a9a',
}
