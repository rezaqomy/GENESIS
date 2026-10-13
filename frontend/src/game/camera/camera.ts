import type { Application, Container } from 'pixi.js'
import type { Position } from '../../types/world'
export const TILE=32
export class Camera {
  private cleanup: () => void
  private target={x:0,y:0,zoom:1}
  private anchor:Position={x:0,y:0}
  private finite=false
  private worldWidth=40
  private worldHeight=30
  dragged=false
  manual=false
  constructor(private app: Application, private world: Container) {
    const canvas=app.canvas
    let drag:{x:number;y:number;wx:number;wy:number}|null=null
    const down=(e:PointerEvent)=>{
      if(e.button!==0)return
      this.dragged=false
      drag={x:e.clientX,y:e.clientY,wx:this.target.x,wy:this.target.y}
      canvas.setPointerCapture(e.pointerId)
    }
    const move=(e:PointerEvent)=>{
      if(!drag)return
      const dx=e.clientX-drag.x,dy=e.clientY-drag.y
      if(Math.abs(dx)+Math.abs(dy)>4){this.dragged=true;this.manual=true}
      this.target.x=drag.wx+dx;this.target.y=drag.wy+dy
    }
    const up=()=>{drag=null}
    const wheel=(e:WheelEvent)=>{
      e.preventDefault();this.manual=true
      const b=canvas.getBoundingClientRect(),x=e.clientX-b.left,y=e.clientY-b.top
      const old=this.target.zoom,next=Math.min(3,Math.max(.4,old*Math.exp(-e.deltaY*.001)))
      this.target.x=x-(x-this.target.x)*next/old;this.target.y=y-(y-this.target.y)*next/old
      this.target.zoom=next
    }
    canvas.addEventListener('pointerdown',down);canvas.addEventListener('pointermove',move)
    canvas.addEventListener('pointerup',up);canvas.addEventListener('pointercancel',up);canvas.addEventListener('wheel',wheel,{passive:false})
    this.cleanup=()=>{canvas.removeEventListener('pointerdown',down);canvas.removeEventListener('pointermove',move);canvas.removeEventListener('pointerup',up);canvas.removeEventListener('pointercancel',up);canvas.removeEventListener('wheel',wheel)}
  }
  configure(infinite:boolean,width:number,height:number,center:Position) {
    this.finite=!infinite;this.worldWidth=width;this.worldHeight=height;this.anchor=center;this.fit(true)
  }
  update(delta:number) {
    const f=1-Math.exp(-delta/90)
    this.world.x+=(this.target.x-this.world.x)*f;this.world.y+=(this.target.y-this.world.y)*f
    this.world.scale.set(this.world.scale.x+(this.target.zoom-this.world.scale.x)*f)
  }
  jump(position:Position,snap=false) {
    this.manual=false
    this.target.x=this.app.screen.width/2-(position.x+.5)*TILE*this.target.zoom
    this.target.y=this.app.screen.height/2-(position.y+.5)*TILE*this.target.zoom
    if(snap)this.snap()
  }
  follow(position:Position) {this.jump(position)}
  fit(snap=false) {
    const width=this.finite?this.worldWidth:30,height=this.finite?this.worldHeight:24
    this.target.zoom=Math.max(.4,Math.min(1.2,(this.app.screen.width-35)/(width*TILE),(this.app.screen.height-35)/(height*TILE)))
    this.center(snap)
  }
  center(snap=false) {
    const p=this.finite?{x:this.worldWidth/2-.5,y:this.worldHeight/2-.5}:this.anchor
    this.jump(p,snap)
  }
  private snap(){this.world.position.set(this.target.x,this.target.y);this.world.scale.set(this.target.zoom)}
  bounds(){const scale=this.world.scale.x;return {left:-this.world.x/scale/TILE,top:-this.world.y/scale/TILE,right:(this.app.screen.width-this.world.x)/scale/TILE,bottom:(this.app.screen.height-this.world.y)/scale/TILE}}
  destroy(){this.cleanup()}
}
