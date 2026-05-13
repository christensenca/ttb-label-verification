export default function SharedDemoBanner() {
  return (
    <div
      role="status"
      className="shared-demo-banner"
      style={{
        background: '#fff8db',
        borderBottom: '1px solid #e3d488',
        color: '#5d4b00',
        padding: '8px 16px',
        fontSize: 14,
        textAlign: 'center',
      }}
    >
      Shared demo instance — submissions, decisions, and overrides are visible
      to everyone using this URL.
    </div>
  )
}
