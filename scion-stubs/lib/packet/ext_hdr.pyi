from lib.packet.packet_base import Serializable
from typing import Optional


class ExtensionHeader(Serializable):
    NAME = "ExtensionHeader"
    LINE_LEN = 8  # Length of extension must be multiplication of LINE_LEN.
    MIN_LEN = LINE_LEN
    EXT_CLASS = None  # type: Optional[int] # Class of extension (hop-by-hop or end-to-end).
    EXT_TYPE = None  # type: Optional[int] # Type of extension.
    EXT_TYPE_STR = None  #type: None # Name of extension.
    SUBHDR_LEN = 3
    MIN_PAYLOAD_LEN = MIN_LEN - SUBHDR_LEN


class HopByHopExtension(ExtensionHeader):
    pass