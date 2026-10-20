import { useState } from 'react'
import { control } from '../api/client'
import { useWorld } from '../stores/world'
import { FieldIllustration } from './FieldIllustration'
export function Controls() {
  const { snapshot, pending, connection } = useWorld()
  const [seed, setSeed] = useState('42')
  const world = snapshot?.state
  const alive = world ? Object.values(world.agents).filter(a => a.alive).length : 0
  const food = world?.config.infinite ? Object.values(world.settlements).reduce((s,v)=>s+v.food_reserves,0) : world ? Object.values(world.resources).filter(r => r.kind === 'food').reduce((s,r) => s+r.quantity,0) : 0
  const running = world?.status === 'running'
  const disabled = pending || connection !== 'live' || !snapshot
  const validSeed = /^\d+$/.test(seed) && Number(seed) <= 4294967295
  return <aside className="controls panel">
    <div className="brand"><div className="brand-icon">✳</div><div><h1>GENESIS</h1><span>A LIVING ARTIFICIAL WORLD</span></div></div>
    <div className="experiment"><FieldIllustration compact/><span className="eyebrow">A SMALL BEGINNING</span><p>Life finds a way.</p><span className="phase-label">DISCOVER <i /> CREATE <i /> COEXIST</span></div>
    <div className="section-line"><span className="eyebrow">WORLD STATE</span><span className={`status-pill ${running ? 'active' : ''}`}>{running ? 'RUNNING' : 'PAUSED'}</span></div>
    <div className="tick"><span>{String(world?.tick ?? 0).padStart(5,'0')}</span><small>SIMULATION TICK</small></div>
    <div className="stats"><div><span className="stat-icon">♙</span><b>{alive}<small> / {world?.config.agent_count ?? 10}</small></b><label>Living agents</label></div><div><span className="stat-icon berry">✿</span><b>{food}</b><label>Food reserves</label></div></div>
    <div className="divider" />
    <span className="eyebrow">SIMULATION</span>
    <button className="primary mt-4" disabled={disabled} onClick={() => void control(running ? 'pause' : world?.tick ? 'resume' : 'start')}>{running ? 'Ⅱ Pause world' : '▶ '+(world?.tick ? 'Resume world' : 'Start world')}</button>
    <button className="secondary" disabled={disabled || running} onClick={() => void control('step')}>↦ Advance one tick</button>
    <div className="speed-label"><label>Time speed</label><span>{world?.speed ?? 1}×</span></div>
    <div className="speeds">{[.5,1,2,4,8].map(s => <button key={s} className={world?.speed === s ? 'chosen' : ''} disabled={disabled} onClick={() => void control('speed',{ multiplier:s })}>{s}×</button>)}</div>
    <div className="divider" />
    <label className="eyebrow" htmlFor="seed">WORLD SEED</label>
    <div className="seed-input"><span>⌘</span><input id="seed" aria-label="World seed" inputMode="numeric" value={seed} onChange={e => setSeed(e.target.value)} /></div>
    <p className="helper">Current seed: {world?.config.seed ?? '—'}. Same seed, same beginning.</p>
    <button className="secondary reset" disabled={disabled || !validSeed} onClick={() => void control('reset',{seed:Number(seed)})}>↺ Reset world</button>
    <div className="control-footer"><span className={`status-dot ${connection !== 'live' ? 'offline' : ''}`} /><span>{connection === 'live' ? 'Connected to simulation' : connection === 'connecting' ? 'Connecting…' : 'Reconnecting…'}</span><small>EVERY CHOICE LEAVES A TRACE</small></div>
  </aside>
}
