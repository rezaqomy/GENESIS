export type Position = { x: number; y: number }
export type ResourceKind = 'food' | 'wood' | 'stone' | 'fiber' | 'clay' | 'ore' | 'fuel' | 'water' | 'seeds'
export const resourceKinds: ResourceKind[] = ['food','wood','stone','fiber','clay','ore','fuel','water','seeds']
export type Action = 'MOVE' | 'GATHER' | 'EAT' | 'REST' | 'IDLE' | 'SOCIALIZE' | 'STORE' | 'WITHDRAW' | 'CRAFT' | 'BUILD' | 'REFUEL'
export type Personality = Record<'sociability'|'curiosity'|'risk_tolerance'|'independence'|'cooperation'|'ambition'|'resourcefulness'|'loyalty'|'comfort_preference'|'exploration_drive',number>
export interface Psychology { loneliness:number; fear:number; stress:number; mood:number; sense_of_safety:number; satisfaction:number; homesickness:number; attachment:number; social_satisfaction:number }
export interface CandidateGoal {goal:string;utility:number;factors:Record<string,number>;rejection:string|null}
export interface Decision {selected_goal:string;candidates:CandidateGoal[];factors:Record<string,number>;plan:string[];target:Position|null;selected_tick:number;commitment_until:number;progress:number;failures:number;cooldowns:Record<string,number>}
export type Inventory = Record<ResourceKind,number> & { capacity:number; tools:Record<string,number> }
export interface Agent {
  memories?: {tick:number;kind:string;text:string;goal:string;outcome:number;peer_id:string|null}[]
  habits?: Record<string,number>; cognition_source?:string; thought?:string
  id: string; name: string; age: number; visual_color: string
  health: number; hunger: number; energy: number; position: Position
  inventory: Inventory; destination: Position | null; current_action: Action; alive: boolean
  personality:Personality; psychology:Psychology; decision:Decision; settlement_id:string|null
  home:Position; known_chunks:string[]; discoveries:Position[];food_memory:Record<string,number>; exploration_steps:number; time_away:number
  lifestyle:'settler'|'wanderer'; nearby_agents:string[]; relationships:Record<string,number>
}
export interface Resource { id: string; position: Position; kind: ResourceKind; quantity: number; capacity: number }
export type Terrain = 'grass'|'forest'|'water'|'rock'|'soil'|'sand'|'mountain'|'path'
export type BuildingKind = 'campfire'|'shelter'|'storage'|'workbench'|'farm'|'wooden_wall'|'stone_wall'|'watchtower'|'bridge'|'road'|'remote_camp'
export interface Building { id:string;kind:BuildingKind;position:Position;settlement_id:string|null;owner_id:string|null;progress:number;durability:number;fuel:number;food:number;created_tick:number }
export interface Settlement { id:string;name:string;center:Position;members:string[];storage:Inventory;buildings:string[];food_reserves:number;safety:number;comfort:number;resource_availability:number;social_cohesion:number;influence:number;crowding:number;exploration_activity:number }
export interface World {
  config: { seed: number; width: number; height: number; agent_count: number; regeneration_ticks: number;infinite:boolean;chunk_size:number;generator_version:number;active_radius:number;chunk_cache_size:number }
  tick: number; status: 'running' | 'paused'; speed: number
  tiles: { position: Position; terrain: Terrain; walkable: boolean }[]
  agents: Record<string, Agent>; resources: Record<string, Resource>
  buildings:Record<string,Building>;settlements:Record<string,Settlement>
  resource_modifications:Record<string,{quantity:number;tick:number;capacity:number}>
  terrain_modifications:Record<string,{position:Position;terrain:Terrain;walkable:boolean}>
  explored_chunks:string[]
}
export interface WorldEvent {
  event_id: string; run_id: string; sequence_number: number; tick: number
  event_type: string; actor_id: string | null; payload: { message?: string; action?: Action;goal?:string;factors?:Record<string,number> }; schema_version: number
}
export interface ChunkView {key:string;cx:number;cy:number;terrain:string;walkable:string;resources:Record<string,Resource>;generator_version:number}
export interface ChunkMessage {type:'chunks';run_id:string;sequence_number:number;tick:number;chunks:ChunkView[]}
export interface Environment {day:number;phase:number;night:boolean;weather:'rain'|'wind'|'clear';cold:number}
export interface Metrics {tick_duration_ms:number;decision_duration_ms:number;active_chunks:number;loaded_chunks:number;visual_cached_chunks:number;payload_bytes:number}
export interface Snapshot { type: 'snapshot'|'entities'; run_id: string; sequence_number: number; tick_ms: number; state: World; state_hash: string; events: WorldEvent[]; environment?:Environment;metrics?:Metrics }
