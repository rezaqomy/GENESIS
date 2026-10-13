# Phase 1 rules

All health, hunger and energy values are integers in 0–100. **Higher hunger means greater hunger; 100 means starvation**, not satiety. Each tick adds 1 hunger and subtracts 1 energy from living agents. Hunger ≥90 costs 3 health. Hunger <50 and energy >35 heals 1 health. Health reaching zero makes an agent permanently dead, clears its destination and stops further drives/actions. Dead agents do not block movement.

| Action | Preconditions | Outcome after physiology |
|---|---|---|
| MOVE | Living actor; Manhattan-adjacent target; inside world; walkable; not occupied; energy ≥2 | Integer position changes; energy −2 |
| GATHER | Living actor; resource distance ≤1; quantity >0; inventory total <8; energy ≥3 | Resource −1; matching inventory +1; energy −3 |
| EAT | Living actor; inventory food >0 | Food −1; hunger −35 (floor 0) |
| REST | Living actor | Energy +14 (cap 100) |
| IDLE | Living actor | No action change beyond physiology |

Resource tiles are walkable; bushes/trees represent gatherable objects. Water and rocks are solid obstacles. All agents spawn uniquely in the largest walkable component; resources are generated in that component. Agents cannot teleport, cross obstacles or overlap living agents. Gathering can occur from the same tile or an adjacent cardinal tile.

Actions resolve in ascending agent ID order. The lowest ID wins contention for an empty tile or the last resource unit. Later actors validate against the already-updated state. Moving into a tile vacated by an earlier actor is legal; swapping occupied positions in the same tick is rejected. Only one intent per actor is resolved. Rejected intents produce a recorded reason and leave the actor idle.

Every 20 ticks (configurable, 0 disables), every resource gains one unit up to its capacity. Gather and regeneration happen in that order. Food resources are berry bushes; wood resources are trees. The survival policy prioritizes food, so agents do not collect wood without a purpose in this phase; the GATHER resolver fully supports wood.

The rule policy uses copied observations only, not global state. It eats at hunger ≥55, rests below energy 18 (so it can perform survival work), acquires up to three food units, rests below energy 40 if food is unavailable/unneeded, then explores. BFS chooses the shortest reachable food approach with resource ID tie breaking. Exploration uses a local seeded generator derived from seed, agent ID and tick; it preserves a visible reachable destination until arrival. No wall-clock time or Python hash randomization is used in decisions.

The world starts paused. Start/resume advances automatically; pause freezes ticks; step advances exactly one tick while remaining paused. Allowed speeds: 0.5, 1, 2, 4, 8. Reset preserves the configured map dimensions/count/regeneration, uses the requested seed, returns to tick 0 and speed 1, and archives the previous run by leaving its events intact.

## Phase 2 infinite-mode rules

The original rules above remain the finite-mode compatibility contract. Infinite mode uses signed 32×32 chunks, ten unique nearby spawns and a seeded safe camp. Hunger/health/energy remain 0–100; high hunger is worse. Personality and psychology are 0–1, with high loneliness/fear/stress/homesickness worse and high mood/safety/satisfaction/attachment better.

Resource regeneration adds one unit per elapsed global `regeneration_ticks` boundary to a sparse harvested quantity, capped at original capacity. It occurs identically in inactive chunks. Zero disables regeneration. Static terrain has no background tick; durable buildings are persistent entities updated independently of chunk activation. Camera requests neither advance time nor discover locations for agents.

Goals expose clipped 0–1 scores and signed factors. Default weight groups: need .55, trait .25, reward .20, travel .18, risk .22, social .15, scarcity .24. Factors already contain goal-specific coefficients; configured weights scale each coefficient by its ratio to the default group weight. Scores are sums clipped to [0,1], not probabilities. Ties use goal name. Six-tick commitment and .09 hysteresis prevent unnecessary switches; hunger >=85 prioritizes valid food goals, energy <12 prioritizes selected rest. Three failures trigger eight-tick cooldown. These rules are recorded in decisions.

Exploration has a budget of `60 + floor(independence*140)` accepted exploration moves. Near-home movement resets the budget. Exploration avoids the last12 movement positions to prevent short loops at blocked frontiers. Food memory records observed food only, rather than assuming every discovered resource is edible. Loneliness, fatigue, cargo, danger, attachment and budget motivate homeward goals. Remote camps can support optional migration when independence >.72, loyalty <.35 and actual time away >120 ticks.

Day length is 240 ticks. Nights occupy phase <.12 or >=.72. Weather changes every120 ticks from seeded samples. Unsheltered cold exposure costs one health every8 ticks. Nearby compatible peers reduce loneliness, build affinity and improve mood; crowding adds stress. Local safety is calculated from peers, environmental cold, fueled fires, durable shelters/walls/towers. Shelter rest restores more energy than exposed rest.

Structures cost actual materials on creation and require four adjacent build actions, each advancing progress25 and costing4 energy. Recipes are defined in `settlements/effects.py`. Storage adds80 communal capacity and enables nearby transfers; the initial camp has a small cache. Campfire consumes1 fuel every12 ticks; refuel consumes1 inventory/shared fuel and adds4 fire fuel. Workbench enables axe/pickaxe/torch crafting. Torches provide local light/protection and small warmth within3 tiles, losing1 durability every12 night ticks. Axe and pickaxe improve gathering to2 units and lose1 durability per use. Farms consume1 shared water to yield2 food every24 ticks. Walls/towers block their tile and protect nearby agents; towers extend sight from8 to12. Bridges permit water crossing. Roads reduce movement energy cost. Shelters/remote camps reduce exposure and improve rest. Every240 ticks maintained structures consume1 shared wood or lose5 durability. Incomplete/destroyed structures provide no benefit.

Distant builders can withdraw and haul project supplies from the shared cache. The communal construction radius is8, transfer radius2, and workbench/build/refuel radius1. Each action is revalidated at resolution; stable actor order determines the winner in contention. Settlements pay maintenance, face limited food/storage, local depletion and crowding. Shared project sites are public settlement plans; individual utilities decide who works, explores or rests.
