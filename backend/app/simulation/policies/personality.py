from app.simulation.chunks.generator import sample
from app.simulation.models.domain import Personality


def personality_for(seed: int, index: int) -> Personality:
    return Personality(
        **{
            name: round(0.08 + 0.84 * sample(seed, index, 0, f"trait:{name}"), 4)
            for name in Personality.model_fields
        }
    )
