export type Position = { x: number; y: number }
export type Action = 'MOVE' | 'GATHER' | 'EAT' | 'REST' | 'IDLE'
export interface Agent {
  id: string; name: string; age: number; visual_color: string
  health: number; hunger: number; energy: number; position: Position
  inventory: { food: number; wood: number; capacity: number }
  destination: Position | null; current_action: Action; alive: boolean
}
export interface Resource { id: string; position: Position; kind: 'food' | 'wood'; quantity: number; capacity: number }
export interface World {
  config: { seed: number; width: number; height: number; agent_count: number; regeneration_ticks: number }
  tick: number; status: 'running' | 'paused'; speed: number
  tiles: { position: Position; terrain: 'grass' | 'forest' | 'water' | 'rock' | 'soil'; walkable: boolean }[]
  agents: Record<string, Agent>; resources: Record<string, Resource>
}
export interface WorldEvent {
  event_id: string; run_id: string; sequence_number: number; tick: number
  event_type: string; actor_id: string | null; payload: { message?: string; action?: Action }; schema_version: number
}
export interface Snapshot { type: 'snapshot'; run_id: string; sequence_number: number; tick_ms: number; state: World; state_hash: string; events: WorldEvent[] }
