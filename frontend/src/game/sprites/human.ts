import { Container, Graphics, Rectangle, Text } from 'pixi.js'
import type { Agent } from '../../types/world'

export class Human {
  node = new Container()
  body = new Graphics()
  ring = new Graphics()
  label: Text
  indicator: Text
  from = { x: 0, y: 0 }
  to = { x: 0, y: 0 }
  progress = 1
  direction = { x: 0, y: 1 }
  agent: Agent
  constructor(agent: Agent, select: (id: string) => void) {
    this.agent = agent
    this.node.addChild(this.ring, this.body)
    this.label = new Text({ text: agent.name, style: { fontFamily: 'monospace', fontSize: 9, fontWeight: 'bold', fill: '#fff5dc', stroke: { color: '#243c32', width: 3 } } })
    this.label.anchor.set(.5, 1); this.label.y = -21
    this.indicator = new Text({ text: '', style: { fontFamily: 'monospace', fontSize: 9, fill: '#fff0b2', stroke: { color: '#243c32', width: 3 } } })
    this.indicator.anchor.set(.5, 0); this.indicator.y = 4
    this.node.addChild(this.label, this.indicator)
    this.node.eventMode = 'static'; this.node.cursor = 'pointer'
    this.node.hitArea = new Rectangle(-13, -24, 26, 33)
    this.node.on('pointertap', () => select(agent.id))
  }
  draw(time: number, selected: boolean, running: boolean) {
    const a = this.agent
    const walking = this.progress < 1
    const swing = walking ? Math.sin(time * 13) * 2.5 : 0
    const bob = a.alive && running ? Math.sin(time * (walking ? 26 : 2) + Number(a.id.slice(-2))) * (walking ? .6 : .35) : 0
    const g = this.body.clear()
    g.ellipse(0, 0, 8, 3).fill({ color: '#18372a', alpha: .28 })
    this.body.y = bob
    g.rect(-5, -6, 4, 7 + swing).fill('#293e50')
    g.rect(1, -6, 4, 7 - swing).fill('#293e50')
    g.rect(-6, 0 + swing, 5, 2).fill('#1c2731')
    g.rect(1, 0 - swing, 5, 2).fill('#1c2731')
    g.rect(-6, -14, 12, 10).fill(a.alive ? a.visual_color : '#758479')
    g.rect(-7, -13 + swing, 3, 7).fill(a.visual_color)
    g.rect(4, -13 - swing, 3, 7).fill(a.visual_color)
    const skin = ['#efc499', '#c99872', '#a77050', '#e0ae87'][Number(a.id.slice(-2)) % 4]
    g.rect(-7, -7 + swing, 3, 3).fill(skin); g.rect(4, -7 - swing, 3, 3).fill(skin)
    g.rect(-4, -21, 8, 8).fill(skin)
    g.rect(-5, -23, 10, 4).fill(['#553d32', '#b0793f', '#333438'][Number(a.id.slice(-2)) % 3])
    g.rect(-5, -20, 2, 3).fill('#553d32')
    if (this.direction.y >= 0) {
      const offset = this.direction.x * 2
      g.rect(-2 + offset, -18, 1, 1).fill('#292d35'); g.rect(2 + offset, -18, 1, 1).fill('#292d35')
    } else { g.rect(-4, -20, 8, 5).fill('#553d32') }
    if (a.current_action === 'GATHER') g.rect(6, -9, 4, 3).fill('#e093a0')
    this.ring.clear()
    if (selected) {
      this.ring.ellipse(0, 0, 12, 5).stroke({ color: '#fff0af', width: 1.6 })
      this.ring.poly([-3,-30, 3,-30, 0,-26]).fill('#fff0af')
    }
    this.indicator.text = !a.alive ? '†' : { MOVE: '', GATHER: 'gathering', EAT: 'eating', REST: 'z z', IDLE: '' }[a.current_action]
    this.node.alpha = a.alive ? 1 : .5
  }
}
