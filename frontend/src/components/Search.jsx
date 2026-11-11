import { useState } from 'react'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function Search() {
  const [q, setQ] = useState('')
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const search = async (e) => {
    e.preventDefault()
    if (!q.trim()) return
    setLoading(true)
    setError(null)
    setResults(null)
    try {
      const res = await fetch(`${API}/search?q=${encodeURIComponent(q)}&top_k=10`)
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setResults(data.results)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold">Semantic Search</h2>
      <form onSubmit={search} className="flex gap-2">
        <input
          type="text"
          value={q}
          onChange={e => setQ(e.target.value)}
          placeholder="Search across your documents…"
          className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
        />
        <button
          type="submit"
          disabled={loading}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 rounded-lg text-sm text-white transition"
        >
          {loading ? 'Searching…' : 'Search'}
        </button>
      </form>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {results !== null && (
        results.length === 0 ? (
          <p className="text-gray-500 text-sm">No results found.</p>
        ) : (
          <div className="space-y-3">
            {results.map((r, i) => (
              <div key={i} className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs font-mono text-gray-500">doc #{r.document_id} · chunk #{r.chunk_id}</span>
                  {r.score !== undefined && (
                    <span className="ml-auto text-xs text-gray-500">score {r.score.toFixed(3)}</span>
                  )}
                </div>
                <p className="text-sm text-gray-300 leading-relaxed line-clamp-4">{r.text}</p>
                <p className="text-xs text-gray-600 mt-1 font-mono">chars {r.char_start}–{r.char_end}</p>
              </div>
            ))}
          </div>
        )
      )}
    </div>
  )
}
