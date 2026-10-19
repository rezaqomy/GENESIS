import { useState } from 'react'
import { useWorld } from '../stores/world'
import { resourceKinds } from '../types/world'
import { SettlementDashboard } from './Settlement'
import { MemoryPanel } from './MemoryPanel'
import { TaskPanel } from './TaskPanel'
import { VisionPanel } from './VisionPanel'
import { EngineeringPanel } from './EngineeringPanel'
function Meter({label,value,color='#8bbc9c'}:{label:string;value:number;color?:string}) {
  return <div className="meter"><div><span>{label.replaceAll('_',' ')}</span><b>{Math.round(value)}<small> / 100</small></b></div><div className="meter-track"><i style={{width:`${Math.max(0,Math.min(100,value))}%`,background:color}}/></div></div>
}
const tabs=['Overview','Vision','Personality','Decision','Plans','Building','Inventory','Social','Memory','History'] as const
export function Inspector() {
  const {snapshot,selected,select,events,focus}=useWorld()
  const [tab,setTab]=useState<typeof tabs[number]>('Overview')
  const agents=Object.values(snapshot?.state.agents??{})
  const a=selected?snapshot?.state.agents[selected]:null
  const history=events.filter(e=>e.actor_id===selected&&e.payload.message).slice(-30).reverse()
  return <aside className="inspector panel"><div className="section-line"><span className="eyebrow">AGENT INSPECTOR</span><span className="muted">↗</span></div>
    {a?<><div className="agent-profile"><div className="portrait" style={{backgroundColor:a.visual_color+'35'}}><img src={`/assets/genesis/character-${Number(a.id.slice(-2))%4}.png`} alt="" onError={e=>{e.currentTarget.style.display='none'}}/></div><div><h2>{a.name}</h2><p>{a.age} years old · {a.alive?'Alive':'Deceased'}</p><span className="agent-action">{a.current_action.toLowerCase()}</span></div><button className="close" aria-label="Clear selection" onClick={()=>select(null)}>×</button></div>
    <nav className="inspector-tabs" aria-label="Agent details">{tabs.map(t=><button key={t} aria-pressed={tab===t} className={tab===t?'chosen':''} onClick={()=>setTab(t)}>{t}</button>)}</nav><div className="inspector-content">
      {tab==='Overview'&&<><Meter label="Health" value={a.health}/><Meter label="Hunger" value={a.hunger} color="#d9ae74"/><Meter label="Energy" value={a.energy} color="#86acc7"/><p className="helper">Higher hunger means closer to starvation.</p><p className="helper">{!a.alive?'Life ended':a.hunger>=100?'Starving · health declines gradually':a.hunger>=65?'Hungry · finding food takes priority':'Food needs are manageable'} · {a.inventory.food} meals carried</p><Meter label="Mood" value={a.psychology.mood*100}/><Meter label="Safety" value={a.psychology.sense_of_safety*100}/><dl className="details"><div><dt>Goal</dt><dd>{a.decision.selected_goal.replaceAll('_',' ')}</dd></div><div><dt>Position</dt><dd>{a.position.x}, {a.position.y}</dd></div><div><dt>Destination</dt><dd>{a.destination?`${a.destination.x}, ${a.destination.y}`:'—'}</dd></div><div><dt>Lifestyle</dt><dd>{a.lifestyle}</dd></div></dl><button className="secondary" onClick={()=>focus(a.position)}>Focus camera</button></>}
      {tab==='Personality'&&Object.entries(a.personality).map(([k,v])=><Meter key={k} label={k} value={v*100}/>)}
      {tab==='Decision'&&<><p className="helper">Decision source: {a.cognition_source??'utility'}</p>{a.thought&&<blockquote>{a.thought}</blockquote>}<h3>{a.decision.selected_goal.replaceAll('_',' ')}</h3><p className="helper">Committed through tick {a.decision.commitment_until} · {a.decision.failures} recent failures</p><Meter label="Goal progress" value={a.decision.progress*100}/><ol className="plan">{a.decision.plan.map((p,i)=><li key={i}>{p}</li>)}</ol><div className="utility-list">{[...a.decision.candidates].sort((a,b)=>b.utility-a.utility).map(c=><details key={c.goal} className={c.goal===a.decision.selected_goal?'selected-goal':''}><summary><span>{c.goal.replaceAll('_',' ')}</span><b>{c.utility.toFixed(3)}</b></summary><div className="utility-bar"><i style={{width:`${c.utility*100}%`}}/></div>{c.rejection?<p className="helper">Unavailable: {c.rejection}</p>:Object.entries(c.factors).map(([k,v])=><p className="factor" key={k}><span>{k.replaceAll('_',' ')}</span><b>{v>=0?'+':''}{v.toFixed(3)}</b></p>)}</details>)}</div></>}
      {tab==='Inventory'&&<><div className="section-caption">CAPACITY <span>{resourceKinds.reduce((n,k)=>n+a.inventory[k],0)+Object.values(a.inventory.tools).filter(v=>v>0).length} / {a.inventory.capacity}</span></div><div className="inventory">{resourceKinds.map(k=><div key={k}><img className="item-icon" src={`/assets/genesis/item_${k==='water'?'water_item':k}.png`} alt=""/><b>{a.inventory[k]}</b><small>{k}</small></div>)}</div><h3>Tools</h3>{Object.entries(a.inventory.tools).map(([k,v])=><Meter key={k} label={`${k} durability`} value={v}/>)}{!Object.keys(a.inventory.tools).length&&<p className="helper">No tools carried.</p>}</>}
      {tab==='Social'&&<><dl className="details"><div><dt>Community</dt><dd>{a.settlement_id?snapshot?.state.settlements[a.settlement_id]?.name:'Independent'}</dd></div><div><dt>Time away</dt><dd>{a.time_away} ticks</dd></div><div><dt>Known regions</dt><dd>{a.known_chunks.length}</dd></div></dl>{(['loneliness','social_satisfaction','attachment','homesickness','stress','fear'] as const).map(k=><Meter key={k} label={k} value={a.psychology[k]*100}/>)}<h3>Nearby companions</h3>{a.nearby_agents.map(id=><p key={id}>{snapshot?.state.agents[id]?.name} · affinity {Math.round((a.relationships[id]??0)*100)}%</p>)}</>}
      {tab==='Plans'&&<TaskPanel agent={a} tick={snapshot?.state.tick??0}/>}
      {tab==='Building'&&<EngineeringPanel agent={a} buildings={Object.values(snapshot?.state.buildings??{})}/>}
      {tab==='Vision'&&snapshot&&<VisionPanel agentId={a.id} runId={snapshot.run_id} tick={snapshot.state.tick}/>}
      {tab==='Memory'&&<MemoryPanel agent={a} tick={snapshot?.state.tick??0}/>}
      {tab==='History' &&<div className="recent-activity">{history.map(e=><p key={e.event_id}><small>T{e.tick}</small>{e.payload.message}</p>)}{!history.length&&<p className="helper">This life is just beginning.</p>}</div>}
    </div></>:<div className="inspector-empty"><div className="empty-icon">♙</div><h2>Every life has a story.</h2><p>Select a character to understand<br/>what matters to them.</p></div>}
    <div className="roster"><div className="section-caption">INHABITANTS <span>{agents.filter(a=>a.alive).length} ALIVE</span></div><div className="roster-grid">{agents.map(a=><button className={selected===a.id?'selected':''} key={a.id} onClick={()=>select(a.id)} aria-label={`Inspect ${a.name}`}><i style={{background:a.visual_color,opacity:a.alive?1:.3}}/>{a.name}</button>)}</div></div><SettlementDashboard/>
  </aside>
}
