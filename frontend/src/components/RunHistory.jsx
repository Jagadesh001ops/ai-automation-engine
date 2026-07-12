import { useState, useEffect } from "react"

const API_URL = import.meta.env.VITE_API_URL

export default function RunHistory({ onSelectRun }) {
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [loadingRun, setLoadingRun] = useState(null)

  useEffect(() => {
    if (!API_URL) {
      setError("VITE_API_URL is not configured.")
      setLoading(false)
      return
    }

    fetch(`${API_URL}/runs`)
      .then(res => res.json())
      .then(data => { setRuns(data); setLoading(false) })
      .catch(err => { setError(err.message); setLoading(false) })
  }, [])

  async function handleSelect(run) {
    setLoadingRun(run.id)
    try {
      if (!API_URL) throw new Error("VITE_API_URL is not configured.")

      const res = await fetch(`${API_URL}/runs/${run.id}`)
      const data = await res.json()
      onSelectRun(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoadingRun(null)
    }
  }

  if (loading) return <p className="text-gray-400 text-sm">Loading history...</p>
  if (error) return <p className="text-red-400 text-sm">{error}</p>
  if (runs.length === 0) return <p className="text-gray-400 text-sm">No runs yet.</p>

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-semibold mb-1">Run History</h2>
        <p className="text-gray-400 text-sm">{runs.length} runs total</p>
      </div>

      <div className="space-y-2">
        {runs.map(run => (
          <div
            key={run.id}
            onClick={() => handleSelect(run)}
            className="bg-gray-900 border border-gray-800 rounded-lg px-4 py-3 flex items-center justify-between hover:border-gray-600 transition cursor-pointer"
          >
            <div className="space-y-0.5">
              <p className="text-sm font-medium">{run.goal}</p>
              <p className="text-xs text-gray-500">
                {new Date(run.created_at).toLocaleString()} · {run.steps} steps · {run.total_tokens} tokens
              </p>
            </div>
            <div className="flex items-center gap-2">
              {loadingRun === run.id && (
                <span className="text-xs text-gray-400">Loading...</span>
              )}
              <span className={`text-xs px-2 py-0.5 rounded-full ${
                run.status === "success"
                  ? "bg-green-900 text-green-400"
                  : "bg-red-900 text-red-400"
              }`}>
                {run.status}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
