import { useWorld } from '../stores/world'
export function Minimap() {
  const {snapshot,chunks,selected,cameraBounds,focus} = useWorld()
  if(!snapshot?.state.config.infinite) return null
  const known=snapshot.state.explored_chunks.map(k=>k.split(',').map(Number))
  if(!known.length) return null
  const minX=Math.min(...known.map(c=>c[0]))*32,minY=Math.min(...known.map(c=>c[1]))*32
  const width=(Math.max(...known.map(c=>c[0]))+1)*32-minX,height=(Math.max(...known.map(c=>c[1]))+1)*32-minY
  const size=Math.max(width,height),x=minX-(size-width)/2,y=minY-(size-height)/2
  const colors:Record<string,string>={g:'#719667',f:'#3c624a',w:'#467a97',r:'#949084',s:'#b8a56d',a:'#c4b889',m:'#656c73',p:'#9f8664'}
  return <div className="minimap"><span>KNOWN WORLD</span><svg viewBox={`${x} ${y} ${size} ${size}`} role="img" aria-label="Explored world minimap" onClick={e=>{ const r=e.currentTarget.getBoundingClientRect();focus({x:Math.floor(x+(e.clientX-r.left)/r.width*size),y:Math.floor(y+(e.clientY-r.top)/r.height*size)}) }}>
    {known.map(([cx,cy])=>{const c=chunks[`${cx},${cy}`];return <g key={`${cx},${cy}`}><rect x={cx*32} y={cy*32} width="32" height="32" fill="#365344"/>{c && Array.from({length:64},(_,i)=><rect key={i} x={cx*32+i%8*4} y={cy*32+Math.floor(i/8)*4} width="4" height="4" fill={colors[c.terrain[Math.floor(i/8)*4*32+i%8*4]]??'#365344'}/>)}</g>})}
    {Object.values(snapshot.state.settlements).map(s=><path key={s.id} d={`M ${s.center.x} ${s.center.y-2} l 2 2 -2 2 -2 -2 Z`} fill="#edc67b"/>)}
    {Object.values(snapshot.state.agents).filter(a=>a.alive).map(a=><circle key={a.id} cx={a.position.x} cy={a.position.y} r={a.id===selected?1.5:.8} fill={a.id===selected?'#fff':a.visual_color}/>)}
    {cameraBounds && <rect x={cameraBounds.left} y={cameraBounds.top} width={cameraBounds.right-cameraBounds.left} height={cameraBounds.bottom-cameraBounds.top} fill="none" stroke="#fff9" strokeWidth=".5"/>}
  </svg></div>
}
