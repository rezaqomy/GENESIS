import { useState } from 'react'
import { useWorld } from '../stores/world'
import type { WorldEvent } from '../types/world'
export function Timeline() {
  const runId=useWorld(state=>state.snapshot?.run_id)
  return <Journal key={runId}/>
}
function Journal(){
  const events=useWorld(state=>state.events)
  const snapshot=useWorld(state=>state.snapshot)
  const [type, setType] = useState('all')
  const [highlights,setHighlights]=useState(true)
  const [agent, setAgent] = useState('all')
  const [hold, setHold] = useState<WorldEvent[] | null>(null)
  const follow=hold===null
  const shown=hold??events
  const quietActions=['MOVE','IDLE','REST','GATHER','STORE','WITHDRAW']
  const quietEvents=['GOAL_SELECTED','NAVIGATION_ADJUSTED','ACTION_REJECTED','COMMAND_ACCEPTED']
  const filtered = shown.filter(e => e.payload.message && (type === 'all' || e.payload.action === type || e.event_type === type) && (!highlights||type!=='all'||(!quietActions.includes(e.payload.action??'')&&!quietEvents.includes(e.event_type)&&!/[12]\/3/.test(e.payload.message))) && (agent === 'all' || e.actor_id === agent || e.payload.peer_id === agent)).slice(-200).reverse()
  return <section className="timeline panel">
    <div className="timeline-header"><div><span className="eyebrow">WORLD JOURNAL</span><button className="journal-mode" aria-pressed={highlights} onClick={()=>setHighlights(!highlights)}>{highlights?'✧ Highlights':'All activity'}</button><span className="journal-count">{filtered.length} moments</span></div><div className="timeline-filters"><select aria-label="Filter event type" value={type} onChange={e=>setType(e.target.value)}><option value="all">All events</option>{['TILL','PLANT','WATER_CROP','HARVEST','FEED','BREED','COLLECT','ATTACK','STEAL','PICK_UP','ANIMAL_APPEARED','ANIMAL_DIED','CROP_RIPENED','ITEMS_DROPPED','EXPERIMENT_ASSEMBLY','ASSEMBLE','OPERATE','HEAT','DISMANTLE','OFFER_TRADE','ACCEPT_TRADE','DIG','MINE','PLACE_BLOCK','GIVE','REPAIR','PROPOSE_PROJECT','COMMUNITY_PROJECT_COMPLETED','COMMUNITY_PROJECT_EXPIRED','MOVE','GATHER','EAT','REST','IDLE','BUILD','EXPERIMENT','EXPERIMENT_TOOL','DISCARD','BUILDING_DAMAGED','BUILDING_COLLAPSED','CRAFT','STORE','WITHDRAW','REFUEL','SOCIALIZE','DIALOGUE','GOAL_SELECTED','ACTION_REJECTED','AGENT_DIED','COMMAND_ACCEPTED'].map(v=><option key={v}>{v}</option>)}</select><select aria-label="Filter agent" value={agent} onChange={e=>setAgent(e.target.value)}><option value="all">All agents</option>{Object.values(snapshot?.state.agents ?? {}).map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select><button className={follow ? 'following' : ''} onClick={() => {setHold(follow?[...events]:null)}}>{follow ? '● Live' : '○ Hold'}</button></div></div>
    <div className="event-list" tabIndex={0} aria-label="Scrollable world events">{filtered.length ? filtered.map(e => <div className="event-row" key={e.event_id}><span className="event-tick">T{String(e.tick).padStart(5,'0')}</span><span className={`event-symbol ${e.payload.action?.toLowerCase() ?? ''}`}>{({MOVE:'↗',GATHER:'✿',EAT:'◒',REST:'☾',IDLE:'·'} as Record<string,string>)[e.payload.action ?? ''] ?? '◇'}</span><p>{e.payload.message}</p><span className="event-tag">{e.payload.action ?? e.event_type.replaceAll('_',' ').toLowerCase()}</span></div>) : <div className="journal-empty">{highlights?'The next discovery is still taking shape. Try All activity to see every step.':'The journal is quiet. Start the world to follow its first steps.'}</div>}</div>
  </section>
}
