import type { Agent } from '../types/world'

export function TaskPanel({agent:a,tick}:{agent:Agent;tick:number}) {
  const task=a.task
  return <>
    <h3>Current plan</h3>
    {task?<><p><b>{task.kind} · {task.status}</b></p><dl className="details">
      <div><dt>Stage</dt><dd>{task.stage}</dd></div>
      <div><dt>Started</dt><dd>Tick {task.started_tick}</dd></div>
      <div><dt>Time remaining</dt><dd>{task.status==='active'?Math.max(0,task.deadline-tick):0} ticks</dd></div>
      <div><dt>Actions / energy spent</dt><dd>{task.actions} / {task.energy_spent}</dd></div>
      <div><dt>Last progress</dt><dd>Tick {task.last_progress_tick}</dd></div>
    </dl>{task.reason&&<p className="helper">{task.reason}</p>}</>:<p className="helper">A plan begins when this agent chooses to forage, build or explore.</p>}
    <h3>Verified strategies</h3>
    <p className="helper">Strategies enter this library after a measured success. Results in similar conditions influence later goal choices.</p>
    {Object.entries(a.skills??{}).map(([id,s])=><details key={id}>
      <summary>{s.kind} · {s.context} · {s.successes} successes</summary>
      <ol className="plan">{s.stages.map(stage=><li key={stage}>{stage}</li>)}</ol>
      <p className="helper">{s.failures} later failures · average successful duration {s.mean_ticks.toFixed(1)} ticks</p>
    </details>)}
    {!Object.keys(a.skills??{}).length&&<p className="helper">No strategies verified yet.</p>}
    <h3>Plan outcomes</h3>
    <div className="recent-activity">{[...(a.task_history??[])].reverse().map(o=><p key={o.id}>
      <small>T{o.ended_tick} · {o.kind} · {o.status}</small>{o.reason}
      <small>{o.ended_tick-o.started_tick} ticks · {o.actions} actions · {o.energy_spent} action energy · food {o.food_delta>=0?'+':''}{o.food_delta} · hunger {o.hunger_delta>=0?'+':''}{o.hunger_delta} · {o.discoveries} new regions</small>
    </p>)}</div>
  </>
}
