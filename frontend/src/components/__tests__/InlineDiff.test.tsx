import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import InlineDiff from '../InlineDiff'
import type { components } from '../../api/generated'

type DiffToken = components['schemas']['DiffToken']

describe('InlineDiff', () => {
  it('renders all three token kinds with distinct class names', () => {
    const tokens: DiffToken[] = [
      { text: 'shared ', kind: 'equal' },
      { text: 'added ', kind: 'added' },
      { text: 'removed', kind: 'removed' },
    ]
    const { container } = render(<InlineDiff tokens={tokens} />)
    const spans = container.querySelectorAll('span')
    expect(spans.length).toBe(3)
    const classes = Array.from(spans).map((s) => s.className)
    expect(classes[0]).toMatch(/diff-equal/)
    expect(classes[1]).toMatch(/diff-added/)
    expect(classes[2]).toMatch(/diff-removed/)
    // All three classes are distinct.
    expect(new Set(classes).size).toBe(3)
  })

  it('preserves whitespace inside tokens', () => {
    const tokens: DiffToken[] = [
      { text: 'hello ', kind: 'equal' },
      { text: 'world', kind: 'equal' },
    ]
    const { container } = render(<InlineDiff tokens={tokens} />)
    expect(container.textContent).toBe('hello world')
  })

  it('renders empty when token list is empty', () => {
    const { container } = render(<InlineDiff tokens={[]} />)
    // Component renders no token spans; the root wrapper may still exist but
    // must contain no text.
    expect(container.textContent).toBe('')
    expect(container.querySelectorAll('span').length).toBe(0)
  })
})
