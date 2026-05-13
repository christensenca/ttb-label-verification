import { useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'

import { ApiError, api } from '../api/client'
import type { components } from '../api/generated'
import styles from './AddSubmissionForm.module.css'

type SubmissionCreateOut = components['schemas']['SubmissionCreateOut']

const EXAMPLE_EXPECTED_VALUES = JSON.stringify(
  {
    brand: "Brand Name",
    class_type: "Whisky",
    alcohol_content: 40.0,
    net_contents: "750 mL",
    producer_name: "Producer Co.",
    producer_address: "City, ST",
    is_imported: false,
    country_of_origin: null,
  },
  null,
  2,
)

export interface AddSubmissionFormProps {
  onCreated?: (created: SubmissionCreateOut) => void
}

export default function AddSubmissionForm({ onCreated }: AddSubmissionFormProps) {
  const fileRef = useRef<HTMLInputElement | null>(null)
  const [expectedValues, setExpectedValues] = useState(EXAMPLE_EXPECTED_VALUES)
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: async () => {
      const file = fileRef.current?.files?.[0]
      if (!file) {
        throw new ApiError(400, null, 'Please choose an image file.')
      }
      const fd = new FormData()
      fd.append('image', file)
      fd.append('expected_values', expectedValues)
      return api.post<SubmissionCreateOut>('/api/submissions', fd)
    },
    onSuccess: (created) => {
      setError(null)
      setExpectedValues(EXAMPLE_EXPECTED_VALUES)
      if (fileRef.current) fileRef.current.value = ''
      onCreated?.(created)
    },
    onError: (err: unknown) => {
      if (err instanceof ApiError) {
        setError(err.message)
      } else {
        setError(String(err))
      }
    },
  })

  return (
    <form
      className={styles.form}
      onSubmit={(e) => {
        e.preventDefault()
        setError(null)
        mutation.mutate()
      }}
    >
      <div className={styles.row}>
        <label className={styles.label} htmlFor="add-submission-image">
          Label image
        </label>
        <input
          ref={fileRef}
          id="add-submission-image"
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className={styles.fileInput}
          required
        />
        <span className={styles.help}>JPG, PNG, or WebP. Max 10 MB.</span>
      </div>
      <div className={styles.row}>
        <label className={styles.label} htmlFor="add-submission-expected">
          Expected values (JSON)
        </label>
        <textarea
          id="add-submission-expected"
          className={styles.textarea}
          value={expectedValues}
          onChange={(e) => setExpectedValues(e.target.value)}
          spellCheck={false}
        />
        <span className={styles.help}>
          Set <code>is_imported: true</code> only when{' '}
          <code>country_of_origin</code> is also a non-empty string.
        </span>
      </div>
      {error && <div className={styles.error}>{error}</div>}
      <div className={styles.actions}>
        <button
          type="submit"
          className={styles.submitButton}
          disabled={mutation.isPending}
        >
          {mutation.isPending ? 'Adding…' : 'Add to queue'}
        </button>
      </div>
    </form>
  )
}
