import { useState } from "react"

const API_URL = import.meta.env.VITE_API_URL

export default function SubmitRun({ onRunComplete }) {
  const [document, setDocument] = useState("")
  const [request, setRequest] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function handleSubmit() {
    if (!document.trim() || !request.trim()) {
      setError("Both fields are required.")
      return
    }

    setLoading(true)
    setError(null)

    try {
      if (!API_URL) throw new Error("VITE_API_URL is not configured.")

      const res = await fetch(`${API_URL}/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ document, request })
      })

      if (!res.ok) throw new Error(`Server error: ${res.status}`)
      const data = await res.json()
      onRunComplete(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold mb-1">New Run</h2>
        <p className="text-gray-400 text-sm">
          Paste a document and describe what you want done with it.
        </p>
      </div>

      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1.5">
            Document
          </label>
          <textarea
            value={document}
            onChange={e => setDocument(e.target.value)}
            rows={8}
            placeholder="Paste your document text here..."
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-3 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-gray-500 resize-none"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1.5">
            Request
          </label>
          <input
            value={request}
            onChange={e => setRequest(e.target.value)}
            placeholder="e.g. Summarize this, extract key concepts, and generate quiz questions."
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-3 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-gray-500"
          />
        </div>

        {error && (
          <p className="text-red-400 text-sm">{error}</p>
        )}

        <button
          onClick={handleSubmit}
          disabled={loading}
          className="w-full bg-white text-gray-950 font-medium text-sm py-3 rounded-lg hover:bg-gray-100 transition disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? "Running pipeline..." : "Run Workflow"}
        </button>
      </div>
    </div>
  )
}
