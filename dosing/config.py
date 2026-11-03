"""Config flags, read from the environment at call time (so tests can monkeypatch)."""
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# verbatim copy of Final_Drugs_data/dosesafe_formulary_v2.json, kept inside the repo so a fresh clone works; override with DOSING_FORMULARY_PATH
DEFAULT_FORMULARY = ROOT / "data" / "dosesafe_formulary_v2.json"
BANNER = "Prototype data, not clinically verified"
DEMO_BANNER = "DEMO - UNVERIFIED DATA"
OVERRIDE_CATEGORIES = {"benefit_outweighs_risk": "Benefit outweighs risk", "patient_tolerates": "Patient already tolerates it",
                       "no_alternative": "No alternative available", "other": "Other"}


def _flag(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Config:
    allow_unverified: bool = False        # DOSING_ALLOW_UNVERIFIED: compute UNVERIFIED rules (marked) instead of refusing
    ml_step: float = 0.5                  # DOSING_ML_STEP: liquid volume rounding step
    abw_factor: float | None = None       # DOSING_ABW_FACTOR: None = formulary formulas.adjusted_body_weight.factor_default
    override_min_chars: int = 10          # a written override reason shorter than this is rejected
    adult_min_age_years: int = 18         # convention: rules written for adults carry min_age_years 18
    formulary_path: Path = DEFAULT_FORMULARY
    demo_mode: bool = False               # DOSING_DEMO_MODE or DEMO_MODE: forces allow_unverified and shows a red DEMO banner on every result

    def __post_init__(self):
        if self.demo_mode and not self.allow_unverified:
            object.__setattr__(self, "allow_unverified", True)

    @staticmethod
    def from_env() -> "Config":
        f = os.environ.get("DOSING_ABW_FACTOR")
        return Config(
            allow_unverified=_flag("DOSING_ALLOW_UNVERIFIED", False),
            demo_mode=_flag("DOSING_DEMO_MODE", False) or _flag("DEMO_MODE", False),   # DEMO_MODE also shows "Load demo patient"
            ml_step=float(os.environ.get("DOSING_ML_STEP", "0.5")),
            abw_factor=float(f) if f else None,
            formulary_path=Path(os.environ.get("DOSING_FORMULARY_PATH", DEFAULT_FORMULARY)))
