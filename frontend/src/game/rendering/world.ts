import { Application, Container, Graphics, Rectangle, Sprite, Text } from 'pixi.js'
import type { Building, ChunkView, Resource, Snapshot, Terrain } from '../../types/world'
import { useWorld } from '../../stores/world'
import { requestChunks } from '../../api/stream'
import { Human } from '../sprites/human'
import { Camera, TILE } from '../camera/camera'
import { GameAssets } from './assets'

const CODE:Record<string,Terrain>={g:'grass',f:'forest',w:'water',r:'rock',s:'soil',a:'sand',m:'mountain',p:'path'}
const COLOR:Record<Terrain,string>={grass:'#8caa68',forest:'#507858',water:'#4f9ea8',rock:'#9b9c8a',soil:'#91765d',sand:'#d4bc83',mountain:'#8c9290',path:'#a0896c'}
const RESOURCE_ASSET:Record<string,string>={wood:'pine',food:'berry_bush',stone:'rock',fiber:'fiber_plant',clay:'clay_deposit',ore:'ore_deposit',fuel:'coal_pile',water:'spring',seeds:'seed_plant'}
interface RenderChunk {node:Container;resources:string[];water:Sprite[];trees:Sprite[];key:string}
export class WorldRenderer {
  app=new Application();scene=new Container();terrainLayer=new Container();terrainEditsLayer=new Container();entities=new Container()
  destination=new Graphics();influence=new Graphics();atmosphere=new Graphics();weather=new Graphics();lights=new Container()
  assets=new GameAssets();humans=new Map<string,Human>();chunks=new Map<string,RenderChunk>()
  resources=new Map<string,{sprite:Container;resource:Resource}>();buildings=new Map<string,Container>()
  camera:Camera|null=null;last:Snapshot|null=null;selected:string|null=null
  duration=500;time=0;ready=false;disposed=false;observer:ResizeObserver|null=null
  private chunkData:Record<string,ChunkView>={};private lastWanted='';private requestTime=0
  private frames=0;private frameMs=0;private reportMs=0;private lastEffectTick=-1;private dust:{g:Graphics;life:number}[]=[]
  private hoveredBuilding:string|null=null
  constructor(private host:HTMLDivElement,private select:(id:string)=>void){}
  async init(){
    await this.app.init({background:'#223831',antialias:false,resolution:Math.min(devicePixelRatio,2),autoDensity:true,resizeTo:this.host,preference:'webgl'})
    if(this.disposed){this.app.destroy(true,{children:true});return}
    await this.assets.load()
    if(this.disposed){this.app.destroy(true,{children:true});return}
    this.host.appendChild(this.app.canvas)
    this.entities.sortableChildren=true
    this.scene.addChild(this.terrainLayer,this.terrainEditsLayer,this.influence,this.entities,this.destination)
    this.app.stage.addChild(this.scene,this.atmosphere,this.lights,this.weather)
    this.camera=new Camera(this.app,this.scene)
    this.observer=new ResizeObserver(()=>{this.app.resize();this.camera?.center()})
    this.observer.observe(this.host)
    this.app.ticker.add(ticker=>this.frame(ticker.deltaMS))
    useWorld.setState({fallbackAssets:this.assets.missing.length})
    this.ready=true
  }
  setSelected(selected:string|null){this.selected=selected;this.drawDestination()}
  setChunks(chunks:Record<string,ChunkView>){this.chunkData=chunks;if(this.last?.state.config.infinite)this.syncChunks()}
  private sprite(id:string,width:number,height=width):Container {
    const texture=this.assets.get(id)
    if(texture){const s=new Sprite(texture);s.width=width;s.height=height;s.anchor.set(.5,1);return s}
    // Explicit runnable fallback only when the externally replaceable asset is missing.
    const g=new Graphics().roundRect(-width/3,-height*.7,width*.66,height*.7,5).fill('#759464')
    return g
  }
  private assemblySprite(b:Building):Container {
    const node=new Container(),g=new Graphics()
    const palette:Record<string,number>={wood:0x956d43,stone:0x858c91,fiber:0xb2ae70,clay:0xb87852,ore:0x716966,metal:0xa8bdc8,ceramic:0xd6a681}
    const design=b.assembly!.design
    g.ellipse(0,-1,20,6).fill({color:0x17231d,alpha:.3})
    design.parts.forEach((p,i)=>{
      const x=(i%3-1)*12,y=-8-Math.floor(i/3)*13,color=palette[p.material]??0x999999
      if(p.shape==='wheel')g.circle(x,y-7,8).stroke({color,width:3}).moveTo(x-7,y-7).lineTo(x+7,y-7).stroke({color,width:2})
      else if(p.shape==='bowl')g.roundRect(x-8,y-10,16,12,5).fill(color).ellipse(x,y-10,7,3).fill(0x3b3630)
      else if(p.shape==='mesh'){
        g.rect(x-8,y-18,16,20).stroke({color,width:2})
        for(let k=0;k<4;k++)g.moveTo(x-6+k*4,y-18).lineTo(x-6+k*4,y+2).stroke({color,width:1})
        for(let k=0;k<5;k++)g.moveTo(x-8,y-16+k*4).lineTo(x+8,y-16+k*4).stroke({color,width:1})
      }else if(p.shape==='rod')g.rect(x-2,y-26,4,27).fill(color)
      else if(p.shape==='blade')g.poly([x-8,y,x+7,y-20,x+9,y-2]).fill(color)
      else g.roundRect(x-9,y-15,18,14,2).fill(color).stroke({color:0x393a30,width:1})
    })
    if(design.enclosed)g.roundRect(-21,-34,42,32,5).stroke({color:0xd6bc81,width:2,alpha:.75})
    node.addChild(g)
    const label=new Text({text:design.name,style:{fontSize:8,fontFamily:'monospace',fill:0xffe9bb,stroke:{color:0x22352b,width:2}}})
    label.label='assembly-name';label.anchor.set(.5,1);label.y=-39;label.visible=false;node.addChild(label)
    node.eventMode='static';node.cursor='help';node.hitArea=new Rectangle(-24,-36,48,40)
    node.on('pointerover',()=>{this.hoveredBuilding=b.id})
    node.on('pointerout',()=>{if(this.hoveredBuilding===b.id)this.hoveredBuilding=null})
    return node
  }
  private ground(terrain:Terrain,x:number,y:number){
    const variation=Math.abs(x*17+y*31)%17
    const id=terrain==='grass'?(variation===0?'grass_flowers':'grass'):
      terrain==='forest'?(variation%3?'forest_floor':'forest_leaves'):
      terrain==='water'?'water':terrain==='soil'?'fertile_soil':terrain==='sand'?'sand':
      terrain==='mountain'?'mountain_floor':terrain==='path'?'path':'stone_floor'
    const texture=this.assets.get(id)
    if(texture){const sprite=new Sprite(texture);sprite.position.set(x*TILE,y*TILE);sprite.width=TILE;sprite.height=TILE;return sprite}
    return new Graphics().rect(x*TILE,y*TILE,TILE,TILE).fill(COLOR[terrain])
  }
  private renderChunk(chunk:ChunkView){
    const node=new Container(),water:Sprite[]=[],trees:Sprite[]=[],ids:string[]=[]
    node.label=chunk.key
    for(let i=0;i<chunk.terrain.length;i++){
      const x=chunk.cx*32+i%32,y=chunk.cy*32+Math.floor(i/32),terrain=CODE[chunk.terrain[i]]??'grass'
      const ground=this.ground(terrain,x,y);node.addChild(ground)
      if(terrain==='water'&&ground instanceof Sprite)water.push(ground)
      // Soft coast/biome fringe over authored tiles; silhouettes remain generated art.
      if(terrain==='grass'||terrain==='forest'){
        const next=chunk.terrain[i+1]
        if(next&&next!==chunk.terrain[i]&&i%32!==31){
          const edge=new Graphics().rect(x*TILE+28,y*TILE,4,TILE).fill({color:COLOR[CODE[next]],alpha:.16})
          node.addChild(edge)
        }
      }
    }
    for(const resource of Object.values(chunk.resources)){
      let asset=RESOURCE_ASSET[resource.kind]
      if(resource.kind==='wood'&&Math.abs(resource.position.x+resource.position.y)%3===0)asset='oak'
      const sprite=this.sprite(asset,resource.kind==='wood'?58:resource.kind==='food'?34:40)
      sprite.position.set(resource.position.x*TILE+16,resource.position.y*TILE+27)
      sprite.zIndex=sprite.y;this.entities.addChild(sprite)
      ids.push(resource.id);this.resources.set(resource.id,{sprite,resource})
      if(resource.kind==='wood'&&sprite instanceof Sprite)trees.push(sprite)
    }
    this.terrainLayer.addChild(node)
    this.chunks.set(chunk.key,{node,resources:ids,water,trees,key:chunk.key})
  }
  private terrainEdits=new Map<string,Container>()
  private livingNodes=new Map<string,Container>()
  private syncLife(snapshot:Snapshot){
    const e=snapshot.state.ecosystem,present=new Set<string>()
    for(const animal of Object.values(e?.animals??{})){
      present.add(animal.id)
      const signature=`${animal.species}:${animal.owner_id}:${snapshot.state.tick-animal.born_tick<240}`
      let node=this.livingNodes.get(animal.id)
      if(node?.label!==signature){
        node?.destroy({children:true});node=new Container();node.label=signature
        const g=new Graphics(),chicken=animal.species==='chicken'
        const color=animal.species==='sheep'?0xeee6ce:chicken?0xf2d8a2:0xa57b57
        g.ellipse(0,0,11,4).fill({color:0x17231d,alpha:.25})
        g.rect(-6,-5,3,7).rect(4,-5,3,7).fill(0x554e3d)
        g.ellipse(-1,-10,chicken?7:11,chicken?7:8).fill(color)
        g.circle(9,-13,chicken?4:6).fill(color).circle(11,-14,1).fill(0x25372d)
        if(chicken)g.poly([12,-13,17,-11,12,-10]).fill(0xe3a64c)
        if(animal.species==='cow')g.ellipse(-4,-11,4,5).fill(0x4c463c)
        if(animal.owner_id)g.circle(0,-24,2).fill(0x85d9a3)
        node.addChild(g)
        if(snapshot.state.tick-animal.born_tick<240)node.scale.set(.65)
        this.entities.addChild(node);this.livingNodes.set(animal.id,node)
      }
      node.position.set((animal.position.x+.5)*TILE,(animal.position.y+.7)*TILE)
      node.zIndex=node.y
    }
    for(const crop of Object.values(e?.crops??{})){
      present.add(crop.id)
      const stage=crop.health===0?-1:Math.floor(crop.growth/20)
      const signature=`${stage}:${crop.moisture>20}`
      let node=this.livingNodes.get(crop.id)
      if(node?.label!==signature){
        node?.destroy({children:true});node=new Container();node.label=signature
        const g=new Graphics().roundRect(-12,-5,24,12,3).fill(crop.moisture>20?0x67503b:0x9d7752)
        for(let i=0;i<3;i++){
          const x=i*7-7,height=5+Math.max(0,stage)*4,color=stage<0?0x88734b:stage===4?0xe8c66a:0x80b858
          g.moveTo(x,0).lineTo(x,-height).stroke({color,width:2})
          g.ellipse(x,-height,3,5).fill(color)
        }
        node.addChild(g);this.entities.addChild(node);this.livingNodes.set(crop.id,node)
      }
      node.position.set((crop.position.x+.5)*TILE,(crop.position.y+.7)*TILE);node.zIndex=node.y-1
    }
    for(const drop of Object.values(e?.drops??{})){
      present.add(drop.id)
      let node=this.livingNodes.get(drop.id)
      if(!node){
        node=new Container();node.addChild(new Graphics().roundRect(-5,-9,10,10,3).fill(0xc2a66d).moveTo(-3,-7).lineTo(3,-7).stroke({color:0x574e35,width:2}))
        this.entities.addChild(node);this.livingNodes.set(drop.id,node)
      }
      node.position.set((drop.position.x+.5)*TILE,(drop.position.y+.7)*TILE);node.zIndex=node.y
    }
    for(const [key,node] of this.livingNodes)if(!present.has(key)){node.destroy({children:true});this.livingNodes.delete(key)}
  }
  private syncChunks(){
    for(const [key,chunk] of Object.entries(this.chunkData))if(!this.chunks.has(key))this.renderChunk(chunk)
    for(const [key,chunk] of this.chunks)if(!(key in this.chunkData)){
      chunk.node.destroy({children:true});chunk.resources.forEach(id=>{this.resources.get(id)?.sprite.destroy({children:true});this.resources.delete(id)})
      this.chunks.delete(key)
    }
  }
  update(snapshot:Snapshot){
    if(!this.ready)return
    const fresh=this.last?.run_id!==snapshot.run_id,tickChanged=this.last?.state.tick!==snapshot.state.tick
    const pauseChanged=this.last?.state.status==='running'&&snapshot.state.status==='paused'
    const w=snapshot.state
    this.duration=Math.max(60,Math.min(1000,w.status==='paused'?250:snapshot.tick_ms))
    if(fresh){
      this.hoveredBuilding=null
      this.terrainLayer.removeChildren().forEach(c=>c.destroy({children:true}))
      this.entities.removeChildren().forEach(c=>c.destroy({children:true}));this.livingNodes.clear()
      this.terrainEditsLayer.removeChildren().forEach(c=>c.destroy({children:true}));this.terrainEdits.clear();this.chunks.clear();this.resources.clear();this.buildings.clear();this.humans.clear();this.chunkData={};this.lastWanted='';this.dust=[]
      this.lights.removeChildren().forEach(c=>c.destroy({children:true}))
      const center=Object.values(w.settlements)[0]?.center??{x:0,y:0}
      this.camera?.configure(w.config.infinite,w.config.width,w.config.height,center)
      if(!w.config.infinite){
        for(const t of w.tiles)this.terrainLayer.addChild(this.ground(t.terrain,t.position.x,t.position.y))
        for(const r of Object.values(w.resources)){
          const sprite=this.sprite(RESOURCE_ASSET[r.kind],r.kind==='wood'?52:34)
          sprite.position.set(r.position.x*TILE+16,r.position.y*TILE+27);sprite.zIndex=sprite.y
          this.entities.addChild(sprite);this.resources.set(r.id,{sprite,resource:r})
        }
      }
    }
    for(const [key,tile] of Object.entries(w.terrain_modifications)){
      const old=this.terrainEdits.get(key)
      if(old?.label===tile.terrain)continue
      old?.destroy({children:true})
      const node=new Container();node.label=tile.terrain
      node.addChild(this.ground(tile.terrain,tile.position.x,tile.position.y))
      if(!tile.walkable)node.addChild(new Graphics().roundRect(tile.position.x*TILE+3,tile.position.y*TILE+3,TILE-6,TILE-6,3).fill(0x777e86).stroke({color:0x40474e,width:2}))
      this.terrainEditsLayer.addChild(node);this.terrainEdits.set(key,node)
    }
    for(const a of Object.values(w.agents)){
      let h=this.humans.get(a.id)
      if(!h){h=new Human(a,this.assets,id=>{if(!this.camera?.dragged)this.select(id)});this.humans.set(a.id,h);this.entities.addChild(h.node);h.node.position.set(a.position.x*TILE+16,a.position.y*TILE+27)}
      if(fresh||tickChanged||pauseChanged){
        h.from={x:h.node.x,y:h.node.y};h.to={x:a.position.x*TILE+16,y:a.position.y*TILE+27}
        const dx=h.to.x-h.from.x,dy=h.to.y-h.from.y
        if(Math.abs(dx)+Math.abs(dy)>1)h.direction=Math.abs(dx)>Math.abs(dy)?(dx<0?2:3):(dy<0?1:0)
        h.progress=fresh||pauseChanged?1:0
        if(h.progress===1)h.node.position.set(h.to.x,h.to.y)
      }
      h.agent=a
    }
    for(const b of Object.values(w.buildings)){
      let sprite=this.buildings.get(b.id)
      if(!sprite){sprite=b.assembly?this.assemblySprite(b):this.sprite(b.kind,b.kind==='watchtower'?68:b.kind==='shelter'?64:48);this.entities.addChild(sprite);this.buildings.set(b.id,sprite)}
      sprite.position.set(b.position.x*TILE+16,b.position.y*TILE+28);sprite.zIndex=sprite.y+1
      sprite.alpha=b.durability<=0?.2:b.progress<100?.35+b.progress/200:.45+.55*b.durability/100
    }
    this.influence.clear()
    for(const s of Object.values(w.settlements)){
      this.influence.ellipse((s.center.x+.5)*TILE,(s.center.y+.5)*TILE,s.influence*TILE,s.influence*TILE).stroke({color:'#d8ba75',width:1,alpha:.22})
    }
    this.syncLife(snapshot)
    this.last=snapshot;this.drawDestination();this.syncChunks()
    for(const [id,r] of this.resources){
      const mod=w.resource_modifications[id],isFood=r.resource.kind==='food'
      const interval=w.config.regeneration_ticks*(isFood?24:1)
      const gains=mod&&interval?Math.max(0,isFood?Math.floor((w.tick-mod.tick)/interval):Math.floor(w.tick/interval)-Math.floor(mod.tick/interval)):0
      const quantity=w.config.infinite?(mod?Math.min(r.resource.capacity,mod.quantity+gains):r.resource.capacity):(w.resources[id]?.quantity??0)
      r.sprite.alpha=quantity>0?1:.22
    }
    if(tickChanged&&this.lastEffectTick!==w.tick&&useWorld.getState().effects){
      this.lastEffectTick=w.tick
      for(const a of Object.values(w.agents))if(a.current_action==='GATHER'||a.current_action==='BUILD'){
        for(let i=0;i<3;i++){const g=new Graphics().rect(0,0,2,2).fill(a.current_action==='BUILD'?'#f0d5a0':'#d9d98d');g.position.set((a.position.x+.5)*TILE+i*4-4,(a.position.y+.5)*TILE);this.entities.addChild(g);this.dust.push({g,life:600})}
      }
    }
  }
  private drawDestination(){
    this.destination.clear();const a=this.selected?this.last?.state.agents[this.selected]:null
    if(a?.destination)this.destination.roundRect(a.destination.x*TILE+3,a.destination.y*TILE+3,TILE-6,TILE-6,4).stroke({color:'#ffe3a2',width:2,alpha:.8})
  }
  private frame(delta:number){
    this.time+=delta/1000;this.frames++;this.frameMs+=delta;this.reportMs+=delta
    const state=useWorld.getState()
    if(state.follow&&this.selected&&!this.camera?.manual){const a=this.last?.state.agents[this.selected];if(a)this.camera?.follow(a.position)}
    if(state.follow&&this.camera?.manual)useWorld.setState({follow:false})
    this.camera?.update(delta)
    for(const [id,node] of this.buildings)for(const child of node.children){
      if(child.label==='assembly-name')child.visible=this.scene.scale.x>=1.3||this.hoveredBuilding===id
    }
    const bounds=this.camera?.bounds()
    for(const h of this.humans.values()){
      h.progress=Math.min(1,h.progress+delta/this.duration)
      h.node.position.set(h.from.x+(h.to.x-h.from.x)*h.progress,h.from.y+(h.to.y-h.from.y)*h.progress);h.node.zIndex=h.node.y+2
      const target=h.agent.destination
      const mining=target?[...this.resources.values()].some(r=>r.resource.position.x===target.x&&r.resource.position.y===target.y&&['stone','ore','fuel'].includes(r.resource.kind)):false
      h.draw(this.time,h.agent.id===this.selected,this.last?.state.status==='running',mining)
      h.node.visible=!bounds||(h.agent.position.x>=bounds.left-2&&h.agent.position.x<=bounds.right+2&&h.agent.position.y>=bounds.top-2&&h.agent.position.y<=bounds.bottom+2)
    }
    let visible=0
    for(const chunk of this.chunks.values()){
      const data=this.chunkData[chunk.key]
      if(!data||!bounds)continue
      chunk.node.visible=data.cx*32<bounds.right+2&&(data.cx+1)*32>bounds.left-2&&data.cy*32<bounds.bottom+2&&(data.cy+1)*32>bounds.top-2
      chunk.resources.forEach(id=>{const r=this.resources.get(id);if(r)r.sprite.visible=chunk.node.visible})
      if(chunk.node.visible){visible++;if(state.effects){chunk.water.forEach((s,i)=>{s.tint=Math.floor(this.time*2+i)%3===0?0xd8f0ee:0xffffff});chunk.trees.forEach((s,i)=>{s.rotation=Math.sin(this.time*1.2+i)*.009})}}
    }
    for(let i=this.dust.length-1;i>=0;i--){const p=this.dust[i];p.life-=delta;p.g.y-=delta*.012;p.g.alpha=Math.max(0,p.life/600);if(p.life<=0){p.g.destroy();this.dust.splice(i,1)}}
    this.drawAtmosphere(state.effects)
    if(this.reportMs>=300&&bounds){
      this.reportMs=0
      useWorld.setState({cameraBounds:bounds,renderedChunks:visible,fps:Math.round(this.frames*1000/Math.max(1,this.frameMs))})
      if(this.frameMs>=1000){this.frames=0;this.frameMs=0}
      for(const [key,value] of Object.entries(bounds))this.host.dataset[`camera${key[0].toUpperCase()+key.slice(1)}`]=value.toFixed(4)
      if(this.last?.state.config.infinite){
        const coords:number[][]=[]
        for(let cy=Math.floor(bounds.top/32);cy<=Math.floor(bounds.bottom/32);cy++)for(let cx=Math.floor(bounds.left/32);cx<=Math.floor(bounds.right/32);cx++)coords.push([cx,cy])
        const centerX=(bounds.left+bounds.right)/64,centerY=(bounds.top+bounds.bottom)/64
        coords.sort((a,b)=>(a[0]-centerX)**2+(a[1]-centerY)**2-((b[0]-centerX)**2+(b[1]-centerY)**2))
        const wanted=coords.slice(0,25),signature=wanted.map(c=>c.join(',')).join('|')
        const missing=wanted.filter(c=>!this.chunkData[c.join(',')])
        if(signature!==this.lastWanted||(missing.length&&this.time-this.requestTime>2)){
          requestChunks(missing.length?missing:wanted);this.lastWanted=signature;this.requestTime=this.time
        }
      }
    }
  }
  private drawAtmosphere(effects:boolean){
    const env=this.last?.environment
    this.atmosphere.clear();this.weather.clear()
    const darkness=Math.min(.34, Math.max(0, Math.cos((env?.phase??.5)*Math.PI*2))*.26+((env?.weather==='rain'||env?.weather==='storm')?.08:0))
    if(effects&&darkness)this.atmosphere.rect(0,0,this.app.screen.width,this.app.screen.height).fill({color:'#172d4d',alpha:darkness})
    if(effects&&(env?.weather==='rain'||env?.weather==='storm'))for(let i=0;i<45;i++){
      const x=(i*97+this.time*24)%this.app.screen.width,y=(i*61+this.time*210)%this.app.screen.height
      this.weather.moveTo(x,y).lineTo(x-3,y+10).stroke({color:'#d1e6dd',width:1,alpha:.2})
    }
    // Lightweight additive firelight and animated flames use the authored campfire sprite.
    this.lights.removeChildren().forEach(c=>c.destroy({children:true}))
    if(!effects||!this.last)return
    for(const b of Object.values(this.last.state.buildings))if(b.kind==='campfire'&&b.fuel>0&&b.progress===100){
      const sprite=this.buildings.get(b.id)
      if(sprite){sprite.scale.y=Math.abs(sprite.scale.y)*(1+Math.sin(this.time*10)*.0008)}
      const x=this.scene.x+(b.position.x+.5)*TILE*this.scene.scale.x,y=this.scene.y+(b.position.y+.5)*TILE*this.scene.scale.x
      const glow=new Graphics()
      for(let i=5;i>0;i--)glow.circle(x,y,(15+i*12)*this.scene.scale.x).fill({color:'#ffc477',alpha:(env?.night?.035:.012)*(1+Math.sin(this.time*7)*.1)})
      glow.blendMode='add';this.lights.addChild(glow)
    }
  }
  destroy(){this.disposed=true;this.observer?.disconnect();this.camera?.destroy();if(this.ready)this.app.destroy(true,{children:true})}
}
