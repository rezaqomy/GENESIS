import type { Agent, MemoryRecord } from '../types/world'

function Experiences({records,recalled}:{records:MemoryRecord[];recalled:string[]}) {
  return <div className="recent-activity">{[...records].sort((a,b)=>b.tick-a.tick||a.id.localeCompare(b.id)).map(m=><p key={m.id}>
    <small>T{m.tick} · {m.kind}{recalled.includes(m.id)?' · recalled':''} · outcome {m.outcome.toFixed(2)}</small>{m.text}
  </p>)}{!records.length&&<p className="helper">No experiences retained here yet.</p>}</div>
}

export function MemoryPanel({agent:a,tick}:{agent:Agent;tick:number}) {
  const memory=a.memory
  if(!memory) return <><h3>Remembered experiences</h3><div className="recent-activity">{[...(a.memories??[])].reverse().map((m,i)=><p key={`${m.tick}-${i}`}><small>T{m.tick} · {m.kind}</small>{m.text}</p>)}<p className="helper">Layered memories appear when this agent next observes or acts.</p></div></>
  return <>
    <h3>Short-term memory · {memory.short_term.length} / 24</h3>
    <p className="helper">Recent actions and encounters. Important experiences are also retained long term.</p>
    <Experiences records={memory.short_term} recalled={memory.recalled_ids}/>
    <h3>Long-term memory · {memory.long_term.length} / 64</h3>
    <Experiences records={memory.long_term} recalled={memory.recalled_ids}/>
    <h3>Practical lessons</h3>
    <p className="helper">Outcomes influence goal scores in similar conditions. Positive means helpful; negative means unsuccessful.</p>
    {Object.entries(memory.lessons).map(([id,l])=><p className="factor" key={id}><span>{l.goal.replaceAll('_',' ')} · {l.action.toLowerCase()}<small> · {l.context} · {l.samples} attempts</small></span><b>{l.mean_outcome.toFixed(2)}</b></p>)}
    {!Object.keys(memory.lessons).length&&<p className="helper">Lessons develop from action outcomes.</p>}
    <h3>Known food locations · {Object.keys(memory.facts).length}</h3>
    <p className="helper">Last observed quantities may have changed. Older observations are less reliable.</p>
    {Object.values(memory.facts).sort((a,b)=>b.observed_tick-a.observed_tick||a.resource_id.localeCompare(b.resource_id)).map(f=><p className="factor" key={f.resource_id}><span>({f.position.x}, {f.position.y}) · {f.quantity} food<small> · observed T{f.observed_tick}</small></span><b>{Math.round(100/(1+Math.max(0,tick-f.observed_tick)/48))}% confidence</b></p>)}
  </>
}
