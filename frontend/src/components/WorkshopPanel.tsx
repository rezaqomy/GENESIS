import type { Agent, AssemblyDesign, Building } from '../types/world'

function Parts({design}:{design:AssemblyDesign}) {
  return <p className="helper">{design.parts.map(p=>`${p.count}× ${p.material} ${p.shape}`).join(' + ')} · {design.joint} joints · {design.mechanism}{design.enclosed?' · enclosed':''}</p>
}
export function WorkshopPanel({agent,buildings}:{agent:Agent;buildings:Building[]}) {
  const k=agent.workshop
  const devices=buildings.filter(b=>b.assembly&&b.owner_id===agent.id)
  return <>
    <h3>Creative workshop</h3>
    <p className="helper">Ideas become physical experiments. Parts, connections and enclosure determine measured effects. A name or spoken promise grants no capability.</p>
    <dl className="details"><div><dt>Shared ideas</dt><dd>{k?.proposals.length??0}</dd></div><div><dt>Device trials</dt><dd>{k?.trials.length??0}</dd></div><div><dt>Devices fabricated</dt><dd>{devices.length}</dd></div></dl>
    {k?.experiment&&<><h3>Testing {k.experiment.name} · {k.steps}/3</h3><Parts design={k.experiment}/></>}
    {(k?.proposals??[]).map((d,i)=><details key={i}><summary>Untested idea · {d.name}</summary><Parts design={d}/></details>)}
    {[...(k?.trials??[])].slice(-10).reverse().map((t,i)=><details key={i}><summary>T{t.tick} · {t.design.name}</summary><Parts design={t.design}/><dl className="details">{Object.entries(t.measured).map(([key,value])=><div key={key}><dt>{key}</dt><dd>{Math.round(value*100)}%</dd></div>)}</dl><p className="helper">{t.feedback.join(' ')}</p></details>)}
    {devices.map(b=><details key={b.id}><summary>{b.assembly!.design.name} · {b.durability>0?`${b.durability}% durability`:'dismantled / broken'}</summary><p className="helper">At {b.position.x}, {b.position.y} · food produced {b.food}</p></details>)}
    <h3>Transformation evidence</h3>
    {Object.entries(k?.transformations??{}).map(([input,result])=><p className="helper" key={input}>{input.replace(':',' at ')} heat → {result}</p>)}
    {!Object.keys(k?.transformations??{}).length&&<p className="helper">No heating trials yet. Temperature and inputs must be tested.</p>}
    {k?.offer&&<><h3>Barter offer</h3><p className="helper">{k.offer.give_amount} {k.offer.give_item} for {k.offer.want_amount} {k.offer.want_item} · expires T{k.offer.expires}. Goods move only after acceptance.</p></>}
  </>
}
