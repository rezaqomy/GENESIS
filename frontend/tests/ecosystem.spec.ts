import { expect, test } from '@playwright/test'
import type { Snapshot } from '../src/types/world'

test('local animal inspection and world rendering after ecology starts', async ({page,request})=>{
  const errors:string[]=[]
  page.on('pageerror',e=>errors.push(e.message))
  await request.post('/api/simulation/reset',{data:{seed:42}})
  for(let i=0;i<32;i++)expect((await request.post('/api/simulation/step')).ok()).toBeTruthy()
  const snapshot:Snapshot=await (await request.get('/api/world')).json()
  const animals=Object.values(snapshot.state.ecosystem?.animals??{})
  expect(animals.length).toBeGreaterThan(0)
  const observer=Object.values(snapshot.state.agents).find(a=>animals.some(v=>Math.abs(v.position.x-a.position.x)+Math.abs(v.position.y-a.position.y)<=(a.vision_radius??8)))
  expect(observer).toBeDefined()
  if(!observer)throw new Error('No local observer near animals')
  await page.goto('/')
  await expect(page.getByText('Connected to simulation')).toBeVisible()
  await expect(page.locator('canvas')).toBeVisible()
  await expect(page.getByText('Preparing your world…')).toHaveCount(0)
  await page.getByRole('button',{name:`Inspect ${observer.name}`,exact:true}).click()
  await page.getByRole('button',{name:'Focus camera',exact:true}).click()
  await page.getByRole('button',{name:'Ecosystem',exact:true}).click()
  await expect(page.locator('.inspector-content')).toContainText('Animals ·')
  await expect(page.locator('.inspector-content')).toContainText('Trust')
  await expect(page.locator('.inspector-content')).toContainText('Crops ·')
  await page.screenshot({path:'../artifacts/genesis-ecosystem.png',fullPage:true})
  expect(errors).toEqual([])
})
