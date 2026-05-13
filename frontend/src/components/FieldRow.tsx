import type { components } from '../api/generated'

type Field = components['schemas']['FieldRowOut']

const FIELD_LABELS: Record<string, string> = {
  brand: 'Brand',
  class_type: 'Class / Type',
  alcohol_content: 'Alcohol content',
  net_contents: 'Net contents',
  producer_name: 'Producer name',
  producer_address: 'Producer address',
  is_imported: 'Imported',
  country_of_origin: 'Country of origin',
  government_warning_text: 'Warning text',
  government_warning_style: 'Warning style',
}

const VERDICT_COLOR: Record<string, string> = {
  pass: '#2e7d32',
  fail: '#c62828',
  not_applicable: '#888',
}

export default function FieldRow({ field }: { field: Field }) {
  const label = FIELD_LABELS[field.field] ?? field.field
  return (
    <tr style={{ borderBottom: '1px solid #eee', verticalAlign: 'top' }}>
      <td style={{ padding: '6px 8px 6px 0', fontWeight: 500 }}>{label}</td>
      <td style={{ padding: '6px 8px' }}>
        {field.extracted_value ?? <span style={{ color: '#999' }}>—</span>}
      </td>
      <td style={{ padding: '6px 8px' }}>
        {field.expected_value ?? <span style={{ color: '#999' }}>—</span>}
      </td>
      <td style={{ padding: '6px 8px' }}>
        <span
          style={{
            color: VERDICT_COLOR[field.effective_verdict] ?? '#222',
            fontWeight: 600,
          }}
        >
          {field.effective_verdict.toUpperCase()}
        </span>
        <div style={{ color: '#666', fontSize: 12 }}>{field.rule}</div>
      </td>
    </tr>
  )
}
