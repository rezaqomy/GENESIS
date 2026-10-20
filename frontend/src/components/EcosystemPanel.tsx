import type { Agent, World, Position } from '../types/world'

export function EcosystemPanel({agent,world}:{agent:Agent;world:World}) {
  const e=world.ecosystem
  const local=(p:Position)=>agent.alive&&Math.abs(p.x-agent.position.x)+Math.abs(p.y-agent.position.y)<=(agent.vision_radius??8)
  const animals=Object.values(e?.animals??{}).filter(a=>local(a.position))
  const crops=Object.values(e?.crops??{}).filter(c=>local(c.position))
  const drops=Object.values(e?.drops??{}).filter(d=>local(d.position))
  return <div>
    <p className="helper">Life and supplies within this agent’s base sight range.</p>
    <h3>Animals · {animals.length}</h3>
    {animals.map(a=><details key={a.id}><summary>{a.species} · {world.tick-a.born_tick<240?'juvenile':a.owner_id?`tame · ${world.agents[a.owner_id]?.name??a.owner_id}`:'wild'}</summary><p className="helper">Health {a.health}/40 · Hunger {a.hunger}/100 · Trust {a.trust}/3</p><p className="helper">{a.position.x}, {a.position.y} · {a.ready_until>=world.tick?'Fed for breeding':'Needs feeding before breeding'}</p></details>)}
    {!animals.length&&<p className="helper">No animals in sight.</p>}
    <h3>Crops · {crops.length}</h3>
    {crops.map(c=><div key={c.id}><p>{c.health===0?'Failed crop':c.growth===80?'Ready to harvest':`Growing · ${Math.round(c.growth/80*100)}%`} · {world.agents[c.owner_id]?.name??c.owner_id}</p><p className="helper">Moisture {c.moisture}/100 · Health {c.health}/100 · {c.position.x}, {c.position.y}</p><progress aria-label="Crop growth" max={80} value={c.growth}/></div>)}
    {!crops.length&&<p className="helper">No crops in sight.</p>}
    <h3>Dropped belongings · {drops.length}</h3>
    {drops.map(d=><p className="helper" key={d.id}>{d.position.x}, {d.position.y} · {d.owner_id?world.agents[d.owner_id]?.name??d.owner_id:'Wild supplies'} · Decays in {Math.max(0,d.expires-world.tick)} ticks</p>)}
    {agent.combat?.attacker_id&&<p className="helper">Last attacked by {world.agents[agent.combat.attacker_id]?.name??agent.combat.attacker_id} at tick {agent.combat.attacked_tick}.</p>}
  </div>
}
