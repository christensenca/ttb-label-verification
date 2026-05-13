import { Outlet, Route, Routes } from 'react-router-dom'

import SharedDemoBanner from './components/SharedDemoBanner'
import QueuePage from './pages/QueuePage'
import ReviewPage from './pages/ReviewPage'

function Layout() {
  return (
    <div className="app-shell">
      <SharedDemoBanner />
      <header className="app-header">
        <h1>TTB Label Verify</h1>
        <span className="app-tagline">
          AI-assisted label compliance review · prototype
        </span>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<QueuePage />} />
        <Route path="/items/:id" element={<ReviewPage />} />
      </Route>
    </Routes>
  )
}
