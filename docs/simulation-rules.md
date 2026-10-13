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
