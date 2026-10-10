from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ProfileParams(BaseModel):
    """Tunables for learning and for how the router reads learned scores."""

    model_config = ConfigDict(frozen=True)

    # alpha = max(min_alpha, 1 / (n + 1)): a running mean at first, then a fixed-rate average
    # that keeps adapting (and so forgets old behaviour) once n is large.
    min_alpha: float = Field(default=0.1, gt=0.0, le=1.0)
    # Interactions needed before a score may influence routing (one event is not a pattern).
    min_evidence: int = Field(default=2, ge=1)
    downgrade_below: float = -0.4  # notify -> digest
    mute_below: float = -0.7  # digest -> mute
    upgrade_above: float = 0.6  # digest -> notify
