import type { HealthResponse } from '../types'

/**
 * Comprueba la conexión con el back-end FastAPI a través del endpoint /health.
 * En desarrollo, Vite redirige /health hacia http://127.0.0.1:8000/health.
 */
export async function checkBackendHealth(): Promise<HealthResponse> {
  const response = await fetch('/health', {
    headers: {
      Accept: 'application/json',
    },
  })

  if (!response.ok) {
    throw new Error(`Error HTTP: ${response.status}`)
  }

  return response.json() as Promise<HealthResponse>
}
