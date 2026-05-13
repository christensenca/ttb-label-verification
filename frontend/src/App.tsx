import { Outlet, Route, Routes } from 'react-router-dom'

import QueuePage from './pages/QueuePage'
import ReviewPage from './pages/ReviewPage'

function Layout() {
  return (
    <div className="app-shell">
      <header className="app-topbar">
        <div className="app-topbar-inner">
          <span className="app-brand">LabelGuard</span>
          <span className="app-subtitle">AI-assisted TTB review</span>
        </div>
      </header>
      <main className="app-content">
        <Outlet />
      </main>
      <footer className="app-footer">
        <div className="app-footer-inner">
          <span>
            Shared demo instance — submissions, decisions, and overrides are
            visible to everyone using this URL.
          </span>
          <span className="app-footer-tag">Prototype</span>
        </div>
      </footer>
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
