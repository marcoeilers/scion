from lib.packet.packet_base import Serializable
from lib.packet.opaque_field import OpaqueField, InfoOpaqueField, HopOpaqueField, OpaqueFieldList
from lib.packet.pcb import ASMarking
from lib.util import Raw
from typing import cast, Optional, Sized, List, Tuple

class SCIONPath(Serializable):
    NAME = "SCIONPath"
    A_IOF = "A_segment_iof"
    A_HOFS = "A_segment_hofs"
    B_IOF = "B_segment_iof"
    B_HOFS = "B_segment_hofs"
    C_IOF = "C_segment_iof"
    C_HOFS = "C_segment_hofs"
    OF_ORDER = A_IOF, A_HOFS, B_IOF, B_HOFS, C_IOF, C_HOFS
    IOF_LABELS = A_IOF, B_IOF, C_IOF
    HOF_LABELS = A_HOFS, B_HOFS, C_HOFS

    def __init__(self, raw:Raw=None) -> None:  # pragma: no cover
        self._ofs = OpaqueFieldList(SCIONPath.OF_ORDER)
        self._iof_idx = None  # type: Optional[int]
        self._hof_idx = None  # type: Optional[int]
        self.interfaces = []  # type: List[Tuple[ASMarking, int]]
        self.mtu = None  # type: Optional[int]



    def matches(self, raw: bytes, offset: int) -> bool:
        return True

    def get_iof(self) -> Optional[InfoOpaqueField]:  # pragma: no cover
        idx = self._iof_idx
        if not isinstance(idx, int):
            return None
        return cast(InfoOpaqueField, self._ofs.get_by_idx(idx))

    def get_hof(self) -> Optional[HopOpaqueField]:  # pragma: no cover
        idx = self._hof_idx
        if not isinstance(idx, int):
            return None
        return cast(HopOpaqueField, self._ofs.get_by_idx(idx))

    def get_hof_ver(self, ingress: bool =True) -> Optional[HopOpaqueField]:
        """Return the :any:`HopOpaqueField` needed to verify the current HOF."""
        iof = self.get_iof()
        hof = self.get_hof()
        if not hof.xover or (iof.shortcut and not iof.peer):
            # For normal hops on any type of segment, or cross-over hops on
            # non-peer shortcut hops, just use next/prev HOF.
            return self._get_hof_ver_normal(iof)
        iof_peer = iof.peer
        iof_up_flag = iof.up_flag
        if iof_peer:
            # Peer shortcut paths have two extra HOFs; 1 for the peering
            # interface, and another from the upstream interface, used for
            # verification only.
            if ingress:
                if iof_up_flag:
                    offset = 2  # type: Optional[int]
                else:
                    offset = 1
            else:
                if iof_up_flag:
                    offset = -1
                else:
                    offset = -2
        else:
            # Non-peer shortcut paths have an extra HOF above the last hop, used
            # for verification of the last hop in that segment.
            if ingress:
                if iof_up_flag:
                    offset = None
                else:
                    offset = -1
            else:
                if iof_up_flag:
                    offset = 1
                else:
                    offset = None
        # Map the local direction of travel and the IOF up flag to the required
        # offset of the verification HOF (or None, if there's no relevant HOF).
        if not isinstance(offset, int):
            return None
        return cast(HopOpaqueField, self._ofs.get_by_idx(self._hof_idx + offset))


    def _get_hof_ver_normal(self, iof: InfoOpaqueField) -> Optional[HopOpaqueField]:
        ...
        # # Requires iof in bla
        # # If this is the last hop of an Up path, or the first hop of a Down
        # # path, there's no previous HOF to verify against.
        # if (iof.up_flag and self._hof_idx == self._iof_idx + iof.hops) or (
        #         not iof.up_flag and self._hof_idx == self._iof_idx + 1):
        #     return None
        # # Otherwise use the next/prev HOF based on the up flag.
        # offset = 1 if iof.up_flag else -1
        # return self._ofs.get_by_idx(self._hof_idx + offset)

    def is_on_last_segment(self) -> bool:
        ...

    def get_fwd_if(self) -> int:
        ...

    def inc_hof_idx(self) -> bool:
        ...

    def get_of_idxs(self) -> Tuple[int, int]:
        ...

    def __len__(self) -> int:
        return len(self._ofs) * OpaqueField.LEN

    def get_curr_if(self, ingress: bool=True) -> int:
        ...

    @staticmethod
    def from_values(a_iof: InfoOpaqueField=None, a_hofs: List[HopOpaqueField]=None,
                    b_iof: InfoOpaqueField=None, b_hofs: List[HopOpaqueField]=None,
                    c_iof: InfoOpaqueField=None, c_hofs: List[HopOpaqueField]=None) -> 'SCIONPath':
        ...


def valid_hof(path: SCIONPath) -> bool:
    return True