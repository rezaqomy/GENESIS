"""One-tick reservations, with local replanning and explicit yielding (not full MAPF)."""

from app.simulation.models.domain import Action
from app.simulation.pathfinding.astar import astar, local_waypoint


def coordinate_movements(observations, intents, tick):
    by_actor = {o.self_agent.id: o for o in observations}
    proposals = {i.actor_id: i.model_copy(deep=True) for i in intents}
    movers = sorted(aid for aid, i in proposals.items() if i.action == Action.MOVE)
    if not movers:
        return intents
    # Rotate first choice each tick; resolution order itself remains stable by actor ID.
    offset = tick % len(movers)
    order = movers[offset:] + movers[:offset]
    reserved = set()
    for aid in order:
        intent = proposals[aid]
        o = by_actor.get(aid)
        if o is None or intent.target is None:
            continue
        target = (intent.target.x, intent.target.y)
        if target not in reserved:
            reserved.add(target)
            continue
        occupied = {(p.x, p.y) for p in o.occupied}
        walkable = {(t.position.x, t.position.y) for t in o.tiles if t.walkable}
        walkable -= occupied | reserved
        start = o.self_agent.position
        walkable.add((start.x, start.y))
        path = None
        if intent.destination:
            d = intent.destination
            # Interactions can happen on or next to the resource/building.
            goals = {(d.x, d.y), (d.x + 1, d.y), (d.x - 1, d.y), (d.x, d.y + 1), (d.x, d.y - 1)}
            path = astar(start, goals & walkable, walkable, o.path_budget)
            if path is None:
                path = local_waypoint(start, d, walkable, o.path_budget)
        if path and (path[0].x, path[0].y) not in reserved:
            intent.target = path[0]
            intent.navigation_note = "Replanned around another agent's reserved next tile"
            reserved.add((path[0].x, path[0].y))
        else:
            intent.action = Action.IDLE
            intent.target = None
            intent.navigation_note = "Yielded this tick because the next tile was reserved"
            # Speech belongs only to a successfully validated social interaction.
            intent.utterance = None
    return [proposals[i.actor_id] for i in intents]
