"""Voluntary cooperation from local public needs and observed neighbours."""

from app.simulation.actions.provisions import carrying_room
from app.simulation.engineering.housing import HOUSING, tested
from app.simulation.models.domain import Action, Inventory, Position, ShelterDesign
from app.simulation.policies.projects import propose_project
from app.simulation.settlements.effects import building_usable


def community_goals(o, add, approach):
    a, s = o.self_agent, o.settlement
    safe_to_help = a.hunger < 55 and a.energy >= 20
    peers = [p for p in o.peers if p.get("need") in ("food", "care")]
    if peers and a.inventory.food >= 2 and safe_to_help:
        peer = min(
            peers,
            key=lambda p: (
                p["need"] != "care",
                a.position.distance(Position.model_validate(p["position"])),
                p["id"],
            ),
        )
        approach(
            "help_neighbor",
            Position.model_validate(peer["position"]),
            {
                "visible_need": 0.55 if peer["need"] == "food" else 0.7,
                "cooperation": a.personality.cooperation * 0.2,
                "relationship": a.relationships.get(peer["id"], 0.5) * 0.12,
            },
            Action.GIVE,
            adjacent=True,
            peer_id=peer["id"],
            item="food",
            amount=1,
        )
    else:
        add("help_neighbor", {}, rejection="No visible unmet need or no safe meal surplus")
    board = (s or {}).get("community") or {}
    active = next((p for p in board.get("projects", []) if p["status"] == "active"), None)
    if s and not active and safe_to_help:
        proposal = propose_project(o)
        if proposal:
            kind, target, _ = proposal
            from app.simulation.engineering.housing import best_design, construction_cost

            cost = construction_cost(kind, best_design(a))
            ready = all(getattr(a.inventory, k) + s["storage"][k] >= n for k, n in cost.items())
            if ready:
                add("organize_project", {}, rejection="Materials ready; start the work directly")
            elif kind not in HOUSING or best_design(a):
                approach(
                    "organize_project",
                    Position.model_validate(s["center"]),
                    {
                        "shared_need": 0.62,
                        "cooperation": a.personality.cooperation * 0.14,
                        "ambition": a.personality.ambition * 0.1,
                    },
                    Action.PROPOSE_PROJECT,
                    adjacent=True,
                    target=target,
                    building_kind=kind,
                )
            else:
                add("organize_project", {}, rejection="Learn a shelter design first")
        else:
            add("organize_project", {}, rejection="No locally observed construction need")
    else:
        add("organize_project", {}, rejection="Public project active or personal recovery needed")
    repairs = [
        b
        for b in o.buildings
        if building_usable(b)
        and b["durability"] < 75
        and (
            b["kind"] not in HOUSING
            or not b.get("design")
            or tested(a, ShelterDesign.model_validate(b["design"]))
        )
    ]
    if repairs and safe_to_help and (a.inventory.wood or (s and s["storage"]["wood"])):
        b = min(repairs, key=lambda b: (b["durability"], b["id"]))
        approach(
            "maintain_community",
            Position.model_validate(b["position"]),
            {
                "shared_need": 0.52,
                "damage": (100 - b["durability"]) / 180,
                "cooperation": a.personality.cooperation * 0.15,
            },
            Action.REPAIR,
            adjacent=True,
            building_id=b["id"],
        )
    else:
        add("maintain_community", {}, rejection="No repairable observed damage or wood unavailable")
    # A food supplier gathers for the public cache, rather than endlessly filling private bags.
    if s and s["food_reserves"] < 6 and safe_to_help:
        cache = Position.model_validate(s["center"])
        if (
            a.inventory.food > 1
            and carrying_room(Inventory.model_validate(s["storage"]), "food", communal=True) > 0
        ):
            approach(
                "feed_community",
                cache,
                {"shared_need": 0.42, "cooperation": a.personality.cooperation * 0.18},
                Action.STORE,
                adjacent=True,
                item="food",
                amount=1,
            )
        elif a.inventory.food < 3:
            food = [
                r
                for r in o.resources
                if r.kind == "food" and r.quantity > 0 and carrying_room(a.inventory, "food") > 0
            ]
            if food:
                r = min(food, key=lambda r: (a.position.distance(r.position), r.id))
                approach(
                    "feed_community",
                    r.position,
                    {
                        "shared_need": 0.34,
                        "cooperation": a.personality.cooperation * 0.16,
                        "travel_cost": -min(0.25, a.position.distance(r.position) * 0.015),
                    },
                    Action.GATHER,
                    adjacent=True,
                    resource_id=r.id,
                )
            else:
                add("feed_community", {}, rejection="No visible reachable surplus food")
    else:
        add("feed_community", {}, rejection="Public food reserve adequate or recovery needed")
