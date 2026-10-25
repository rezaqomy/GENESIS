import { WorkshopPanel } from './WorkshopPanel'
import type { Agent, Building, ShelterDesign, ToolDesign } from '../types/world'

function describeTool(d:ToolDesign) {
  return `${d.core} ${d.form} · ${d.grip} grip (${d.length}) · ${d.binding} binding${d.fueled?' · fueled':''}`
}

function describe(d:ShelterDesign) {
  return `${d.frame} frame · ${d.roof} roof · ${d.bracing?'braced':'unbraced'} · ${d.raised_foundation?'raised foundation':'ground foundation'}`
}
export function EngineeringPanel({agent,buildings}:{agent:Agent;buildings:Building[]}) {
  const k=agent.housing
  const tools=agent.inventions
  return <>
    <WorkshopPanel agent={agent} buildings={buildings}/>
    <h3>Invention workshop</h3>
    <p className="helper">Assemblies are discovered through material and load tests. A failed prototype leaves evidence for the next attempt. One design can have several uses.</p>
    <dl className="details">
      <div><dt>Tool practice</dt><dd>{tools?.practice??0}</dd></div>
      <div><dt>Remembered trials</dt><dd>{tools?.trials.length??0}</dd></div>
      <div><dt>Learned assemblies</dt><dd>{Object.keys(tools?.designs??{}).length}</dd></div>
    </dl>
    {tools?.experiment&&<><h3>Tool experiment · {tools.experiment_steps}/3</h3><p>{describeTool(tools.experiment)}</p><p className="helper">{tools.studying_peer?'Reconstructing an adjacent maker’s tool':'Testing a new assembly'}</p></>}
    {Object.entries(tools?.designs??{}).map(([id,trial])=><details key={id}>
      <summary>{describeTool(trial.design)}</summary>
      <p>Durability: {agent.inventory.tools[id]??0} uses · cut {Math.round(trial.performance.cut*100)}% · mine {Math.round(trial.performance.mine*100)}% · light {Math.round(trial.performance.light*100)}%</p>
    </details>)}
    <h3>Recent tool evidence</h3>
    {[...(tools?.trials??[])].slice(-8).reverse().map((trial,i)=><details key={`${trial.tick}:${i}`}>
      <summary>T{trial.tick} · {Math.max(...Object.values(trial.performance))>=0.3?'Useful prototype':'Prototype failed'}</summary>
      <p>{describeTool(trial.design)}</p><p className="helper">{trial.feedback.join(' ')}</p>
    </details>)}
    {!tools?.trials.length&&<p className="helper">No tool knowledge yet. Naming a tool does not unlock its construction.</p>}
    <h3>Construction learning</h3>
    <p className="helper">Shelter designs become usable after three steps of prototyping or local study. A standing prototype has not yet proven it can survive a storm. Practice changes actual workmanship.</p>
    <dl className="details">
      <div><dt>Practice</dt><dd>{k?.practice??0}</dd></div>
      <div><dt>Design trials</dt><dd>{k?.trials.length??0}</dd></div>
      <div><dt>Observed collapses</dt><dd>{Object.keys(k?.observed_failures??{}).length}</dd></div>
    </dl>
    {k?.experiment&&<><h3>Current experiment · {k.experiment_steps}/3</h3><p>{describe(k.experiment)}</p><p className="helper">{k.studying_id?'Studying a nearby structure':'Testing a prototype'}</p></>}
    <h3>Lessons from damage</h3>
    {k?.insights.length?<p>{k.insights.join(' · ')}</p>:<p className="helper">No structural damage witnessed yet.</p>}
    <h3>Tested designs</h3>
    {[...(k?.trials??[])].reverse().map((trial,i)=><details key={`${trial.tick}:${i}`}>
      <summary>T{trial.tick} · {trial.stood?'Prototype stood':'Prototype failed'} · {Math.round(trial.score*100)}% measured load score</summary>
      <p>{describe(trial.design)}</p><p className="helper">{trial.source==='study'?'Learned through local study':'Learned through experiment'}. A load score is evidence, not guaranteed storm resistance.</p>
    </details>)}
    {!k?.trials.length&&<p className="helper">No shelter design learned yet.</p>}
    <h3>Built structures</h3>
    {buildings.filter(b=>b.contributors?.includes(agent.id)).map(b=><details key={b.id}>
      <summary>{b.kind.replaceAll('_',' ')} · {b.durability===0?'Collapsed':`${b.progress}% built`}</summary>
      <p>Workmanship {Math.round((b.quality??1)*100)}% · durability {b.durability}%</p>
      {b.design&&<p>{describe(b.design)}</p>}
      {b.last_damage_cause&&<p className="helper">Last damage: {b.last_damage_cause}</p>}
    </details>)}
  </>
}
