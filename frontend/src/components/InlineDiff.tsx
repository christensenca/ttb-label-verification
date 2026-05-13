import { Fragment } from 'react'
import type { components } from '../api/generated'
import styles from './InlineDiff.module.css'

type DiffToken = components['schemas']['DiffToken']

const KIND_CLASS: Record<DiffToken['kind'], string> = {
  equal: `diff-equal ${styles.equal}`,
  added: `diff-added ${styles.added}`,
  removed: `diff-removed ${styles.removed}`,
}

export default function InlineDiff({ tokens }: { tokens: DiffToken[] }) {
  if (tokens.length === 0) return null
  return (
    <Fragment>
      {tokens.map((tok, i) => (
        <span key={i} className={`${styles.token} ${KIND_CLASS[tok.kind]}`}>
          {tok.text}
        </span>
      ))}
    </Fragment>
  )
}
