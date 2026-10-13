import { useState } from 'react'
import { useWorld } from '../stores/world'
export function Timeline() {
  const { events, snapshot } = useWorld()
  const [type, setType] = useState('all')
  const [agent, setAgent] = useState('all')
  const [follow, setFollow] = useState(true)
  const [hold, setHold] = useState<number | null>(null)
  const filtered = events.filter(e => e.payload.message && (type === 'all' || e.payload.action === type || e.event_type === type) && (agent === 'all' || e.actor_id === agent) && (follow || hold === null || e.sequence_number <= hold)).slice(-200).reverse()
  return <section className="timeline panel">
    <div className="timeline-header"><div><span className="eyebrow">WORLD JOURNAL</span><span className="journal-count">{events.length} recent events</span></div><div className="timeline-filters"><select aria-label="Filter event type" value={type} onChange={e=>setType(e.target.value)}><option value="all">All events</option>{['MOVE','GATHER','EAT','REST','IDLE','ACTION_REJECTED','AGENT_DIED','COMMAND_ACCEPTED'].map(v=><option key={v}>{v}</option>)}</select><select aria-label="Filter agent" value={agent} onChange={e=>setAgent(e.target.value)}><option value="all">All agents</option>{Object.values(snapshot?.state.agents ?? {}).map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select><button className={follow ? 'following' : ''} onClick={() => {setHold(snapshot?.sequence_number ?? null);setFollow(!follow)}}>{follow ? '● Live' : '○ Hold'}</button></div></div>
    <div className="event-list" tabIndex={0} aria-label="Scrollable world events">{filtered.length ? filtered.map(e => <div className="event-row" key={e.event_id}><span className="event-tick">T{String(e.tick).padStart(5,'0')}</span><span className={`event-symbol ${e.payload.action?.toLowerCase() ?? ''}`}>{({MOVE:'↗',GATHER:'✿',EAT:'◒',REST:'☾',IDLE:'·'} as Record<string,string>)[e.payload.action ?? ''] ?? '◇'}</span><p>{e.payload.message}</p><span className="event-tag">{e.payload.action ?? e.event_type.replaceAll('_',' ').toLowerCase()}</span></div>) : <div className="journal-empty">The journal is quiet. Start the world to follow its first steps.</div>}</div>
  </section>
}
