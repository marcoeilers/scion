import lib.packet.scion_addr

from typing import List
from py2viper_contracts.contracts import *

class PathSegment:
    def short_desc(self) -> str: ...

    def iter_asms(self, start: int=0) -> List[ASMarking]:
        Requires(Acc(self.State(), 1/100))
        Ensures(Acc(self.State(), 1/100))
        Ensures(Acc(list_pred(Result())))
        ...

    def get_n_peer_links(self) -> int:  ...

    def get_n_hops(self) -> int: ...

    def get_timestamp(self) -> int: ...

    @Predicate
    def State(self) -> bool:
        return True


class PCBMarking:
    def __init__(self) -> None:
        self.p = PPCBMarking()

    def inIA(self) -> 'lib.packet.scion_addr.ISD_AS': ...

    def outIA(self) -> 'lib.packet.scion_addr.ISD_AS': ...

    @Predicate
    def State(self) -> bool:
        return True

class PPCBMarking:
    """
    struct PCBMarking {
    inIA @0 :UInt32;  # Ingress (incl peer) ISD-AS
    inIF @1 :UInt64; # Interface ID on far end of ingress link
    inMTU @2 :UInt16;  # Ingress Link MTU
    outIA @3 :UInt32;  # Downstream ISD-AS
    outIF @4 :UInt64; # Interface ID on far end of egress link
    hof @5 :Data;
    }
    """
    def __init__(self) -> None:
        self.inIA = 0
        self.inIF = 0
        self.inMTU = 0
        self.outIA = 0
        self.outIF = 0

    @Predicate
    def State(self) -> bool:
        return True

class ASMarking:
    def isd_as(self) -> 'lib.packet.scion_addr.ISD_AS': ...
    def iter_pcbms(self, start: int=0) -> List[PCBMarking]:  ...

    @Predicate
    def State(self) -> bool:
        return True