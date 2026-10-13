import { Assets, Texture } from 'pixi.js'
interface AssetEntry {id:string;file:string;width:number;height:number;category:string;frames?:{cell_width:number;cell_height:number;directions:string[];actions:string[];frames_per_action:number}}
interface Manifest {assets:Record<string,AssetEntry>}
export class GameAssets {
  textures=new Map<string,Texture>()
  missing:string[]=[]
  manifest:Manifest|null=null
  async load() {
    try {
      const response=await fetch('/assets/genesis/manifest.json')
      if(!response.ok)throw new Error('Asset manifest unavailable')
      this.manifest=await response.json() as Manifest
      await Promise.all(Object.entries(this.manifest.assets).map(async([id,entry])=>{
        try {
          // Check availability first so a missing optional sprite does not crash Pixi.
          const response=await fetch(entry.file,{method:'HEAD'})
          if(!response.ok)throw new Error(`Missing ${id}`)
          const texture=await Assets.load<Texture>(entry.file)
          texture.source.scaleMode='nearest'
          this.textures.set(id,texture)
        } catch {this.missing.push(id)}
      }))
    } catch { this.missing.push('manifest') }
  }
  get(id:string) {return this.textures.get(id)}
}
