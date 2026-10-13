import { Controls } from './components/Controls'
import { Inspector } from './components/Inspector'
import { Timeline } from './components/Timeline'
import { WorldView } from './components/WorldView'
import { useSimulation } from './hooks/useSimulation'
import { useWorld } from './stores/world'
export default function App() {
  useSimulation()
  const error = useWorld(s => s.error)
  return <div className="app-shell"><Controls/><main><header className="main-header"><div><span className="header-symbol">◈</span><span>THE FIRST WORLD</span><i/><small>Observe. Let life unfold.</small></div><span className="version">GENESIS / 0.2</span></header>{error && <div className="error-banner" role="alert">{error}<button onClick={() => useWorld.setState({error:null})} aria-label="Dismiss error">×</button></div>}<WorldView/><Timeline/></main><Inspector/></div>
}
