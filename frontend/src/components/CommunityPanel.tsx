import type { Agent, Building, CommunityState, Inventory } from '../types/world'

const workLabels:Record<string,string>={care:'Care',food_supply:'Food supply',materials:'Material supply',construction:'Construction',maintenance:'Maintenance',farming:'Irrigation'}
export function CommunityPanel({community,agents,buildings,storage}:{community?:CommunityState|null;agents:Record<string,Agent>;buildings:Record<string,Building>;storage:Inventory}) {
  if(!community)return <p className="helper">Shared projects appear when someone posts a local need. Contributions count completed actions, not spoken promises.</p>
  const project=community.projects.find(p=>p.status==='active')
  const site=project?Object.values(buildings).find(b=>b.kind===project.kind&&b.position.x===project.target.x&&b.position.y===project.target.y):undefined
  const funded=site&&site.durability>0&&site.progress>0
  return <section className="community-panel" aria-label="Community cooperation">
    <h3>Working together</h3>
    <p className="helper">{community.meals_given} meals given directly · {community.repairs} repairs · {community.projects_completed} public projects completed</p>
    {project?<><h4>Shared project: {project.kind.replaceAll('_',' ')}</h4><p className="helper">Proposed by {agents[project.proposer_id]?.name??project.proposer_id} · ({project.target.x}, {project.target.y})</p>
      <p>{Object.entries(project.cost).map(([k,n])=>`${k}: ${funded?'funded':`${Math.min(storage[k as keyof Inventory] as number,n)}/${n}`}`).join(' · ')}</p>
      <p className="helper">Construction {site?.durability?site.progress:0}% · {Object.keys(project.contributors).length} contributors</p>
      <p className="helper">Materials are pooled at camp. Members can supply, build, irrigate or maintain structures as their needs allow.</p></>:<p className="helper">No active public project.</p>}
    <h4>Observed contributions</h4><p className="helper">These are actions people have taken, not assigned professions.</p>
    {Object.entries(community.contributions).map(([id,work])=><div className="community-contributor" key={id}><b>{agents[id]?.name??id}</b><span>{Object.entries(work).sort((a,b)=>b[1]-a[1]).map(([k,n])=>`${workLabels[k]??k}: ${n}`).join(' · ')}</span></div>)}
    {!!community.projects.length&&<details><summary>Project history</summary>{community.projects.slice().reverse().map(p=><p className="helper" key={p.id}>{p.kind.replaceAll('_',' ')} · {p.status} · {Object.keys(p.contributors).length} contributors</p>)}</details>}
  </section>
}
