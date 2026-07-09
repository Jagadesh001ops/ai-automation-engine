import { useState } from "react"
import SubmitRun from "./components/SubmitRun"
import Results from "./components/Results"
import RunHistory from "./components/RunHistory"

export default function App() {
  const [screen, setScreen] = useState("submit") // "submit" | "results" | "history"
  const [currentRun, setCurrentRun] = useState(null)

  function handleRunComplete(run) {
    setCurrentRun(run)
    setScreen("results")
  }

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      {/* Nav */}
      <nav className="border-b border-gray-800 px-6 py-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold tracking-tight">
          AI Workflow Engine
        </h1>
        <div className="flex gap-4">
          <button
            onClick={() => setScreen("submit")}
            className={`text-sm px-3 py-1.5 rounded-md transition ${
              screen === "submit"
                ? "bg-gray-800 text-white"
                : "text-gray-400 hover:text-white"
            }`}
          >
            New Run
          </button>
          <button
            onClick={() => setScreen("history")}
            className={`text-sm px-3 py-1.5 rounded-md transition ${
              screen === "history"
                ? "bg-gray-800 text-white"
                : "text-gray.400 hover:text-white"
            }`}
          >
            History
          </button>
        </div>
      </nav>

      {/* Screens */}
      <main className="max-w-3xl mx-auto px-6 py-10">
        {screen === "submit" && (
          <SubmitRun onRunComplete={handleRunComplete} />
        )}
        {screen === "results" && (
          <Results run={currentRun} onNewRun={() => setScreen("submit")} />
        )}
        {screen === "history" && (
          <RunHistory onSelectRun={(run) => { setCurrentRun(run); setScreen("results") }} />
        )}
      </main>
    </div>
  )
}