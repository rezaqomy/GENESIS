import { useWorld } from '../stores/world'
export function SettlementDashboard() {
  const {snapshot,select,focus,fps,renderedChunks,fallbackAssets} = useWorld()
  const s=Object.values(snapshot?.state.settlements??{})[0]
  if(!s) return null
  return <section className="settlement-dashboard"><div className="section-line"><span className="eyebrow">SETTLEMENT</span><button onClick={()=>focus(s.center)}>⌖ {s.name}</button></div><div className="settlement-stats">{[['Population',s.members.filter(id=>snapshot?.state.agents[id]?.alive).length],['Food',s.food_reserves],['Buildings',s.buildings.length],['Explorers',s.exploration_activity]].map(([k,v])=><div key={k}><b>{v}</b><small>{k}</small></div>)}</div>
    {(['safety','comfort','social_cohesion','resource_availability','crowding'] as const).map(k=><div className="settlement-meter" key={k}><span>{k.replaceAll('_',' ')}</span><meter min="0" max="1" value={s[k]}/><b>{Math.round(s[k]*100)}%</b></div>)}
    <div className="settlement-members">{s.members.map(id=>{const a=snapshot?.state.agents[id];return a?<button key={id} onClick={()=>{select(id);focus(a.position)}}>{a.name}</button>:null})}</div>
    <details className="performance"><summary>Performance · {Math.round(fps)} FPS</summary><p>Tick {snapshot?.metrics?.tick_duration_ms.toFixed(1)} ms · decisions {snapshot?.metrics?.decision_duration_ms.toFixed(1)} ms</p><p>{snapshot?.metrics?.active_chunks} active · {snapshot?.metrics?.loaded_chunks} cached · {renderedChunks} visible chunks</p><p>{Math.round((snapshot?.metrics?.payload_bytes??0)/1024)} KB update · {fallbackAssets} missing assets</p></details>
  </section>
}
