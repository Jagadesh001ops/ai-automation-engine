export default function Results({ run, onNewRun }) {
  if (!run) return null

  const outputKeys = Object.keys(run.output)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold mb-1">Results</h2>
          <p className="text-gray-400 text-sm">{run.goal}</p>
        </div>
        <button
          onClick={onNewRun}
          className="text-sm px-3 py-1.5 border border-gray-700 rounded-md text-gray-300 hover:text-white hover:border-gray-500 transition whitespace-nowrap"
        >
          New Run
        </button>
      </div>

      {/* Metadata */}
      <div className="flex gap-4 text-sm text-gray-400">
        <span>Run #{run.run_id}</span>
        <span>·</span>
        <span>{run.steps?.length} steps</span>
        <span>·</span>
        <span>{run.total_tokens} tokens</span>
        <span>·</span>
        <span>{Math.round(run.total_time_ms)}ms</span>
      </div>

      {/* Pipeline steps */}
      <div className="space-y-3">
        {run.steps?.map((step, i) => (
          <div key={step.name} className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-xs font-mono bg-gray-800 text-gray-400 px-2 py-0.5 rounded">
                {i + 1}
              </span>
              <span className="text-sm font-medium">{step.name}</span>
              <span className="text-xs text-gray-500 ml-auto font-mono">
                {step.input_key} → {step.output_key}
              </span>
            </div>
            {run.output[step.output_key] && (
              <p className="text-sm text-gray-300 whitespace-pre-wrap leading-relaxed">
                {run.output[step.output_key]}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}