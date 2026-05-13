import { useEffect, useId, useMemo, useRef, useState } from 'react'
import type { DragEvent } from 'react'

import styles from './Dropzone.module.css'

export interface DropzoneProps {
  headline: string
  subtext: string
  accept: string
  multiple?: boolean
  files: File[]
  onChange: (files: File[]) => void
  required?: boolean
  /** Limit how many files are accepted in a single multi-select. */
  maxFiles?: number
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function isImage(file: File): boolean {
  return file.type.startsWith('image/')
}

export default function Dropzone({
  headline,
  subtext,
  accept,
  multiple = false,
  files,
  onChange,
  required,
  maxFiles,
}: DropzoneProps) {
  const inputId = useId()
  const inputRef = useRef<HTMLInputElement | null>(null)
  // Counter handles dragenter/leave fires from descendant elements.
  const dragDepth = useRef(0)
  const [isDragging, setIsDragging] = useState(false)

  // Generate preview URLs for image files; revoke on cleanup or replacement.
  const previews = useMemo(
    () => files.map((f) => (isImage(f) ? URL.createObjectURL(f) : null)),
    [files],
  )
  useEffect(() => {
    return () => {
      previews.forEach((url) => {
        if (url) URL.revokeObjectURL(url)
      })
    }
  }, [previews])

  function applyIncoming(list: FileList | File[]) {
    let next = Array.from(list)
    if (!multiple) next = next.slice(0, 1)
    if (maxFiles != null && next.length > maxFiles) next = next.slice(0, maxFiles)
    onChange(next)
  }

  function handleDragEnter(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    dragDepth.current += 1
    if (e.dataTransfer.types.includes('Files')) setIsDragging(true)
  }

  function handleDragOver(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'copy'
  }

  function handleDragLeave(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    dragDepth.current = Math.max(0, dragDepth.current - 1)
    if (dragDepth.current === 0) setIsDragging(false)
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    dragDepth.current = 0
    setIsDragging(false)
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      applyIncoming(e.dataTransfer.files)
    }
  }

  function openPicker() {
    inputRef.current?.click()
  }

  function removeAt(i: number) {
    const next = files.filter((_, idx) => idx !== i)
    onChange(next)
    if (next.length === 0 && inputRef.current) inputRef.current.value = ''
  }

  function clearAll() {
    onChange([])
    if (inputRef.current) inputRef.current.value = ''
  }

  const hasFiles = files.length > 0
  const showRequired = required && !hasFiles
  const isSingleMode = !multiple

  return (
    <div
      className={[
        styles.zone,
        isDragging ? styles.dragging : '',
        hasFiles ? styles.populated : '',
      ]
        .filter(Boolean)
        .join(' ')}
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onClick={() => {
        if (!hasFiles) openPicker()
      }}
      role="button"
      tabIndex={hasFiles ? -1 : 0}
      onKeyDown={(e) => {
        if (!hasFiles && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault()
          openPicker()
        }
      }}
    >
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        accept={accept}
        multiple={multiple}
        className={styles.input}
        onChange={(e) => {
          if (e.target.files) applyIncoming(e.target.files)
        }}
        required={showRequired}
        aria-label={headline}
      />

      {!hasFiles && (
        <>
          <div className={styles.icon} aria-hidden>
            ⬆
          </div>
          <div className={styles.headline}>{headline}</div>
          <div className={styles.subtext}>{subtext}</div>
        </>
      )}

      {hasFiles && isSingleMode && (
        <SinglePopulated
          file={files[0]}
          previewUrl={previews[0]}
          onReplace={openPicker}
        />
      )}

      {hasFiles && !isSingleMode && (
        <>
          <div className={styles.populatedHeader}>
            <span>
              {files.length} {files.length === 1 ? 'file' : 'files'} selected
            </span>
            <button
              type="button"
              className={styles.actionButton}
              onClick={(e) => {
                e.stopPropagation()
                openPicker()
              }}
            >
              Add more…
            </button>
          </div>
          <ul className={styles.fileList}>
            {files.map((file, i) => (
              <li key={`${file.name}-${i}`} className={styles.fileItem}>
                {previews[i] ? (
                  <img
                    src={previews[i] ?? undefined}
                    alt=""
                    className={styles.thumb}
                  />
                ) : (
                  <span className={styles.thumbPlaceholder} aria-hidden>
                    📄
                  </span>
                )}
                <span className={styles.fileName} title={file.name}>
                  {file.name}
                </span>
                <span className={styles.fileSize}>{formatBytes(file.size)}</span>
                <button
                  type="button"
                  className={styles.removeIcon}
                  onClick={(e) => {
                    e.stopPropagation()
                    removeAt(i)
                  }}
                  aria-label={`Remove ${file.name}`}
                >
                  ✕
                </button>
              </li>
            ))}
          </ul>
          <div className={styles.multiFooter}>
            <button
              type="button"
              className={styles.actionButton}
              onClick={(e) => {
                e.stopPropagation()
                clearAll()
              }}
            >
              Clear all
            </button>
          </div>
        </>
      )}
    </div>
  )
}

function SinglePopulated({
  file,
  previewUrl,
  onReplace,
}: {
  file: File
  previewUrl: string | null
  onReplace: () => void
}) {
  return (
    <div className={styles.singlePopulated}>
      <div className={styles.singlePreview}>
        {previewUrl ? (
          <img src={previewUrl} alt={file.name} />
        ) : (
          <div className={styles.singleNonImage}>
            <span className={styles.docIcon} aria-hidden>
              📄
            </span>
            <span>No preview available</span>
          </div>
        )}
      </div>
      <div className={styles.singleMeta}>
        <span className={styles.singleFilename} title={file.name}>
          {file.name}
        </span>
        <span className={styles.singleSize}>{formatBytes(file.size)}</span>
      </div>
      <button
        type="button"
        className={styles.singleReplace}
        onClick={(e) => {
          e.stopPropagation()
          onReplace()
        }}
      >
        Replace
      </button>
    </div>
  )
}
