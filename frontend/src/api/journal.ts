import type { Snapshot, WorldEvent } from '../types/world'
import { useWorld } from '../stores/world'

interface JournalPage { run_id:string; events:WorldEvent[]; next_sequence:number }
type ReadJournal=(runId:string,after:number,through:number,signal:AbortSignal)=>Promise<JournalPage>

const readJournal:ReadJournal=async(runId,after,through,signal)=>{
  const query=new URLSearchParams({run_id:runId,after:String(after),through:String(through)})
  const response=await fetch(`/api/journal?${query}`,{signal})
  if(!response.ok)throw new Error('Could not recover world journal')
  return await response.json() as JournalPage
}

/** State packets may be dropped; the journal has its own coverage cursor. */
export class JournalSync {
  private runId:string|null=null
  private cursor=0
  private target=0
  private generation=0
  private pending=false
  private disposed=false
  private controller:AbortController|null=null

  constructor(private read:ReadJournal=readJournal){}

  observe(snapshot:Snapshot){
    if(this.disposed)return
    if(snapshot.run_id!==this.runId){
      this.controller?.abort()
      this.generation++
      this.runId=snapshot.run_id
      this.cursor=0
      this.target=0
      this.pending=false
    }
    this.target=Math.max(this.target,snapshot.sequence_number)
    if(snapshot.events_after!=null&&snapshot.events_after<=this.cursor){
      this.cursor=Math.max(this.cursor,snapshot.sequence_number)
    }
    if(!this.pending&&this.cursor<this.target)void this.recover()
  }

  private async recover(){
    const generation=this.generation,runId=this.runId
    if(!runId)return
    this.pending=true
    const controller=new AbortController()
    const timeout=setTimeout(()=>controller.abort(),10000)
    this.controller=controller
    try{
      while(!this.disposed&&generation===this.generation&&this.cursor<this.target){
        const through=this.target
        const page=await this.read(runId,this.cursor,through,controller.signal)
        if(this.disposed||generation!==this.generation)return
        if(page.run_id!==runId||page.next_sequence>through||page.next_sequence<=this.cursor)break
        useWorld.getState().mergeEvents(runId,page.events)
        this.cursor=Math.max(this.cursor,page.next_sequence)
      }
    }catch{
      if(!this.disposed&&generation===this.generation&&!controller.signal.aborted){
        useWorld.setState({error:'World journal recovery failed; retrying on the next update'})
      }
    }finally{
      clearTimeout(timeout)
      if(generation===this.generation)this.pending=false
    }
  }

  close(){this.disposed=true;this.controller?.abort()}
}
