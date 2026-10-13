import { Application, Container, Graphics } from 'pixi.js'
import type { Snapshot } from '../../types/world'
import { Human } from '../sprites/human'
import { Camera } from '../camera/camera'

const TILE = 24
const COLORS = { grass: ['#9eae71', '#a4b478', '#a8b77c'], forest: ['#81965e', '#8b9e65', '#879b63'], water: ['#6caaae', '#73afb2', '#68a3aa'], rock: ['#96a16e', '#9aa575', '#9fac79'], soil: ['#baa37c', '#b39d73', '#b6a178'] }
export class WorldRenderer {
  app = new Application()
  scene = new Container()
  terrain = new Graphics()
  objects = new Container()
  destination = new Graphics()
  humans = new Map<string, Human>()
  camera: Camera | null = null
  last: Snapshot | null = null
  selected: string | null = null
  duration = 500
  time = 0
  ready = false
  disposed = false
  observer: ResizeObserver | null = null
  constructor(private host: HTMLDivElement, private select: (id: string) => void) {}
  async init() {
    await this.app.init({ background: '#18272a', antialias: false, resolution: Math.min(devicePixelRatio, 2), autoDensity: true, resizeTo: this.host, preference: 'webgl' })
    if (this.disposed) { this.app.destroy(true, { children: true }); return }
    this.host.appendChild(this.app.canvas)
    this.scene.sortableChildren = true
    this.objects.sortableChildren = true
    this.scene.addChild(this.terrain, this.objects, this.destination)
    this.terrain.zIndex = -1000; this.destination.zIndex = 2000
    this.app.stage.addChild(this.scene)
    this.camera = new Camera(this.app, this.scene, 40*TILE, 30*TILE)
    this.camera.fit()
    this.observer = new ResizeObserver(() => { this.app.resize(); this.camera?.center() })
    this.observer.observe(this.host)
    this.app.ticker.add(ticker => {
      this.time += ticker.deltaMS / 1000
      for (const h of this.humans.values()) {
        h.progress = Math.min(1, h.progress + ticker.deltaMS / this.duration)
        const p = h.progress
        h.node.position.set(h.from.x + (h.to.x-h.from.x)*p, h.from.y + (h.to.y-h.from.y)*p)
        h.node.zIndex = h.node.y
        h.draw(this.time, h.agent.id === this.selected, this.last?.state.status === 'running')
      }
    })
    this.ready = true
  }
  setSelected(selected: string | null) { this.selected = selected; this.drawDestination() }
  private drawDestination() {
    this.destination.clear()
    const a = this.selected ? this.last?.state.agents[this.selected] : null
    if (a?.destination) {
      this.destination.rect(a.destination.x*TILE+2, a.destination.y*TILE+2, TILE-4, TILE-4).stroke({ color: '#fff0af', width: 1.5, alpha: .8 })
    }
  }
  update(snapshot: Snapshot) {
    if (!this.ready) return
    const fresh = this.last?.run_id !== snapshot.run_id
    const tickChanged = this.last?.state.tick !== snapshot.state.tick
    const pauseChanged = this.last?.state.status === 'running' && snapshot.state.status === 'paused'
    const world = snapshot.state
    this.duration = Math.max(60, Math.min(1000, world.status === 'paused' ? 250 : snapshot.tick_ms))
    if (fresh) {
      this.drawTerrain(snapshot)
      for (const h of this.humans.values()) h.node.destroy({ children: true })
      this.humans.clear()
      this.camera?.resize(world.config.width*TILE, world.config.height*TILE)
    }
    this.objects.removeChildren().forEach(c => c.destroy({ children: true }))
    for (const r of Object.values(world.resources)) {
      const g = new Graphics()
      const x = r.position.x*TILE+12, y = r.position.y*TILE+17
      g.position.set(x,y); g.zIndex = y
      g.ellipse(0, 1, r.kind === 'wood' ? 12 : 8, 4).fill({ color: '#456242', alpha: .3 })
      if (r.kind === 'wood') {
        g.rect(-2, -14, 5, 17).fill('#735338')
        g.poly([-13,-10, 0,-30, 13,-10]).fill('#496b4b')
        g.poly([-11,-17, 0,-37, 11,-17]).fill('#628551')
        g.poly([-8,-24, 0,-42, 8,-24]).fill('#729358')
        g.rect(-1, -10, 2, 10).fill('#9b7750')
      } else {
        g.roundRect(-8,-10,16,12,4).fill('#597648')
        g.roundRect(-6,-14,12,12,4).fill('#738d4d')
        if (r.quantity) for (let i=0; i<Math.min(r.quantity,5); i++) g.rect(-5+i*2.5, -9+(i%2)*3, 3,3).fill('#c7797c')
      }
      if (!r.quantity) g.alpha = .4
      this.objects.addChild(g)
    }
    for (const a of Object.values(world.agents)) {
      let h = this.humans.get(a.id)
      if (!h) {
        h = new Human(a, this.select); this.humans.set(a.id,h); this.scene.addChild(h.node)
        h.node.position.set(a.position.x*TILE+12, a.position.y*TILE+17)
      }
      if (fresh || tickChanged || pauseChanged) {
        h.from = { x: h.node.x, y: h.node.y }
        h.to = { x: a.position.x*TILE+12, y: a.position.y*TILE+17 }
        const dx = h.to.x-h.from.x, dy = h.to.y-h.from.y
        if (Math.abs(dx)+Math.abs(dy) > 1) h.direction = { x: Math.sign(dx), y: Math.sign(dy) }
        h.progress = fresh || pauseChanged ? 1 : 0
        if (h.progress === 1) h.node.position.set(h.to.x,h.to.y)
      }
      h.agent = a
    }
    this.last = snapshot
    this.drawDestination()
  }
  private drawTerrain(snapshot: Snapshot) {
    const g = this.terrain.clear()
    const world = snapshot.state
    g.roundRect(-6,-6,world.config.width*TILE+12,world.config.height*TILE+12,5).fill('#31463b')
    for (const t of world.tiles) {
      const x = t.position.x*TILE, y = t.position.y*TILE
      const n = (t.position.x*17 + t.position.y*31 + world.config.seed) % 3
      g.rect(x,y,TILE,TILE).fill(COLORS[t.terrain][n])
      if (t.terrain === 'water') {
        g.rect(x+4,y+7+n*3,10,1).fill({ color: '#b9d8c9', alpha: .35 })
        g.rect(x+12,y+17,6,1).fill({ color: '#badacb', alpha: .3 })
      } else if (t.terrain === 'rock') {
        g.ellipse(x+12,y+17,9,5).fill({ color: '#536855', alpha: .35 })
        g.poly([x+3,y+15,x+7,y+5,x+16,y+4,x+21,y+14,x+17,y+18,x+7,y+18]).fill('#8b9690')
        g.poly([x+7,y+5,x+16,y+4,x+15,y+10,x+4,y+14]).fill('#bac0aa')
      } else if (t.terrain === 'soil') {
        for (let j=0;j<3;j++) g.rect(x+4+j*6,y+6,2,12).fill({ color: '#907c56', alpha: .22 })
      } else {
        g.rect(x+5+n*4,y+7,1,3).fill({ color: '#5e7e49', alpha: .3 })
        g.rect(x+15,y+17-n*3,2,1).fill({ color: '#d5d193', alpha: .5 })
        if ((t.position.x*7+t.position.y)%47 === 0) {
          g.rect(x+9,y+11,2,2).fill('#dfd9a7'); g.rect(x+10,y+13,1,3).fill('#64814b')
        }
      }
    }
  }
  destroy() {
    this.disposed = true
    this.observer?.disconnect(); this.camera?.destroy()
    if (this.ready) this.app.destroy(true, { children: true })
  }
}
