import { create } from 'zustand'
import type { ChunkMessage, ChunkView, Position, Snapshot, WorldEvent } from '../types/world'
interface Store {
  snapshot: Snapshot | null; selected: string | null
  connection: 'connecting' | 'live' | 'reconnecting'; error: string | null; pending: boolean
  events: WorldEvent[]; chunks:Record<string,ChunkView>
  fps:number;renderedChunks:number;fallbackAssets:number
  cameraBounds:{left:number;top:number;right:number;bottom:number}|null
  cameraRequest:{position:Position;serial:number}|null
  follow:boolean;effects:boolean
  accept: (snapshot: Snapshot) => void; acceptChunks:(packet:ChunkMessage)=>void
  select: (id: string | null) => void;focus:(position:Position)=>void
}
export const useWorld = create<Store>((set) => ({
  snapshot: null, selected: null, connection: 'connecting', error: null, pending: false, events: [],
  chunks:{},fps:0,renderedChunks:0,fallbackAssets:0,cameraBounds:null,cameraRequest:null,follow:false,effects:true,
  accept: (snapshot) => set((previous) => {
    if (snapshot.run_id === previous.snapshot?.run_id && snapshot.sequence_number < previous.snapshot.sequence_number) return {}
    const sameRun = snapshot.run_id === previous.snapshot?.run_id
    const events = new Map((sameRun ? previous.events : []).map(e => [e.event_id, e]))
    snapshot.events.forEach(e => events.set(e.event_id, e))
    return { snapshot, events: [...events.values()].sort((a,b) => a.sequence_number-b.sequence_number).slice(-1500),
      selected: sameRun ? previous.selected : null, chunks:sameRun?previous.chunks:{},follow:sameRun?previous.follow:false }
  }),
  acceptChunks:packet=>set(previous=>{
    if(packet.run_id!==previous.snapshot?.run_id) return {}
    const chunks={...previous.chunks}
    packet.chunks.forEach(chunk=>{ delete chunks[chunk.key];chunks[chunk.key]=chunk })
    const keys=Object.keys(chunks)
    keys.slice(0,Math.max(0,keys.length-48)).forEach(key=>delete chunks[key])
    return {chunks}
  }),
  select: (selected) => set({ selected }),
  focus:position=>set(s=>({cameraRequest:{position,serial:(s.cameraRequest?.serial??0)+1}})),
}))
