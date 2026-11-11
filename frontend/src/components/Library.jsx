import { useEffect, useState } from 'react'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function Library({ onSelectDoc }) {
  const [docs, setDocs] = useState([])
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState(null)

  const load = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API}/documents`)
      if (res.ok) setDocs(await res.json())
    } catch { /* ignore fetch errors */ }
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  const deleteDoc = async (id) => {
    if (!confirm('Delete this document?')) return
    setDeleting(id)
    try {
      await fetch(`${API}/documents/${id}`, { method: 'DELETE' })
      setDocs(d => d.filter(x => x.document_id !== id))
    } catch { /* ignore fetch errors */ }
    setDeleting(null)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Document Library</h2>
        <button onClick={load} className="text-xs text-gray-400 hover:text-gray-200 transition">
          Refresh
        </button>
      </div>

      {loading ? (
        <p className="text-gray-500 text-sm">Loading…</p>
      ) : docs.length === 0 ? (
        <p className="text-gray-500 text-sm">No documents yet. Upload one to get started.</p>
      ) : (
        <div className="space-y-2">
          {docs.map(doc => (
            <div
              key={doc.document_id}
              className="bg-gray-900 border border-gray-800 rounded-lg p-4 flex items-center gap-3"
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{doc.filename}</p>
                <p className="text-xs text-gray-500 mt-0.5">
                  {doc.page_count} p · {(doc.size_bytes / 1024).toFixed(1)} KB ·{' '}
                  <span className={`${doc.status === 'ready' ? 'text-green-400' : doc.status === 'failed' ? 'text-red-400' : 'text-yellow-400'}`}>
                    {doc.status}
                  </span>
                </p>
              </div>
              <div className="flex gap-2 shrink-0">
                {onSelectDoc && doc.status === 'ready' && (
                  <button
                    onClick={() => onSelectDoc(doc)}
                    className="text-xs px-2 py-1 bg-blue-900/40 border border-blue-700 text-blue-300 rounded hover:bg-blue-900/60 transition"
                  >
                    Use
                  </button>
                )}
                <button
                  onClick={() => deleteDoc(doc.document_id)}
                  disabled={deleting === doc.document_id}
                  className="text-xs px-2 py-1 bg-red-900/20 border border-red-800 text-red-400 rounded hover:bg-red-900/40 transition disabled:opacity-40"
                >
                  {deleting === doc.document_id ? '…' : 'Delete'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
