import { useParams } from 'react-router-dom'

export default function ReviewPage() {
  const { id } = useParams<{ id: string }>()
  return (
    <section className="review-page">
      <h2>Review</h2>
      <p>Submission: {id}</p>
      <p>Review screen goes here (T043 in US1).</p>
    </section>
  )
}
