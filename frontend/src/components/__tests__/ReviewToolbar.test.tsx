import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import ReviewToolbar from '../ReviewToolbar'
import type { components } from '../../api/generated'

type SubmissionListItem = components['schemas']['SubmissionListItem']

function makeItem(id: string): SubmissionListItem {
  return {
    id,
    status: 'ready_for_review',
    brand: `brand-${id}`,
    is_fixture: true,
    created_at: '2026-05-13T00:00:00Z',
    thumbnail_url: `/api/submissions/${id}/image`,
    has_extraction_error: false,
  }
}

function renderWithCache(currentId: string, items: SubmissionListItem[]) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  })
  qc.setQueryData(['queue'], items)
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/items/${currentId}`]}>
        <ReviewToolbar currentId={currentId} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ReviewToolbar', () => {
  const items = [makeItem('a'), makeItem('b'), makeItem('c')]

  it('renders the back link to the queue', () => {
    renderWithCache('a', items)
    const back = screen.getByRole('link', { name: /back to queue/i })
    expect(back).toHaveAttribute('href', '/')
  })

  it('disables Prev at the first item, enables Next', () => {
    renderWithCache('a', items)
    expect(screen.getByRole('button', { name: /previous item/i })).toBeDisabled()
    expect(screen.getByRole('link', { name: /next item/i })).toHaveAttribute(
      'href',
      '/items/b',
    )
    expect(screen.getByText('Item 1 of 3')).toBeInTheDocument()
  })

  it('enables both Prev and Next at a middle item', () => {
    renderWithCache('b', items)
    expect(screen.getByRole('link', { name: /previous item/i })).toHaveAttribute(
      'href',
      '/items/a',
    )
    expect(screen.getByRole('link', { name: /next item/i })).toHaveAttribute(
      'href',
      '/items/c',
    )
    expect(screen.getByText('Item 2 of 3')).toBeInTheDocument()
  })

  it('disables Next at the last item, enables Prev', () => {
    renderWithCache('c', items)
    expect(screen.getByRole('link', { name: /previous item/i })).toHaveAttribute(
      'href',
      '/items/b',
    )
    expect(screen.getByRole('button', { name: /next item/i })).toBeDisabled()
    expect(screen.getByText('Item 3 of 3')).toBeInTheDocument()
  })

  it('renders an em-dash counter when the current id is not in the queue', () => {
    // Cold-load case where the cache hasn't caught up to the current item.
    renderWithCache('zzz-not-in-queue', items)
    expect(screen.getByRole('button', { name: /previous item/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /next item/i })).toBeDisabled()
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})
