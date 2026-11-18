from .eos import EquationOfState, IdealGas, PengRobinson, SoaveRedlichKwong, R
from .lee_kesler import LeeKesler
from .gerg2008 import GERG2008
from .flash import FlashResult, flash_isothermal, flash_eos, psat, rachford_rice

EOS_REGISTRY = {
    cls.name: cls
    for cls in (IdealGas, PengRobinson, SoaveRedlichKwong, LeeKesler, GERG2008)
}

EOS_NAMES = list(EOS_REGISTRY.keys())


def get_eos(name="Ideal Gas") -> EquationOfState:
    if name not in EOS_REGISTRY:
        raise KeyError(f"Unknown EOS '{name}'. Available: {EOS_NAMES}")
    return EOS_REGISTRY[name]()


__all__ = [
    "EquationOfState",
    "IdealGas",
    "PengRobinson",
    "SoaveRedlichKwong",
    "R",
    "EOS_REGISTRY",
    "EOS_NAMES",
    "get_eos",
    "FlashResult",
    "flash_isothermal",
    "flash_eos",
    "psat",
    "rachford_rice",
]
