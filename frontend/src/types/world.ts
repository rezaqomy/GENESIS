export type Position = { x: number; y: number }
export type ResourceKind = 'food' | 'wood' | 'stone' | 'fiber' | 'clay' | 'ore' | 'fuel' | 'water' | 'seeds'
export const resourceKinds: ResourceKind[] = ['food','wood','stone','fiber','clay','ore','fuel','water','seeds']
export type Action = 'TILL' | 'PLANT' | 'WATER_CROP' | 'HARVEST' | 'FEED' | 'BREED' | 'COLLECT' | 'ATTACK' | 'STEAL' | 'PICK_UP' | 'EXPERIMENT_ASSEMBLY' | 'ASSEMBLE' | 'OPERATE' | 'HEAT' | 'DISMANTLE' | 'OFFER_TRADE' | 'ACCEPT_TRADE' | 'DIG' | 'MINE' | 'PLACE_BLOCK' | 'MOVE' | 'GATHER' | 'EAT' | 'REST' | 'IDLE' | 'SOCIALIZE' | 'STORE' | 'WITHDRAW' | 'CRAFT' | 'BUILD' | 'REFUEL' | 'EXPERIMENT' | 'EXPERIMENT_TOOL' | 'DISCARD' | 'GIVE' | 'REPAIR' | 'PROPOSE_PROJECT'
export type Personality = Record<'sociability'|'curiosity'|'risk_tolerance'|'independence'|'cooperation'|'ambition'|'resourcefulness'|'loyalty'|'comfort_preference'|'exploration_drive',number>
export interface Psychology { loneliness:number; fear:number; stress:number; mood:number; sense_of_safety:number; satisfaction:number; homesickness:number; attachment:number; social_satisfaction:number }
export interface CandidateGoal {goal:string;utility:number;factors:Record<string,number>;rejection:string|null}
export interface Decision {selected_goal:string;candidates:CandidateGoal[];factors:Record<string,number>;plan:string[];target:Position|null;selected_tick:number;commitment_until:number;progress:number;failures:number;cooldowns:Record<string,number>}
export type Inventory = Record<ResourceKind,number> & { capacity:number; products?:Record<string,number>; tools:Record<string,number> }
export interface MemoryRecord {id:string;tick:number;kind:'action'|'failure'|'dialogue'|'reflection';text:string;goal:string;action:string;context:string;outcome:number;importance:number;position:Position;target:Position|null;peer_id:string|null}
export interface AgentMemory {
  short_term:MemoryRecord[];long_term:MemoryRecord[];recalled_ids:string[]
  facts:Record<string,{resource_id:string;position:Position;quantity:number;observed_tick:number}>
  lessons:Record<string,{goal:string;action:string;context:string;samples:number;mean_outcome:number;updated_tick:number}>
}
export interface Agent {
  combat?:{last_attack_tick:number;attacker_id:string|null;attacked_tick:number;death_cause:string}|null
  workshop?:WorkshopKnowledge|null
  housing?:HousingKnowledge|null
  inventions?:ToolKnowledge|null
  vision_radius?:number
  task?:TaskPlan|null;task_history?:TaskOutcome[];skills?:Record<string,VerifiedSkill>
  memory?: AgentMemory|null
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
export type BuildingKind = 'assembly' | 'campfire'|'shelter'|'storage'|'workbench'|'farm'|'wooden_wall'|'stone_wall'|'watchtower'|'bridge'|'road'|'remote_camp'
export interface ShelterDesign {frame:'wood'|'stone';roof:'fiber'|'wood';bracing:boolean;raised_foundation:boolean}
export interface HousingKnowledge {
  trials:{design:ShelterDesign;tick:number;score:number;stood:boolean;source:'experiment'|'study'}[]
  practice:number;experiment:ShelterDesign|null;experiment_steps:number;studying_id:string|null
  insights:string[];observed_failures:Record<string,number>
}
export interface ToolDesign {
  core:'wood'|'stone'|'fiber'|'clay'|'ore';grip:'none'|'wood'|'stone'|'fiber'
  binding:'none'|'fiber'|'clay';form:'rounded'|'edge'|'point'|'wrapped';length:number;fueled:boolean
}
export interface ToolTrial {
  design:ToolDesign;tick:number;performance:Record<'cut'|'mine'|'light',number>
  feedback:string[];source:'experiment'|'study'|'craft'
}
export interface ToolKnowledge {
  trials:ToolTrial[];designs:Record<string,ToolTrial>;practice:number
  experiment:ToolDesign|null;experiment_steps:number;studying_peer:string|null
}
export interface AssemblyDesign {
  name:string;parts:{material:string;shape:string;count:number}[]
  joint:string;mechanism:string;enclosed:boolean
}
export interface AssemblyTrial {design:AssemblyDesign;tick:number;measured:Record<string,number>;feedback:string[];source:string}
export interface WorkshopKnowledge {
  trials:AssemblyTrial[];proposals:AssemblyDesign[];experiment:AssemblyDesign|null;steps:number
  transformations:Record<string,string>
  offer:{id:string;peer_id:string;give_item:string;give_amount:number;want_item:string;want_amount:number;expires:number}|null
}
export interface Building { assembly?:AssemblyTrial|null;last_operated_tick?:number;salvaged?:boolean; id:string;kind:BuildingKind;position:Position;settlement_id:string|null;owner_id:string|null;progress:number;durability:number;fuel:number;food:number;created_tick:number;design?:ShelterDesign|null;quality?:number;work_units?:number;contributors?:string[];last_damage_cause?:string }
export interface CommunityProject {id:string;kind:string;target:Position;proposer_id:string;created_tick:number;deadline:number;status:'active'|'completed'|'expired';cost:Record<string,number>;contributors:Record<string,number>}
export interface CommunityState {projects:CommunityProject[];contributions:Record<string,Record<string,number>>;meals_given:number;repairs:number;projects_completed:number}
export interface Settlement { community?:CommunityState|null;id:string;name:string;center:Position;members:string[];storage:Inventory;buildings:string[];food_reserves:number;safety:number;comfort:number;resource_availability:number;social_cohesion:number;influence:number;crowding:number;exploration_activity:number }
export interface Animal {id:string;species:'sheep'|'cow'|'chicken';position:Position;born_tick:number;health:number;hunger:number;owner_id:string|null;trust:number;ready_until:number;breed_after:number;produce_after:number}
export interface Crop {id:string;position:Position;owner_id:string;planted_tick:number;growth:number;moisture:number;health:number}
export interface DroppedItems {id:string;position:Position;inventory:Inventory;expires:number;owner_id:string|null}
export interface Ecosystem {animals:Record<string,Animal>;crops:Record<string,Crop>;drops:Record<string,DroppedItems>}
export interface World {
  ecosystem?:Ecosystem|null
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
  event_type: string; actor_id: string | null; payload: { peer_id?: string; message?: string; action?: Action;goal?:string;factors?:Record<string,number> }; schema_version: number
}
export interface ChunkView {key:string;cx:number;cy:number;terrain:string;walkable:string;resources:Record<string,Resource>;generator_version:number}
export interface ChunkMessage {type:'chunks';run_id:string;sequence_number:number;tick:number;chunks:ChunkView[]}
export interface Environment {day:number;phase:number;night:boolean;weather:'rain'|'wind'|'clear'|'storm';cold:number;wind_strength?:number}
export interface Metrics {tick_duration_ms:number;decision_duration_ms:number;active_chunks:number;loaded_chunks:number;visual_cached_chunks:number;payload_bytes:number}
export interface Snapshot { type: 'snapshot'|'entities'; run_id: string; sequence_number: number; tick_ms: number; state: World; state_hash: string; events: WorldEvent[]; events_after?:number|null; environment?:Environment;metrics?:Metrics }
export interface TaskPlan {
  id:string;kind:'forage'|'construction'|'expedition';context:string;stage:string
  status:'active'|'succeeded'|'failed'|'cancelled';started_tick:number;last_progress_tick:number;deadline:number
  target:Position|null;actions:number;energy_spent:number;exploration_moves:number;reason:string
}
export interface TaskOutcome {id:string;kind:string;status:'succeeded'|'failed'|'cancelled';reason:string;started_tick:number;ended_tick:number;actions:number;energy_spent:number;food_delta:number;hunger_delta:number;discoveries:number}
export interface VerifiedSkill {kind:string;context:string;stages:string[];successes:number;failures:number;mean_ticks:number;updated_tick:number}
