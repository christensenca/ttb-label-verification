import type { components } from '../api/generated'
import FieldRow from './FieldRow'

type Group = components['schemas']['FieldGroupOut']

export default function FieldGroup({ group }: { group: Group }) {
  return (
    <section className="field-group" style={{ marginBottom: 24 }}>
      <h3 style={{ marginBottom: 8, borderBottom: '1px solid #ddd', paddingBottom: 4 }}>
        {group.name}
      </h3>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ textAlign: 'left', color: '#666', fontSize: 12 }}>
            <th style={{ width: '20%' }}>Field</th>
            <th style={{ width: '30%' }}>Extracted</th>
            <th style={{ width: '30%' }}>Expected</th>
            <th style={{ width: '20%' }}>Verdict</th>
          </tr>
        </thead>
        <tbody>
          {group.fields.map((f) => (
            <FieldRow key={f.id} field={f} />
          ))}
        </tbody>
      </table>
    </section>
  )
}
