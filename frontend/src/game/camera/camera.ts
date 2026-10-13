import type { Application, Container } from 'pixi.js'
export class Camera {
  private cleanup: () => void
  constructor(private app: Application, private world: Container, private width: number, private height: number) {
    const canvas = app.canvas
    let drag: { x: number; y: number; wx: number; wy: number } | null = null
    const down = (e: PointerEvent) => {
      if (e.button !== 0) return
      drag = { x: e.clientX, y: e.clientY, wx: world.x, wy: world.y }
      canvas.setPointerCapture(e.pointerId)
    }
    const move = (e: PointerEvent) => {
      if (drag) { world.x = drag.wx + e.clientX-drag.x; world.y = drag.wy + e.clientY-drag.y }
    }
    const up = () => { drag = null }
    const wheel = (e: WheelEvent) => {
      e.preventDefault()
      const bounds = canvas.getBoundingClientRect()
      const x = e.clientX - bounds.left, y = e.clientY - bounds.top
      const old = world.scale.x
      const next = Math.min(3.5, Math.max(.25, old * Math.exp(-e.deltaY * .001)))
      world.x = x - (x-world.x) * next/old; world.y = y - (y-world.y) * next/old
      world.scale.set(next)
    }
    canvas.addEventListener('pointerdown', down); canvas.addEventListener('pointermove', move)
    canvas.addEventListener('pointerup', up); canvas.addEventListener('pointercancel', up)
    canvas.addEventListener('wheel', wheel, { passive: false })
    this.cleanup = () => {
      canvas.removeEventListener('pointerdown', down); canvas.removeEventListener('pointermove', move)
      canvas.removeEventListener('pointerup', up); canvas.removeEventListener('pointercancel', up)
      canvas.removeEventListener('wheel', wheel)
    }
  }
  resize(width: number, height: number) { this.width = width; this.height = height; this.fit() }
  fit() {
    this.world.scale.set(Math.min((this.app.screen.width-50)/this.width, (this.app.screen.height-60)/this.height))
    this.center()
  }
  center() {
    this.world.position.set((this.app.screen.width-this.width*this.world.scale.x)/2, (this.app.screen.height-this.height*this.world.scale.y)/2)
  }
  destroy() { this.cleanup() }
}
