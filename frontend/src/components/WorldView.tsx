import { useEffect, useRef, useState } from 'react'
import { WorldRenderer } from '../game/rendering/world'
import { useWorld } from '../stores/world'
export function WorldView() {
  const host = useRef<HTMLDivElement>(null)
  const renderer = useRef<WorldRenderer | null>(null)
  const [ready, setReady] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const snapshot = useWorld(s => s.snapshot)
  const selected = useWorld(s => s.selected)
  useEffect(() => {
    if (!host.current) return
    const world = new WorldRenderer(host.current, id => useWorld.getState().select(id))
    renderer.current = world
    world.init().then(() => {
      if (world.disposed) return
      const state = useWorld.getState()
      if (state.snapshot) world.update(state.snapshot)
      world.setSelected(state.selected)
      setReady(true)
    }).catch(e => setError(`Renderer could not start: ${String(e)}`))
    return () => world.destroy()
  }, [])
  useEffect(() => { if (snapshot && ready) renderer.current?.update(snapshot) }, [snapshot, ready])
  useEffect(() => renderer.current?.setSelected(selected), [selected])
  return <div className="world-frame">
    <div className="world-heading"><span className="eyebrow">THE OBSERVATORY</span><span>{snapshot?.state.config.width ?? 40} × {snapshot?.state.config.height ?? 30} tiles <i /> TOP-DOWN VIEW</span></div>
    <div className="world-canvas" ref={host} role="img" aria-label="Interactive Genesis world. Click a character to inspect, drag to pan, scroll to zoom." />
    {(!ready || !snapshot || error) && <div className="loading-world">{error ?? 'Preparing your world…'}</div>}
    <div className="world-badge"><span className="status-dot" /> {snapshot?.state.status === 'running' ? 'A world in motion' : 'A moment in time'}</div>
    <div className="camera-controls"><button onClick={() => renderer.current?.camera?.center()} title="Center camera">⌖ Center</button><button onClick={() => renderer.current?.camera?.fit()} title="Fit world to viewport">⛶ Fit world</button></div>
    <div className="world-guide">DRAG TO EXPLORE <span>·</span> SCROLL TO ZOOM <span>·</span> CLICK A CHARACTER</div>
  </div>
}
