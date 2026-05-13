import type { components } from '../api/generated'

type Confidence = components['schemas']['FieldRowOut']['confidence']

const NON_TEXT_FIELDS = new Set(['is_imported', 'government_warning_style'])

function isTextField(fieldName: string): boolean {
  return !NON_TEXT_FIELDS.has(fieldName)
}

const LABEL: Record<NonNullable<Confidence>, string> = {
  hi: 'hi',
  med: 'med',
  low: 'low',
}

const COLOR: Record<NonNullable<Confidence>, string> = {
  hi: '#1b5e20',
  med: '#8d6e00',
  low: '#b71c1c',
}

export default function ConfidenceBadge({
  field,
  confidence,
}: {
  field: string
  confidence: Confidence
}) {
  if (!isTextField(field)) return null
  if (confidence === 'hi' || confidence == null) return null
  return (
    <span
      title={`Extractor confidence: ${LABEL[confidence]}`}
      style={{
        marginLeft: 6,
        fontSize: 11,
        color: COLOR[confidence],
        fontWeight: 500,
      }}
    >
      {LABEL[confidence]}
      {confidence === 'low' ? ' ⚠' : ''}
    </span>
  )
}
