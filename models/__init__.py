from .stream_in import StreamIn
from .stream_out import StreamOut
from .valve import Valve
from .vessel import Vessel
from .check_valve import CheckValve
from .mixer import Mixer
from .divider import Divider
from .compressor import Compressor
from .analog_source import AnalogSource
from .analog_sink import AnalogSink

BLOCK_REGISTRY = {
    cls.block_type: cls
    for cls in (
        StreamIn,
        StreamOut,
        Valve,
        Vessel,
        CheckValve,
        Mixer,
        Divider,
        Compressor,
        AnalogSource,
        AnalogSink,
    )
}


def create_block(block_type: str, name: str = None):
    if block_type not in BLOCK_REGISTRY:
        raise KeyError(f"Unknown block type '{block_type}'")
    return BLOCK_REGISTRY[block_type](name=name)


__all__ = [
    "BLOCK_REGISTRY",
    "create_block",
    "StreamIn",
    "StreamOut",
    "Valve",
    "Vessel",
    "CheckValve",
    "Mixer",
    "Divider",
    "Compressor",
    "AnalogSource",
    "AnalogSink",
]
