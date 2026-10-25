import { Container, Graphics, Rectangle, Sprite, Text, Texture } from 'pixi.js'
import type { Agent } from '../../types/world'
import type { GameAssets } from '../rendering/assets'
export class Human {
  node=new Container();ring=new Graphics();body=new Container();label:Text;indicator:Text
  sprite:Sprite|null=null;frames:Texture[]=[];fallback=new Graphics()
  from={x:0,y:0};to={x:0,y:0};progress=1;direction=0;agent:Agent
  constructor(agent:Agent,assets:GameAssets,select:(id:string)=>void) {
    this.agent=agent
    const sheet=assets.get(`character_${Number(agent.id.slice(-2))%4}`)
    if(sheet) {
      for(let row=0;row<32;row++)for(let col=0;col<4;col++)this.frames.push(new Texture({source:sheet.source,frame:new Rectangle(col*48,row*48,48,48)}))
      this.sprite=new Sprite(this.frames[0]);this.sprite.anchor.set(.5,1);this.sprite.width=48;this.sprite.height=48
      this.body.addChild(this.sprite)
    }else this.body.addChild(this.fallback)
    this.node.addChild(this.ring,this.body)
    this.label=new Text({text:agent.name,style:{fontFamily:'monospace',fontSize:10,fontWeight:'bold',fill:'#fff5d8',stroke:{color:'#172f29',width:3}}})
    this.label.anchor.set(.5,1);this.label.y=-37
    this.indicator=new Text({text:'',style:{fontFamily:'monospace',fontSize:8,fill:'#ffdfa0',stroke:{color:'#24372f',width:3}}})
    this.indicator.anchor.set(.5,0);this.indicator.y=3
    this.node.addChild(this.label,this.indicator)
    this.node.eventMode='static';this.node.cursor='pointer';this.node.hitArea=new Rectangle(-14,-37,28,43)
    this.node.on('pointertap',()=>select(agent.id))
  }
  draw(time:number,selected:boolean,running:boolean,mining=false) {
    const a=this.agent,walking=this.progress<1||a.current_action==='MOVE'
    let action=walking?1:0
    if(!walking)action=({EXPERIMENT_ASSEMBLY:5,ASSEMBLE:4,OPERATE:2,HEAT:5,DISMANTLE:3,OFFER_TRADE:7,ACCEPT_TRADE:7,DIG:3,MINE:3,PLACE_BLOCK:4,GATHER:mining?3:2,REPAIR:4,GIVE:7,PROPOSE_PROJECT:7,BUILD:4,CRAFT:5,EXPERIMENT:5,EXPERIMENT_TOOL:5,REST:6,SOCIALIZE:7,REFUEL:2,STORE:2,WITHDRAW:2,EAT:2,IDLE:0,MOVE:1} as Record<string,number>)[a.current_action]??0
    const frame=running||this.progress<1?Math.floor(time*(action===1?7:3))%4:0
    if(this.sprite)this.sprite.texture=this.frames[(this.direction*8+action)*4+frame]
    else {
      const g=this.fallback.clear();g.rect(-5,-10,4,10).fill('#2f4252');g.rect(1,-10,4,10).fill('#2f4252');g.rect(-7,-24,14,15).fill(a.visual_color);g.rect(-5,-33,10,10).fill('#dfb18c');g.rect(-6,-35,12,4).fill('#684535')
    }
    this.ring.clear().ellipse(0,0,10,3).fill({color:'#152820',alpha:.25})
    if(selected){this.ring.ellipse(0,0,14,5).stroke({color:'#f6dda0',width:2});this.ring.poly([-3,-45,3,-45,0,-40]).fill('#ffe8ae')}
    this.indicator.text=!a.alive?'†':({EXPERIMENT_ASSEMBLY:'testing invention',ASSEMBLE:'fabricating',OPERATE:'operating device',HEAT:'heating material',DISMANTLE:'salvaging',OFFER_TRADE:'offering trade',ACCEPT_TRADE:'bartering',DIG:'digging',MINE:'mining rock',PLACE_BLOCK:'placing block',GATHER:mining?'mining':'gathering',REPAIR:'repairing',GIVE:'sharing a meal',PROPOSE_PROJECT:'proposing project',BUILD:'building',CRAFT:'crafting',EXPERIMENT:'testing shelter',EXPERIMENT_TOOL:'inventing',REST:'z z',SOCIALIZE:'chatting',REFUEL:'tending fire',EAT:'eating',STORE:'storing',WITHDRAW:'resupply',MOVE:'',IDLE:''} as Record<string,string>)[a.current_action]??''
    this.node.alpha=a.alive?1:.4
  }
}
