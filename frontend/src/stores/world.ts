import { create } from 'zustand'
import type { Snapshot, WorldEvent } from '../types/world'
interface Store {
  snapshot: Snapshot | null
  selected: string | null
  connection: 'connecting' | 'live' | 'reconnecting'
  error: string | null
  pending: boolean
  events: WorldEvent[]
  accept: (snapshot: Snapshot) => void
  select: (id: string | null) => void
}
export const useWorld = create<Store>((set) => ({
  snapshot: null, selected: null, connection: 'connecting', error: null, pending: false, events: [],
  accept: (snapshot) => set((previous) => {
    if (snapshot.run_id === previous.snapshot?.run_id && snapshot.sequence_number < previous.snapshot.sequence_number) return {}
    const sameRun = snapshot.run_id === previous.snapshot?.run_id
    const events = new Map((sameRun ? previous.events : []).map(e => [e.event_id, e]))
    snapshot.events.forEach(e => events.set(e.event_id, e))
    return { snapshot, events: [...events.values()].sort((a,b) => a.sequence_number-b.sequence_number).slice(-1500),
      selected: sameRun ? previous.selected : null }
  }),
  select: (selected) => set({ selected }),
}))
