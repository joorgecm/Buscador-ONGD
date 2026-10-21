import { useEffect, useState } from 'react'
import { checkBackendHealth } from './services/api'
import type { HealthResponse } from './types'

function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  const handleRetry = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await checkBackendHealth()
      setHealth(data)
    } catch (err) {
      setHealth(null)
      setError(
        err instanceof Error
          ? err.message
          : 'No se pudo conectar con el servidor FastAPI'
      )
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let active = true
    checkBackendHealth()
      .then((data) => {
        if (active) {
          setHealth(data)
          setError(null)
          setLoading(false)
        }
      })
      .catch((err) => {
        if (active) {
          setHealth(null)
          setError(
            err instanceof Error
              ? err.message
              : 'No se pudo conectar con el servidor FastAPI'
          )
          setLoading(false)
        }
      })
    return () => {
      active = false
    }
  }, [])

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col">
      <header className="bg-white border-b border-slate-200 px-6 py-4">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-slate-900">
              Buscador de ONGD (IEI)
            </h1>
            <p className="text-sm text-slate-500">
              Comunitat Valenciana · Catalunya · Canarias
            </p>
          </div>

          <div className="flex items-center gap-3">
            <span
              className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium border ${
                loading
                  ? 'bg-amber-50 text-amber-700 border-amber-200'
                  : health?.status === 'ok'
                    ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                    : 'bg-rose-50 text-rose-700 border-rose-200'
              }`}
            >
              <span
                className={`h-2 w-2 rounded-full ${
                  loading
                    ? 'bg-amber-500 animate-pulse'
                    : health?.status === 'ok'
                      ? 'bg-emerald-500'
                      : 'bg-rose-500'
                }`}
              />
              {loading
                ? 'Comprobando API...'
                : health?.status === 'ok'
                  ? 'API Conectada'
                  : 'API Desconectada'}
            </span>

            <button
              type="button"
              onClick={handleRetry}
              disabled={loading}
              className="px-3 py-1.5 text-xs font-medium rounded-lg border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 disabled:opacity-50 transition-colors cursor-pointer"
            >
              Reintentar
            </button>
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-5xl w-full mx-auto p-6">
        <div className="bg-white rounded-xl border border-slate-200 shadow-xs p-6">
          <h2 className="text-base font-semibold text-slate-800 mb-2">
            Estado de la conexión Front-end ↔ Back-end (<code>/health</code>)
          </h2>

          {loading && (
            <p className="text-sm text-slate-500">
              Consultando endpoint <code>GET /health</code>...
            </p>
          )}

          {!loading && health && (
            <div className="mt-3 p-4 rounded-lg bg-slate-50 border border-slate-200 font-mono text-xs text-slate-700 space-y-1">
              <div>
                <span className="text-slate-400">status:</span> {health.status}
              </div>
              <div>
                <span className="text-slate-400">service:</span>{' '}
                {health.service}
              </div>
              <div>
                <span className="text-slate-400">version:</span>{' '}
                {health.version}
              </div>
            </div>
          )}

          {!loading && error && (
            <div className="mt-3 p-4 rounded-lg bg-rose-50 border border-rose-200 text-sm text-rose-700">
              <p className="font-medium">
                No se ha podido conectar con el back-end ({error}).
              </p>
              <p className="text-xs text-rose-600 mt-1">
                Asegúrate de tener FastAPI corriendo con:{' '}
                <code className="bg-rose-100 px-1.5 py-0.5 rounded">
                  uv run fastapi dev app/main.py
                </code>
              </p>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

export default App
