import { useWorld } from '../stores/world'
import type { Agent } from '../types/world'
function Portrait({ agent }: { agent: Agent }) {
  return <div className="portrait" style={{'--shirt': agent.visual_color} as React.CSSProperties}><div className="pixel-person"><i className="hair"/><i className="head"/><i className="shirt"/><i className="arm left"/><i className="arm right"/><i className="leg left"/><i className="leg right"/></div></div>
}
function Meter({ label, value, color }: {label:string; value:number; color:string}) {
  return <div className="meter"><div><span>{label}</span><b>{value}<small> / 100</small></b></div><div className="meter-track"><i style={{width:`${value}%`,background:color}} /></div></div>
}
export function Inspector() {
  const { snapshot, selected, select, events } = useWorld()
  const agents = Object.values(snapshot?.state.agents ?? {})
  const agent = selected ? snapshot?.state.agents[selected] : null
  const recent = events.filter(e => e.actor_id === selected).slice(-4).reverse()
  return <aside className="inspector panel">
    <div className="section-line"><span className="eyebrow">AGENT INSPECTOR</span><span className="muted">↗</span></div>
    {agent ? <>
      <div className="agent-profile"><Portrait agent={agent}/><div><h2>{agent.name}</h2><p>{agent.age} years old <span>·</span> {agent.alive ? 'Alive' : 'Deceased'}</p><span className="agent-action">{agent.current_action.toLowerCase()}</span></div><button className="close" aria-label="Clear selection" onClick={() => select(null)}>×</button></div>
      <div className="section-caption">VITAL SIGNS</div>
      <Meter label="Health" value={agent.health} color="#8bbc9c"/><Meter label="Hunger" value={agent.hunger} color="#d9ae74"/><Meter label="Energy" value={agent.energy} color="#86acc7"/>
      <p className="helper">Higher hunger means closer to starvation.</p>
      <div className="divider"/><div className="section-caption">IN THE WORLD</div>
      <dl className="details"><div><dt>Position</dt><dd>{agent.position.x}, {agent.position.y}</dd></div><div><dt>Destination</dt><dd>{agent.destination ? `${agent.destination.x}, ${agent.destination.y}` : '—'}</dd></div><div><dt>Current action</dt><dd>{agent.current_action}</dd></div></dl>
      <div className="section-caption">INVENTORY <span>{agent.inventory.food+agent.inventory.wood}/{agent.inventory.capacity}</span></div>
      <div className="inventory"><div><span>✿</span><b>{agent.inventory.food}</b><small>Food</small></div><div><span>♧</span><b>{agent.inventory.wood}</b><small>Wood</small></div></div>
      <div className="divider"/><div className="section-caption">RECENT ACTIVITY</div><div className="recent-activity">{recent.length ? recent.map(e => <p key={e.event_id}><small>T{e.tick}</small>{e.payload.message}</p>) : <p className="muted">This life is just beginning.</p>}</div>
    </> : <div className="inspector-empty"><div className="empty-icon">♙</div><h2>Every life has a story.</h2><p>Select a character in the world<br/>to see what they’re doing.</p></div>}
    <div className="roster"><div className="section-caption">INHABITANTS <span>{agents.filter(a=>a.alive).length} ALIVE</span></div><div className="roster-grid">{agents.map(a => <button className={selected === a.id ? 'selected' : ''} key={a.id} onClick={() => select(a.id)} aria-label={`Inspect ${a.name}`}><i style={{background:a.visual_color,opacity:a.alive?1:.3}}/>{a.name}</button>)}</div></div>
  </aside>
}
