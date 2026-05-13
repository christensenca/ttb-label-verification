export default function ExtractionFailedBanner({ error }: { error: string }) {
  return (
    <div
      className="extraction-failed-banner"
      role="alert"
      style={{
        background: '#ffebee',
        border: '1px solid #ef9a9a',
        color: '#b71c1c',
        padding: '12px 16px',
        borderRadius: 4,
        marginBottom: 16,
      }}
    >
      <strong>Extraction failed:</strong> {error}
      <p style={{ marginTop: 6, marginBottom: 0, fontSize: 13, color: '#7c1f1f' }}>
        The model could not read this label. Review the expected values against the
        image yourself and override per field, or reject the item with a reason.
      </p>
    </div>
  )
}
