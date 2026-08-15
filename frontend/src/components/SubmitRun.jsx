import { useEffect, useRef, useState } from "react"

const API = import.meta.env.VITE_API_URL || "http://localhost:8000"
const ACCEPT = ".pdf,.txt,.md,text/plain,application/pdf,text/markdown"

export default function SubmitRun({ onRunComplete, prefillDoc, onClearDoc }) {
  const [file, setFile] = useState(null)
  const [request, setRequest] = useState("")
  const [uploading, setUploading] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [steps, setSteps] = useState([])      // live step events for progress display
  const [error, setError] = useState(null)
  const fileInputRef = useRef(null)

  // When the user picks a doc from Library, clear any local file selection
  useEffect(() => {
    if (prefillDoc) setFile(null)
  }, [prefillDoc])

  const loading = uploading || streaming

  async function handleSubmit() {
    if (!file && !prefillDoc) { setError("Please select a file."); return }
    if (!request.trim()) { setError("Please enter a request."); return }
    setError(null)
    setSteps([])

    let documentText = ""

    if (file) {
      // Upload file, get document_id; also read text locally for the run
      setUploading(true)
      try {
        const form = new FormData()
        form.append("file", file)
        const res = await fetch(`${API}/documents`, { method: "POST", body: form })
        if (!res.ok) {
          const body = await res.json().catch(() => ({}))
          throw new Error(body.detail || `Upload failed: ${res.status}`)
        }
        documentText = await _readFileAsText(file)
      } catch (err) {
        setError(err.message)
        return
      } finally {
        setUploading(false)
      }
    } else {
      // prefillDoc selected from Library — fetch its stored text via chunks
      // For simplicity pass a placeholder; retrieval nodes will use the stored chunks
      documentText = `[Document: ${prefillDoc.filename}]`
    }

    setStreaming(true)
    try {
      const res = await fetch(`${API}/run/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          document: documentText,
          request,
          document_id: prefillDoc?.document_id ?? null,
        }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || `Run failed: ${res.status}`)
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""

      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n")
        buffer = lines.pop()
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          try {
            const event = JSON.parse(line.slice(6))
            if (event.type === "step_start") {
              setSteps(s => [...s, { name: event.name, running: true }])
            } else if (event.type === "step") {
              setSteps(s => s.map(x => x.name === event.name
                ? { ...x, running: false, success: event.success, time_ms: event.time_ms }
                : x))
            } else if (event.type === "done") {
              onRunComplete(event)
            } else if (event.type === "error") {
              setError(event.message)
            }
          } catch {}
        }
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setStreaming(false)
    }
  }

  function handleDrop(e) {
    e.preventDefault()
    const f = e.dataTransfer.files?.[0] ?? null
    if (f) { setFile(f); setError(null); onClearDoc?.() }
  }

  function handleFileChange(e) {
    const f = e.target.files?.[0] ?? null
    setFile(f); setError(null); onClearDoc?.()
  }

  function clearFile() {
    setFile(null)
    if (fileInputRef.current) fileInputRef.current.value = ""
  }

  const activeDoc = file ? { name: file.name, size: `${(file.size/1024).toFixed(1)} KB` }
    : prefillDoc ? { name: prefillDoc.filename, size: `${(prefillDoc.size_bytes/1024).toFixed(1)} KB (library)` }
    : null

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold mb-1">New Run</h2>
        <p className="text-gray-400 text-sm">
          Upload a file or pick one from Library, then describe what you want done.
        </p>
      </div>

      <div className="space-y-4">
        {/* File drop zone */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1.5">Document</label>
          <div
            onClick={() => !activeDoc && fileInputRef.current?.click()}
            onDrop={handleDrop}
            onDragOver={e => e.preventDefault()}
            className={`w-full border-2 border-dashed rounded-lg px-4 py-8 text-center transition
              ${activeDoc
                ? "border-gray-600 bg-gray-900 cursor-default"
                : "border-gray-700 bg-gray-900 hover:border-gray-500 cursor-pointer"}`}
          >
            <input ref={fileInputRef} type="file" accept={ACCEPT}
              className="hidden" onChange={handleFileChange} />
            {activeDoc ? (
              <div className="space-y-1">
                <p className="text-sm text-white font-medium">{activeDoc.name}</p>
                <p className="text-xs text-gray-400">
                  {activeDoc.size} &middot;{" "}
                  <span className="text-gray-500 hover:text-gray-300 cursor-pointer transition"
                    onClick={e => { e.stopPropagation(); clearFile(); onClearDoc?.() }}>
                    Remove
                  </span>
                </p>
              </div>
            ) : (
              <div className="space-y-1">
                <p className="text-sm text-gray-400">
                  Drop a file here or <span className="text-white underline">browse</span>
                </p>
                <p className="text-xs text-gray-600">PDF, TXT, MD — up to 25 MB</p>
              </div>
            )}
          </div>
        </div>

        {/* Request */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1.5">Request</label>
          <input
            value={request}
            onChange={e => setRequest(e.target.value)}
            onKeyDown={e => e.key === "Enter" && !loading && handleSubmit()}
            placeholder="e.g. Summarize this, extract key concepts, and generate quiz questions."
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-3 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-gray-500"
          />
        </div>

        {/* Live progress */}
        {steps.length > 0 && (
          <div className="space-y-1">
            {steps.map((s, i) => (
              <div key={i} className="flex items-center gap-2 text-sm">
                <span className={`w-4 text-center ${s.running ? 'text-yellow-400 animate-pulse' : s.success ? 'text-green-400' : 'text-red-400'}`}>
                  {s.running ? '…' : s.success ? '✓' : '✗'}
                </span>
                <span className={s.running ? 'text-white' : 'text-gray-400'}>{s.name}</span>
                {s.time_ms !== undefined && !s.running && (
                  <span className="ml-auto text-xs text-gray-600">{s.time_ms}ms</span>
                )}
              </div>
            ))}
          </div>
        )}

        {error && <p className="text-red-400 text-sm">{error}</p>}

        <button
          onClick={handleSubmit}
          disabled={loading}
          className="w-full bg-white text-gray-950 font-medium text-sm py-3 rounded-lg hover:bg-gray-100 transition disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {uploading ? "Extracting document…" : streaming ? "Running workflow…" : "Run Workflow"}
        </button>
      </div>
    </div>
  )
}

async function _readFileAsText(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = e => resolve(e.target.result)
    reader.onerror = () => reject(new Error("Could not read file"))
    reader.readAsText(file, "utf-8")
  })
}
