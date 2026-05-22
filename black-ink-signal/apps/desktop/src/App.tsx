export function App() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">Black Ink Signal</div>
        <div className="panel">
          <div className="panel-title">Scope</div>
          <div className="panel-body">Public-only • Reddit MVP • Manual review</div>
        </div>
      </aside>
      <main className="feed">
        <header className="feed-header">
          <h1>Live Feed</h1>
          <span className="status">stub</span>
        </header>
        <section className="empty-state">
          <h2>No leads loaded yet</h2>
          <p>Backend/API wiring comes next.</p>
        </section>
      </main>
    </div>
  )
}
