import { useEffect, useRef, useState } from 'react'
import { WorldRenderer } from '../game/rendering/world'
import { Minimap } from './Minimap'
import { useWorld } from '../stores/world'
export function WorldView() {
  const host = useRef<HTMLDivElement>(null)
  const renderer = useRef<WorldRenderer | null>(null)
  const [ready, setReady] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const snapshot = useWorld(s => s.snapshot)
  const selected = useWorld(s => s.selected)
  const chunks = useWorld(s => s.chunks)
  const cameraRequest = useWorld(s => s.cameraRequest)
  const follow = useWorld(s => s.follow)
  const effects = useWorld(s => s.effects)
  useEffect(() => {
    if (!host.current) return
    const world = new WorldRenderer(host.current, id => useWorld.getState().select(id))
    renderer.current = world
    world.init().then(() => {
      if (world.disposed) return
      const state = useWorld.getState()
      if (state.snapshot) world.update(state.snapshot)
      world.setChunks(state.chunks)
      world.setSelected(state.selected)
      setReady(true)
    }).catch(e => setError(`Renderer could not start: ${String(e)}`))
    return () => world.destroy()
  }, [])
  useEffect(() => { if (snapshot && ready) { renderer.current?.update(snapshot); renderer.current?.setChunks(useWorld.getState().chunks) } }, [snapshot, ready])
  useEffect(() => renderer.current?.setSelected(selected), [selected])
  useEffect(() => { if (ready) renderer.current?.setChunks(chunks) }, [chunks, ready])
  useEffect(() => { if (cameraRequest && ready) renderer.current?.camera?.jump(cameraRequest.position) }, [cameraRequest, ready])
  return <div className="world-frame">
    <div className="world-heading"><span className="eyebrow">THE OBSERVATORY</span><span>{snapshot?.state.config.infinite ? 'INFINITE WILDERNESS' : `${snapshot?.state.config.width ?? 40} × ${snapshot?.state.config.height ?? 30} tiles`} <i /> DAY {snapshot?.environment?.day ?? 1} · {snapshot?.environment?.night ? 'NIGHT' : 'DAYLIGHT'} · {snapshot?.environment?.weather ?? 'clear'}</span></div>
    <div className="world-canvas" ref={host} role="img" aria-label="Interactive Genesis world. Click a character to inspect, drag to pan, scroll to zoom." />
    {(!ready || !snapshot || error) && <div className="loading-world">{error ?? 'Preparing your world…'}</div>}
    <div className="world-badge"><span className="status-dot" /> {snapshot?.state.status === 'running' ? 'A world in motion' : 'A moment in time'}</div>
    <Minimap/><div className="camera-controls"><button onClick={() => renderer.current?.camera?.center()} title="Center camera">⌖ Center</button><button onClick={() => renderer.current?.camera?.fit()} title="Fit world to viewport">⛶ Fit world</button><button disabled={!selected} className={follow ? 'chosen' : ''} onClick={() => { const a=selected ? snapshot?.state.agents[selected] : null; if(a) renderer.current?.camera?.jump(a.position); useWorld.setState({follow:!follow}) }}>Follow agent</button><button aria-pressed={effects} onClick={() => useWorld.setState({effects:!effects})}>Effects {effects ? 'on' : 'off'}</button><button onClick={() => { const a=Object.values(snapshot?.state.agents ?? {}).sort((a,b)=>b.time_away-a.time_away)[0]; if(a) useWorld.getState().focus(a.position) }}>Find explorer</button></div>
    <div className="world-guide">DRAG TO EXPLORE <span>·</span> SCROLL TO ZOOM <span>·</span> CLICK A CHARACTER</div>
  </div>
}
