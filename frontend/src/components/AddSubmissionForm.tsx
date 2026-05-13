import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'

import { ApiError, api } from '../api/client'
import type { components } from '../api/generated'
import Dropzone from './Dropzone'
import styles from './AddSubmissionForm.module.css'

type SubmissionCreateOut = components['schemas']['SubmissionCreateOut']
type BulkCreateOut = components['schemas']['BulkCreateOut']

export interface AddSubmissionFormProps {
  /** Called whenever ≥1 row was created so the parent can refetch. */
  onAdded?: () => void
  /** Called when the form has nothing more to show and can be collapsed. */
  onDismiss?: () => void
}

type Tab = 'single' | 'batch'

export default function AddSubmissionForm({
  onAdded,
  onDismiss,
}: AddSubmissionFormProps) {
  const [tab, setTab] = useState<Tab>('single')
  return (
    <section className={styles.shell}>
      <div className={styles.tabs} role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'single'}
          className={styles.tab}
          onClick={() => setTab('single')}
        >
          Single
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'batch'}
          className={styles.tab}
          onClick={() => setTab('batch')}
        >
          Batch
        </button>
      </div>
      {tab === 'single' ? (
        <SinglePanel onAdded={onAdded} onDismiss={onDismiss} />
      ) : (
        <BatchPanel onAdded={onAdded} onDismiss={onDismiss} />
      )}
    </section>
  )
}

interface PanelProps {
  onAdded?: () => void
  onDismiss?: () => void
}

// --- Single ----------------------------------------------------------------

interface SingleFormState {
  brand: string
  class_type: string
  alcohol_content: string
  net_contents: string
  producer_name: string
  producer_address: string
  is_imported: boolean
  country_of_origin: string
}

const EMPTY_SINGLE: SingleFormState = {
  brand: '',
  class_type: '',
  alcohol_content: '',
  net_contents: '',
  producer_name: '',
  producer_address: '',
  is_imported: false,
  country_of_origin: '',
}

function SinglePanel({ onAdded, onDismiss }: PanelProps) {
  const [imageFiles, setImageFiles] = useState<File[]>([])
  const [form, setForm] = useState<SingleFormState>(EMPTY_SINGLE)
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: async () => {
      const file = imageFiles[0]
      if (!file) throw new ApiError(400, null, 'Please choose an image file.')

      const abv = Number(form.alcohol_content)
      if (!Number.isFinite(abv)) {
        throw new ApiError(400, null, 'Alcohol content must be a number.')
      }

      const payload = {
        brand: form.brand.trim(),
        class_type: form.class_type.trim(),
        alcohol_content: abv,
        net_contents: form.net_contents.trim(),
        producer_name: form.producer_name.trim(),
        producer_address: form.producer_address.trim(),
        is_imported: form.is_imported,
        country_of_origin: form.country_of_origin.trim() || null,
      }

      const fd = new FormData()
      fd.append('image', file)
      fd.append('expected_values', JSON.stringify(payload))
      return api.post<SubmissionCreateOut>('/api/submissions', fd)
    },
    onSuccess: () => {
      setError(null)
      setForm(EMPTY_SINGLE)
      setImageFiles([])
      onAdded?.()
      onDismiss?.()
    },
    onError: (err: unknown) => {
      setError(err instanceof ApiError ? err.message : String(err))
    },
  })

  function set<K extends keyof SingleFormState>(key: K, value: SingleFormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  return (
    <form
      className={styles.panel}
      onSubmit={(e) => {
        e.preventDefault()
        setError(null)
        mutation.mutate()
      }}
    >
      <div className={styles.split}>
        <div className={styles.column}>
          <div className={styles.columnLabel}>Label image</div>
          <Dropzone
            headline="Drop a label image here"
            subtext="or click to browse — JPG, PNG, or WebP, up to 10 MB"
            accept="image/jpeg,image/png,image/webp"
            files={imageFiles}
            onChange={setImageFiles}
            required
          />
        </div>
        <div className={styles.column}>
          <div className={styles.columnLabel}>Expected values</div>
          <div className={styles.fieldGrid}>
            <div className={styles.row}>
              <label className={styles.label} htmlFor="single-brand">
                Brand
              </label>
              <input
                id="single-brand"
                className={styles.input}
                value={form.brand}
                onChange={(e) => set('brand', e.target.value)}
                required
              />
            </div>
            <div className={styles.row}>
              <label className={styles.label} htmlFor="single-class">
                Class / Type
              </label>
              <input
                id="single-class"
                className={styles.input}
                value={form.class_type}
                onChange={(e) => set('class_type', e.target.value)}
                required
              />
            </div>
            <div className={styles.row}>
              <label className={styles.label} htmlFor="single-abv">
                Alcohol content (% ABV)
              </label>
              <input
                id="single-abv"
                className={styles.input}
                type="number"
                step="0.1"
                min="0"
                max="100"
                value={form.alcohol_content}
                onChange={(e) => set('alcohol_content', e.target.value)}
                required
              />
            </div>
            <div className={styles.row}>
              <label className={styles.label} htmlFor="single-net">
                Net contents
              </label>
              <input
                id="single-net"
                className={styles.input}
                placeholder="750 mL"
                value={form.net_contents}
                onChange={(e) => set('net_contents', e.target.value)}
                required
              />
            </div>
            <div className={styles.row}>
              <label className={styles.label} htmlFor="single-producer">
                Producer name
              </label>
              <input
                id="single-producer"
                className={styles.input}
                value={form.producer_name}
                onChange={(e) => set('producer_name', e.target.value)}
                required
              />
            </div>
            <div className={styles.row}>
              <label className={styles.label} htmlFor="single-address">
                Producer address
              </label>
              <input
                id="single-address"
                className={styles.input}
                value={form.producer_address}
                onChange={(e) => set('producer_address', e.target.value)}
                required
              />
            </div>
            <div className={styles.checkboxRow}>
              <input
                id="single-imported"
                type="checkbox"
                checked={form.is_imported}
                onChange={(e) => set('is_imported', e.target.checked)}
              />
              <label htmlFor="single-imported">Imported</label>
            </div>
            {form.is_imported && (
              <div className={styles.row}>
                <label className={styles.label} htmlFor="single-country">
                  Country of origin
                </label>
                <input
                  id="single-country"
                  className={styles.input}
                  value={form.country_of_origin}
                  onChange={(e) => set('country_of_origin', e.target.value)}
                  required
                />
              </div>
            )}
          </div>
        </div>
      </div>
      {error && <div className={styles.error}>{error}</div>}
      <div className={styles.actions}>
        <div className={styles.actionsRight}>
          <button
            type="submit"
            className={styles.submitButton}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? 'Adding…' : 'Add to queue'}
          </button>
        </div>
      </div>
    </form>
  )
}

// --- Batch -----------------------------------------------------------------

const CSV_TEMPLATE =
  'filename,brand,class_type,alcohol_content,net_contents,' +
  'producer_name,producer_address,is_imported,country_of_origin\n' +
  'my-label.jpg,Brand Name,Whisky,40.0,750 mL,Producer Co.,"City, ST",false,\n' +
  'imported.jpg,Other Brand,Vodka,40.0,1 L,Importer LLC,"Town, ST",true,Russia\n'

function downloadTemplate() {
  const blob = new Blob([CSV_TEMPLATE], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'expected-values-template.csv'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

function BatchPanel({ onAdded, onDismiss }: PanelProps) {
  const [imageFiles, setImageFiles] = useState<File[]>([])
  const [csvFiles, setCsvFiles] = useState<File[]>([])
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<BulkCreateOut | null>(null)

  const mutation = useMutation({
    mutationFn: async () => {
      const csvFile = csvFiles[0]
      if (!csvFile) throw new ApiError(400, null, 'Please choose a CSV file.')
      if (imageFiles.length === 0) {
        throw new ApiError(400, null, 'Please choose at least one image.')
      }
      const fd = new FormData()
      fd.append('csv', csvFile)
      for (const img of imageFiles) fd.append('images', img)
      return api.post<BulkCreateOut>('/api/submissions/bulk', fd)
    },
    onSuccess: (data) => {
      setError(null)
      setResult(data)
      if (data.created.length > 0) onAdded?.()
      if (data.errors.length === 0 && data.created.length > 0) {
        setCsvFiles([])
        setImageFiles([])
        onDismiss?.()
      }
    },
    onError: (err: unknown) => {
      setResult(null)
      setError(err instanceof ApiError ? err.message : String(err))
    },
  })

  return (
    <form
      className={styles.panel}
      onSubmit={(e) => {
        e.preventDefault()
        setError(null)
        setResult(null)
        mutation.mutate()
      }}
    >
      <div className={styles.split}>
        <div className={styles.column}>
          <div className={styles.columnLabel}>Label images</div>
          <Dropzone
            headline="Drop image files here"
            subtext="or click to browse — one image per CSV row, JPG/PNG/WebP"
            accept="image/jpeg,image/png,image/webp"
            multiple
            files={imageFiles}
            onChange={setImageFiles}
            required
          />
        </div>
        <div className={styles.column}>
          <div className={styles.columnLabel}>CSV manifest</div>
          <Dropzone
            headline="Drop a CSV here"
            subtext="or click to browse — one row per label"
            accept=".csv,text/csv"
            files={csvFiles}
            onChange={setCsvFiles}
            required
          />
          <button
            type="button"
            className={styles.linkButton}
            onClick={downloadTemplate}
          >
            Download CSV template
          </button>
        </div>
      </div>
      {error && <div className={styles.error}>{error}</div>}
      {result && result.created.length > 0 && (
        <div className={styles.success}>
          Added {result.created.length}{' '}
          {result.created.length === 1 ? 'item' : 'items'} to the queue.
        </div>
      )}
      {result && result.errors.length > 0 && (
        <div className={styles.error}>
          {result.errors.length}{' '}
          {result.errors.length === 1 ? 'row was' : 'rows were'} skipped:
          <ul className={styles.errorList}>
            {result.errors.map((e, i) => (
              <li key={i}>
                {e.row != null ? `row ${e.row}` : 'batch'}
                {e.filename ? ` (${e.filename})` : ''}: {e.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className={styles.actions}>
        <div className={styles.actionsRight}>
          <button
            type="submit"
            className={styles.submitButton}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? 'Uploading…' : 'Upload batch'}
          </button>
        </div>
      </div>
    </form>
  )
}
