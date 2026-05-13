import { useEffect } from 'react'

import styles from './ImageLightbox.module.css'

interface Props {
  src: string
  alt: string
  caption?: string
  onClose: () => void
}

export default function ImageLightbox({ src, alt, caption, onClose }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className={styles.backdrop}
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={alt}
    >
      <div className={styles.shell} onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          className={styles.closeButton}
          onClick={onClose}
          aria-label="Close image"
        >
          ×
        </button>
        <img className={styles.image} src={src} alt={alt} />
        {caption && <span className={styles.caption}>{caption}</span>}
      </div>
    </div>
  )
}
