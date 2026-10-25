import { useWorld } from '../stores/world'

export function WorldPulse() {
  const snapshot=useWorld(s=>s.snapshot)
  const world=snapshot?.state
  const people=Object.values(world?.agents??{}).filter(a=>a.alive)
  const animals=Object.values(world?.ecosystem?.animals??{})
  const crops=Object.values(world?.ecosystem?.crops??{}).filter(c=>c.health>0)
  const buildings=Object.values(world?.buildings??{}).filter(b=>b.progress===100&&b.durability>0)
  const cards=[
    {label:'Lives unfolding',value:people.length,icon:'item_food',detail:people.length?`${Math.round(people.reduce((n,a)=>n+a.health,0)/people.length)}% average health`:'Waiting for a world',tone:'sage'},
    {label:'Wildlife',value:animals.length,icon:'fiber_plant',detail:`${animals.filter(a=>a.owner_id).length} animals tamed`,tone:'blue'},
    {label:'Growing things',value:crops.length,icon:'crops',detail:`${crops.filter(c=>c.growth===80).length} ready to harvest`,tone:'gold'},
    {label:'Creations',value:buildings.length,icon:'workbench',detail:`${buildings.filter(b=>b.kind==='assembly').length} working inventions`,tone:'clay'},
  ]
  return <section className="world-pulse" aria-label="World at a glance">{cards.map(c=><div className={`pulse-card ${c.tone}`} key={c.label}><div className="pulse-icon"><img src={`/assets/genesis/${c.icon}.png`} alt=""/></div><div><span>{c.label}</span><strong>{snapshot?c.value:'—'}</strong><small>{c.detail}</small></div></div>)}</section>
}
