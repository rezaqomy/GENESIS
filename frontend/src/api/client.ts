import { useWorld } from '../stores/world'
import type { Snapshot } from '../types/world'
export async function control(command: string, body?: object) {
  useWorld.setState({ pending: true, error: null })
  try {
    const response = await fetch(`/api/simulation/${command}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined })
    if (!response.ok) {
      const error = await response.json()
      throw new Error(typeof error.detail === 'string' ? error.detail : 'Invalid simulation command')
    }
    useWorld.getState().accept(await response.json() as Snapshot)
  } catch (error) {
    useWorld.setState({ error: error instanceof Error ? error.message : 'The server could not be reached' })
  } finally { useWorld.setState({ pending: false }) }
}
