"""Keep practical carrying room for meals and communal food production."""

from app.simulation.models.domain import Inventory


def carrying_room(inventory: Inventory, item: str, *, communal: bool = False) -> int:
    free = inventory.capacity - inventory.total
    if communal:
        reserve = max(0, min(12, inventory.capacity // 4) - inventory.food - inventory.water)
        return max(0, free - (reserve if item not in ("food", "water") else 0))
    reserve = max(0, min(3, inventory.capacity // 4) - inventory.food)
    return max(0, free - (reserve if item != "food" else 0))
