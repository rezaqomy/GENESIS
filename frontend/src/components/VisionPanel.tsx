import { useEffect, useState } from 'react'
import type { Agent, Building, Position, Resource } from '../types/world'

interface Perception {
  tick:number; vision_radius:number; self_agent:Agent
  tiles:{position:Position}[];resources:Resource[];buildings:Building[]
  peers:{id:string;name:string;position:Position}[];settlement:{name:string}|null
}

export function VisionPanel({agentId,runId,tick}:{agentId:string;runId:string;tick:number}) {
  const [result,setResult]=useState<{run_id:string;observation:Perception}|null>(null)
  const [failed,setFailed]=useState(false)
  useEffect(()=>{
    const controller=new AbortController()
    fetch(`/api/agents/${encodeURIComponent(agentId)}/observation`,{signal:controller.signal})
      .then(response=>{if(!response.ok)throw new Error('Observation unavailable');return response.json()})
      .then(data=>{if(!controller.signal.aborted){setResult(data);setFailed(false)}})
      .catch(()=>{if(!controller.signal.aborted)setFailed(true)})
    return ()=>controller.abort()
  },[agentId,runId,tick])
  const o=result?.run_id===runId&&result.observation.self_agent.id===agentId?result.observation:null
  if(failed)return <p className="helper">Vision unavailable. Retrying on the next update.</p>
  if(!o)return <p className="helper">Loading local view…</p>
  return <>
    <h3>Local vision · {o.vision_radius} tiles</h3>
    <p className="helper">Observed at tick {o.tick}. Range follows grid distance. The map camera shows the world; this agent receives only the local view below. Remembered places can remain known after leaving sight.</p>
    <dl className="details">
      <div><dt>Visible terrain</dt><dd>{o.tiles.length} tiles</dd></div>
      <div><dt>Visible resources</dt><dd>{o.resources.length}</dd></div>
      <div><dt>Visible buildings</dt><dd>{o.buildings.length}</dd></div>
      <div><dt>Visible companions</dt><dd>{o.peers.length}</dd></div>
      <div><dt>Local settlement supplies</dt><dd>{o.settlement?.name??'Outside sight'}</dd></div>
    </dl>
    <h3>Companions in sight</h3>
    {o.peers.map(p=><p key={p.id}>{p.name} · {p.position.x}, {p.position.y}</p>)}
    {!o.peers.length&&<p className="helper">No companions in sight.</p>}
    <h3>Resources in sight</h3>
    {o.resources.map(r=><p key={r.id}>{r.kind} × {r.quantity} · {r.position.x}, {r.position.y}</p>)}
  </>
}
