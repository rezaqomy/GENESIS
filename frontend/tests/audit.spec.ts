import { expect, test } from '@playwright/test'

test('journal recovers dropped packets and ignores old-run recovery responses', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('Connected to simulation')).toBeVisible()
  const result=await page.evaluate(async()=>{
    // Vite loads the same modules as the application, including its live Zustand store.
    const {useWorld}=await import('/src/stores/world.ts')
    const {JournalSync}=await import('/src/api/journal.ts')
    const base=useWorld.getState().snapshot
    const calls:{runId:string;after:number;through:number}[]=[]
    const replies:((value:unknown)=>void)[]=[]
    const sync=new JournalSync((runId:string,after:number,through:number)=>{
      calls.push({runId,after,through})
      return new Promise(resolve=>replies.push(resolve))
    })
    const packet={...base,sequence_number:1000,events:[],events_after:null}
    const event=(runId:string,sequence:number)=>({
      event_id:`probe-${runId}-${sequence}`,run_id:runId,sequence_number:sequence,
      tick:0,event_type:'MESSAGE',actor_id:null,payload:{message:`recovered ${sequence}`},schema_version:1,
    })
    useWorld.getState().accept(packet)
    sync.observe(packet)
    replies[0]({run_id:packet.run_id,events:[event(packet.run_id,900)],next_sequence:1000})
    await new Promise(resolve=>setTimeout(resolve,0))
    const recovered=useWorld.getState().events.some((e:{sequence_number:number})=>e.sequence_number===900)
    sync.observe({...packet,sequence_number:1010,events_after:1000})
    const callsAfterContiguous=calls.length
    sync.observe({...packet,sequence_number:1200,events_after:1100})
    const gapRequest={...calls[1]}
    const next={...packet,run_id:'replacement-run',sequence_number:1}
    useWorld.getState().accept(next)
    sync.observe(next)
    replies[1]({run_id:packet.run_id,events:[event(packet.run_id,1150)],next_sequence:1200})
    replies[2]({run_id:next.run_id,events:[event(next.run_id,1)],next_sequence:1})
    await new Promise(resolve=>setTimeout(resolve,0))
    const finalEvents=useWorld.getState().events.map((e:{run_id:string})=>e.run_id)
    sync.close()
    return {recovered,callsAfterContiguous,gapRequest,finalEvents}
  })
  expect(result.recovered).toBeTruthy()
  expect(result.callsAfterContiguous).toBe(1)
  expect(result.gapRequest.after).toBe(1010)
  expect(result.gapRequest.through).toBe(1200)
  expect(result.finalEvents).toEqual(['replacement-run'])
})

test('Hold survives live-buffer eviction and resets with the world', async ({ page, request }) => {
  await request.post('/api/simulation/reset',{data:{seed:42}})
  await page.goto('/')
  await expect(page.getByText('Connected to simulation')).toBeVisible()
  async function insertEvents(start:number,count:number){
    await page.evaluate(async({start,count})=>{
      const {useWorld}=await import('/src/stores/world.ts')
      const snapshot=useWorld.getState().snapshot
      const events=Array.from({length:count},(_,index)=>({
        event_id:`hold-${start+index}`,run_id:snapshot.run_id,sequence_number:start+index,
        tick:0,event_type:'MESSAGE',actor_id:null,payload:{message:`hold event ${start+index}`},schema_version:1,
      }))
      useWorld.getState().mergeEvents(snapshot.run_id,events)
    },{start,count})
  }
  await insertEvents(100,300)
  await expect(page.locator('.event-row').first()).toContainText('hold event 399')
  await page.getByRole('button',{name:'● Live',exact:true}).click()
  const held=await page.locator('.event-list').innerText()
  await insertEvents(1000,1700)
  await expect(page.getByRole('button',{name:'○ Hold',exact:true})).toBeVisible()
  expect(await page.locator('.event-list').innerText()).toBe(held)
  await page.getByRole('button',{name:'○ Hold',exact:true}).click()
  await expect(page.locator('.event-row').first()).toContainText('hold event 2699')
  await page.getByRole('button',{name:'● Live',exact:true}).click()
  await request.post('/api/simulation/reset',{data:{seed:7}})
  await expect(page.getByRole('button',{name:'● Live',exact:true})).toBeVisible()
  await expect(page.locator('.event-list')).not.toContainText('hold event')
})
