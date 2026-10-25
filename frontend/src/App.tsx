import { Controls } from './components/Controls'
import { Inspector } from './components/Inspector'
import { Timeline } from './components/Timeline'
import { WorldView } from './components/WorldView'
import { useSimulation } from './hooks/useSimulation'
import { useWorld } from './stores/world'
import { WorldPulse } from './components/WorldPulse'
export default function App() {
  useSimulation()
  const error = useWorld(s => s.error)
  const environment=useWorld(s=>s.snapshot?.environment)
  return <div className="app-shell"><Controls/><main><header className="main-header"><div className="page-title"><span className="eyebrow">THE LIVING WORLD / OBSERVATORY</span><h2>A world, becoming<span>.</span></h2><p>Watch small choices turn into a shared history.</p></div><div className="day-card"><span aria-hidden="true">{environment?.night?'☾':'☀'}</span><div><b>Day {environment?.day??'—'}</b><small>{environment?.weather??'Waiting for the world'}</small></div></div></header>{error && <div className="error-banner" role="alert">{error}<button onClick={() => useWorld.setState({error:null})} aria-label="Dismiss error">×</button></div>}<WorldPulse/><WorldView/><Timeline/></main><Inspector/></div>
}
