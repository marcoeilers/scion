# Copyright 2014 ETH Zurich
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
:mod:`path_store` --- Path record storage and selection for path servers
========================================================================
"""
# Stdlib
import copy
import heapq
import logging
import math
###from collections import defaultdict, deque

# External
import yaml

# SCION
from lib.packet.pcb import PathSegment
from lib.packet.scion_addr import ISD_AS
from lib.util import SCIONTime, load_yaml_file
from typing import cast, Dict, List, Optional, Tuple
from nagini_contracts.contracts import *


class PathPolicy(object):
    """Stores a path policy."""
    def __init__(self) -> None:  # pragma: no cover
        Ensures(self.State())
        self.best_set_size = 5
        self.candidates_set_size = 20
        self.history_limit = 0
        self.update_after_number = 0
        self.update_after_time = 0
        self.unwanted_ases = []  # type: List[ISD_AS]
        self.property_ranges = {}  # type: Dict[str, Tuple[int, int]]
        self.property_weights = {}  # type: Dict[str, int]
        Fold(self.State())

    @Predicate
    def State(self) -> bool:
        return (Acc(self.best_set_size) and
                Acc(self.candidates_set_size) and
                Acc(self.history_limit) and
                Acc(self.update_after_number) and
                Acc(self.update_after_time) and
                Acc(self.unwanted_ases) and Acc(list_pred(self.unwanted_ases)) and
                Acc(self.property_ranges) and Acc(dict_pred(self.property_ranges)) and
                Acc(self.property_weights)) and Acc(dict_pred(self.property_weights))

    def get_path_policy_dict(self) -> Dict[str, object]:  # pragma: no cover
        Requires(Acc(self.State(), 1/100))
        Ensures(Acc(self.State(), 1/100))
        Ensures(Acc(dict_pred(Result())))
        Ensures('best_set_size' in Result())
        """Return path policy info in a dictionary."""
        Unfold(Acc(self.State(), 1/100))
        result = {
            'best_set_size': self.best_set_size,
            'candidates_set_size': self.candidates_set_size,
            'history_limit': self.history_limit,
            'update_after_number': self.update_after_number,
            'update_after_time': self.update_after_time,
            'unwanted_ases': self.unwanted_ases,
            'property_ranges': self.property_ranges,
            'property_weights': self.property_weights
        }
        Fold(Acc(self.State(), 1/100))
        return result

    def check_filters(self, pcb: PathSegment) -> bool:
        Requires(Acc(pcb.State(), 1/10))
        Requires(Acc(self.State(), 1 / 7))
        Requires(self.valid_ranges())
        Ensures(Acc(pcb.State(), 1 / 10))
        Ensures(Acc(self.State(), 1 / 7))
        """
        Runs some checks, including: unwanted ASes and min/max property values.

        :param pcb: beacon to analyze.
        :type pcb: :class:`PathSegment`
        :returns:
            True if any unwanted AS is present or a range is not respected.
        :rtype: bool
        """
        assert isinstance(pcb, PathSegment)
        isd_as = self._check_unwanted_ases(pcb)
        if isd_as:
            logging.warning("PathStore: pcb discarded, unwanted AS(%s): %s",
                            isd_as, pcb.short_desc())
            return False
        reasons = self._check_property_ranges(pcb)
        if reasons:
            logging.info("PathStore: pcb discarded(%s): %s",
                         ", ".join(reasons), pcb.short_desc())
            return False
        ia = self._check_remote_ifid(pcb)
        if ia:
            logging.error("PathStore: pcb discarded, remote IFID of %s unknown",

                          )
            return False
        return True

    def _check_unwanted_ases(self, pcb: PathSegment) -> Optional[ISD_AS]:  # pragma: no cover
        Requires(Acc(pcb.State(), 1/20))
        Requires(Acc(self.State(), 1/8))
        Ensures(Acc(pcb.State(), 1 / 20))
        Ensures(Acc(self.State(), 1 / 8))
        """
        Checks whether any of the ASes in the path belong to the black list.

        :param pcb: beacon to analyze.
        :type pcb: :class:`PathSegment`
        """
        asms = pcb.iter_asms()
        for asm in asms:
            Invariant(Forall(asms, lambda a: (Acc(a.State(), 1 / 4), [])))
            Invariant(Acc(self.State(), 1/9))
            Invariant(Acc(pcb.State(), 1 / 20))
            isd_as = asm.isd_as()
            Unfold(Acc(self.State(), 1/10))
            if isd_as in self.unwanted_ases:
                Fold(Acc(self.State(), 1 / 10))
                return isd_as
            Fold(Acc(self.State(), 1 / 10))

    def _check_range(self, reasons: List[str], name: str, actual: int) -> None:
        Requires(Acc(list_pred(reasons)))
        Requires(Acc(self.State(), 1/200))
        Requires(Unfolding(Acc(self.State(), 1/400), name in self.property_ranges))
        Ensures(Acc(list_pred(reasons)))
        Ensures(Acc(self.State(), 1 / 200))

        range_ = Unfolding(Acc(self.State(), 1/300), self.property_ranges[name])
        if not range_:
            return
        if (actual < range_[0] or actual > range_[1]):
            reasons.append("%s: %d <= %d <= %d" % (
                name, range_[0], actual, range_[1]))

    def _check_property_ranges(self, pcb: PathSegment) -> List[str]:
        Requires(Acc(self.State(), 1 / 100))
        Requires(self.valid_ranges())
        Ensures(Acc(self.State(), 1 / 100))
        Ensures(Acc(list_pred(Result())))
        """
        Checks whether any of the path properties has a value outside the
        predefined min-max range.

        :param pcb: beacon to analyze.
        :type pcb: :class:`PathSegment`
        """

        reasons = []  # type: List[str]
        self._check_range(reasons, "PeerLinks", pcb.get_n_peer_links())
        self._check_range(reasons, "HopsLength", pcb.get_n_hops())
        self._check_range(reasons, "DelayTime",
                          int(SCIONTime.get_time()) - pcb.get_timestamp())
        self._check_range(reasons, "GuaranteedBandwidth", 10)
        self._check_range(reasons, "AvailableBandwidth", 10)
        self._check_range(reasons, "TotalBandwidth", 10)
        return reasons

    def _check_remote_ifid(self, pcb: PathSegment) -> Optional[ISD_AS]:
        Requires(Acc(pcb.State(), 1 / 20))
        Ensures(Acc(pcb.State(), 1 / 20))
        """
        Checkes whether any PCB markings have unset remote IFID values for
        up/downstream ASes. This can happen during normal startup depending
        on the timing of PCB propagation vs IFID keep-alives, but should
        not happen once the infrastructure is settled.
        Remote IFID is only allowed to be 0 if the corresponding ISD-AS is
        0-0.
        """
        asms = pcb.iter_asms()
        for asm in asms:
            Invariant(Forall(asms, lambda a: (Acc(a.State(), 1 / 4), [])))
            pcbms = asm.iter_pcbms()
            for pcbm in pcbms:
                Invariant(Forall(pcbms, lambda p: (Acc(p.State(), 1 / 4), [])))
                if (pcbm.inIA().to_int() and
                        not Unfolding(Acc(pcbm.State(), 1/8),
                                      Unfolding(Acc(pcbm.p.State(), 1/16), pcbm.p.inIF))):
                    return pcbm.inIA()
                if (pcbm.outIA().to_int() and
                        not Unfolding(Acc(pcbm.State(), 1/8),
                                      Unfolding(Acc(pcbm.p.State(), 1/16), pcbm.p.outIF))):
                    return pcbm.outIA()
        return None

    @classmethod
    def from_file(cls, policy_file: str) -> 'PathPolicy':  # pragma: no cover
        """
        Create a PathPolicy instance from the file.

        :param str policy_file: path to the path policy file
        """
        return cls.from_dict(load_yaml_file(policy_file))

    @classmethod
    def from_dict(cls, policy_dict: Dict[str, object]) -> 'PathPolicy':  # pragma: no cover
        Requires(Acc(dict_pred(policy_dict), 1/10))
        Requires(valid_policy(policy_dict))
        Requires(Acc(dict_pred(policy_dict['PropertyRanges'])))
        Requires(Acc(dict_pred(policy_dict['PropertyWeights'])))
        Ensures(Acc(dict_pred(policy_dict), 1 / 10))
        """
        Create a PathPolicy instance from the dictionary.

        :param dict policy_dict: dictionary representation of path policy
        """
        path_policy = cls()
        path_policy.parse_dict(policy_dict)
        return path_policy

    def parse_dict(self, path_policy: Dict[str, object]) -> None:
        Requires(self.State())
        Requires(Acc(dict_pred(path_policy), 1/20))
        Requires(valid_policy(path_policy))
        Requires(Acc(dict_pred(path_policy['PropertyRanges'])))
        Requires(Acc(dict_pred(path_policy['PropertyWeights'])))
        Ensures(self.State())
        Ensures(Acc(dict_pred(path_policy), 1 / 20))
        """
        Parses the policies from the dictionary.

        :param dict path_policy: path policy.
        """
        Unfold(self.State())
        self.best_set_size = cast(int, path_policy['BestSetSize'])
        self.candidates_set_size = cast(int, path_policy['CandidatesSetSize'])
        self.history_limit = cast(int, path_policy['HistoryLimit'])
        self.update_after_number = cast(int, path_policy['UpdateAfterNumber'])
        self.update_after_time = cast(int, path_policy['UpdateAfterTime'])
        unwanted_ases = cast(str, path_policy['UnwantedASes']).split(',')
        for unwanted in unwanted_ases:
            Invariant(Acc(self.unwanted_ases, 1/2) and Acc(list_pred(self.unwanted_ases)))
            self.unwanted_ases.append(ISD_AS(unwanted))
        property_ranges = cast(Dict[str, str], path_policy['PropertyRanges'])
        for key in property_ranges:
            Invariant(Acc(self.property_ranges, 1/2) and Acc(dict_pred(self.property_ranges)))
            property_range = property_ranges[key].split('-')
            property_range_temp = int(property_range[0]), int(property_range[1])
            self.property_ranges[key] = property_range_temp
        self.property_weights = cast(Dict[str, int], path_policy['PropertyWeights'])
        Fold(self.State())

    @Pure
    def valid_ranges(self) -> bool:
        Requires(Acc(self.State(), 1/200))
        return Unfolding(Acc(self.State(), 1/200),
                         'PeerLinks' in self.property_ranges and
                         'HopsLength' in self.property_ranges and
                         'DelayTime' in self.property_ranges and
                         'GuaranteedBandwidth' in self.property_ranges and
                         'AvailableBandwidth' in self.property_ranges and
                         'TotalBandwidth' in self.property_ranges
                         )

    def __str__(self) -> str:
        Requires(Acc(self.State(), 1/10))
        Ensures(Acc(self.State(), 1 / 10))
        path_policy_dict = self.get_path_policy_dict()
        path_policy_str = yaml.dump(path_policy_dict)
        return path_policy_str

DICT_STR_STR = Dict[str, str]
DICT_STR_INT = Dict[str, int]


@Pure
def valid_policy(path_policy: Dict[str, object]) -> bool:
    Requires(Acc(dict_pred(path_policy), 1 / 1000))
    return ('BestSetSize' in path_policy and
            'CandidatesSetSize' in path_policy and
            'HistoryLimit' in path_policy and
            'UpdateAfterNumber' in path_policy and
            'UpdateAfterTime' in path_policy and
            'UnwantedASes' in path_policy and
            'PropertyRanges' in path_policy and
            'PropertyWeights' in path_policy and
            isinstance(path_policy['BestSetSize'], int) and
            isinstance(path_policy['CandidatesSetSize'], int) and
            isinstance(path_policy['HistoryLimit'], int) and
            isinstance(path_policy['UpdateAfterNumber'], int) and
            isinstance(path_policy['UpdateAfterTime'], int) and
            isinstance(path_policy['UnwantedASes'], str) and
            isinstance(path_policy['PropertyRanges'], DICT_STR_STR) and
            isinstance(path_policy['PropertyWeights'], DICT_STR_INT))


# class PathStoreRecord(object):
#     """
#     Path record that gets stored in the the PathStore.
#
#     :cvar int DEFAULT_OFFSET:
#         the amount of time subtracted from the current time when the path's
#         initial last sent time is set.
#     :ivar pcb: the PCB representing the record.
#     :vartype pcb: :class:`lib.packet.pcb.PathSegment`
#     :ivar bytes id: the path segment identifier stored in the record's PCB.
#     :ivar float fidelity: the fidelity of the path record.
#     :ivar float peer_links:
#         the normalized number of peer links in the path segment.
#     :ivar float hops_length: the normalized length of the path segment.
#     :ivar float disjointness:
#         the normalized disjointness of the path segment compared to the other
#         paths in the PathStore.
#     :ivar int last_sent_time:
#         the Unix time at which the path segment was last sent.
#     :ivar int last_seen_time:
#         the Unix time at which the path segment was last seen.
#     :ivar float delay_time:
#         the normalized time in seconds between the PCB's creation and the time
#         it was last seen by the path server.
#     :ivar int expiration_time: the Unix time at which the path segment expires.
#     :ivar int guaranteed_bandwidth: the path segment's guaranteed bandwidth.
#     :ivar int available_bandwidth: the path segment's available bandwidth.
#     :ivar int total_bandwidth: the path segment's total bandwidth.
#     """
#     DEFAULT_OFFSET = 3600 * 24 * 7  # 1 week
#
#     def __init__(self, pcb: PathSegment) -> None:
#         """
#         :param pcb: beacon to analyze.
#         :type pcb: :class:`PathSegment`
#         """
#         assert isinstance(pcb, PathSegment)
#         self.id = pcb.get_hops_hash(hex=True)
#         self.peer_links = pcb.get_n_peer_links()
#         self.hops_length = pcb.get_n_hops()
#         self.fidelity = 0
#         self.disjointness = 0
#         self.last_sent_time = int(SCIONTime.get_time()) - self.DEFAULT_OFFSET
#         self.guaranteed_bandwidth = 0
#         self.available_bandwidth = 0
#         self.total_bandwidth = 0
#         self.last_seen_time = -1
#         self.update(pcb)
#
#     @Predicate
#     def State(self) -> bool:
#         return (Acc(self.id) and
#                 Acc(self.peer_links) and
#                 Acc(self.hops_length) and
#                 Acc(self.fidelity) and
#                 Acc(self.disjointness) and
#                 Acc(self.last_sent_time) and
#                 Acc(self.guaranteed_bandwidth) and
#                 Acc(self.available_bandwidth) and
#                 Acc(self.total_bandwidth) and
#                 Acc(self.last_seen_time))
#
#     def update(self, pcb: PathSegment) -> None:
#         """
#         Update a candidate entry from a recent PCB.
#         """
#         assert self.id == pcb.get_hops_hash(hex=True)
#         now = int(SCIONTime.get_time())
#         self.pcb = copy.deepcopy(pcb)
#         self.delay_time = now - pcb.get_timestamp()
#         self.last_seen_time = now
#         self.expiration_time = pcb.get_expiration_time()
#
#     def sending(self) -> None:  # pragma: no cover
#         """
#         Update last_sent_time to now.
#         """
#         self.last_sent_time = int(SCIONTime.get_time())
#
#     def update_fidelity(self, path_policy: PathPolicy) -> None:
#         Requires(Acc(path_policy.State(), 1/100))
#         Requires(path_policy.valid_ranges())
#         """
#         Computes a path fidelity based on all path properties and considering
#         the corresponding weights, which are stored in the path policy.
#
#         :param dict path_policy: path policy.
#         """
#         self.fidelity = 0
#         now = SCIONTime.get_time()
#         self.fidelity += (path_policy.property_weights['PeerLinks'] *
#                           self.peer_links)
#         self.fidelity += (path_policy.property_weights['HopsLength'] //
#                           self.hops_length)
#         self.fidelity += (path_policy.property_weights['Disjointness'] *
#                           self.disjointness)
#         if now != 0:
#             self.fidelity += (path_policy.property_weights['LastSentTime'] *
#                               (now - self.last_sent_time) // now)
#             self.fidelity += (path_policy.property_weights['LastSeenTime'] *
#                               self.last_seen_time // now)
#         self.fidelity += (path_policy.property_weights['DelayTime'] //
#                           self.delay_time)
#         self.fidelity += (path_policy.property_weights['ExpirationTime'] *
#                           (self.expiration_time - now) // self.expiration_time)
#         self.fidelity += (path_policy.property_weights['GuaranteedBandwidth'] *
#                           self.guaranteed_bandwidth)
#         self.fidelity += (path_policy.property_weights['AvailableBandwidth'] *
#                           self.available_bandwidth)
#         self.fidelity += (path_policy.property_weights['TotalBandwidth'] *
#                           self.total_bandwidth)

    # def __eq__(self, other):  # pragma: no cover
    #     if type(other) is not type(self):
    #         return False
    #     return self.id == other.id
    #
    # def __str__(self):
    #     return "PathStoreRecord: ID: %s Fidelity: %s" % (
    #         self.id, self.fidelity)
#
#
# class PathStore(object):
#     """Path Store class."""
#     def __init__(self, path_policy):  # pragma: no cover
#         """
#         :param dict path_policy: path policy.
#         """
#         self.path_policy = path_policy
#         self.candidates = []
#         self.best_paths_history = deque(maxlen=self.path_policy.history_limit)
#         self.disjointness = defaultdict(float)
#         self.last_dj_update = 0
#
#     def add_segment(self, pcb):
#         """
#         Possibly add a new path to the candidates list.
#
#         Attempt to add a path (which is an instance of PathSegment) to the set
#         of candidate paths. If successfully added, the candidate path is stored
#         in the PathStore as a PathStoreRecord.
#
#         Before adding the path, the candidate PathSegment is first checked
#         against the PathStore's filter criteria, listed in PathPolicy.  If the
#         path's properties do not meet the filter criteria, the path is not
#         added and the set of candidate paths remains unchanged.
#
#         If the path passes the filter checks but is already in the candidate
#         set (as determined by its identifier), then the path is not added to
#         the candidate set. Instead, the delay and arrival times are updated in
#         the existing record.
#
#         If the path passes the filter checks and is not already in the
#         candidate set, it is added to the list of candidate paths.  If upon
#         adding the path, the candidate path set is too large (i.e., larger than
#         candidates_set_size), the lowest-fidelity path is removed.
#
#         :param pcb: The PCB representing the potential path.
#         :type pcb: PathSegment
#         """
#         assert isinstance(pcb, PathSegment)
#         pcb_hash = pcb.get_hops_hash(hex=True)
#         if not self.path_policy.check_filters(pcb):
#             return
#         for candidate in self.candidates:
#             if candidate.id == pcb_hash:
#                 candidate.update(pcb)
#                 return
#         record = PathStoreRecord(pcb)
#         self.candidates.append(record)
#         self._trim_candidates()
#
#     def _trim_candidates(self):
#         """
#         Trims the set of candidate set if necessary.
#         """
#         if len(self.candidates) > self.path_policy.candidates_set_size:
#             self._remove_expired_segments()
#         if len(self.candidates) > self.path_policy.candidates_set_size:
#             self._update_all_fidelity()
#             self.candidates = sorted(self.candidates, key=lambda x: x.fidelity,
#                                      reverse=True)[:-1]
#
#     def _update_disjointness_db(self):
#         """
#         Update the disjointness database.
#
#         Based on the current time, update the disjointness database keeping
#         track of each path, AS, and interface previously sent.
#         """
#         now = SCIONTime.get_time()
#         for k, v in self.disjointness.items():
#             self.disjointness[k] = v * math.exp(self.last_dj_update - now)
#         self.last_dj_update = now
#
#     def _update_all_disjointness(self):
#         """
#         Update the disjointness of all path candidates.
#
#         The disjointness of a candidate path is measured with respect to
#         previously sent paths and is calculated as follows:
#
#         Each time a path is sent, its ASes and AS-interface pairs are added to
#         the (data structure). The exact path itself is also added to a list of
#         previously sent paths.
#
#         The disjointness is then calculated as the inverse of the sum of the
#         following: the entire path, each AS on the path, and each AS-interface
#         pair on the path.
#
#         The disjointness is normalized by the highest-scoring path's
#         disjointness.
#         """
#         self._update_disjointness_db()
#         max_disjointness = 0.0
#         for candidate in self.candidates:
#             path_disjointness = self.disjointness[candidate.id]
#             as_disjointness = 0.0
#             if_disjointness = 0.0
#             for asm in candidate.pcb.iter_asms():
#                 as_disjointness += self.disjointness[asm.isd_as()[1]]
#                 if_disjointness += self.disjointness[
#                     asm.pcbm(0).hof().egress_if]
#             candidate.disjointness = (path_disjointness + as_disjointness +
#                                       if_disjointness)
#             if candidate.disjointness > max_disjointness:
#                 max_disjointness = candidate.disjointness
#         if max_disjointness > 0.0:
#             for candidate in self.candidates:
#                 candidate.disjointness /= max_disjointness
#
#     def _update_all_delay_time(self):
#         """Update the delay time property of all path candidates."""
#         max_delay_time = 0
#         for candidate in self.candidates:
#             candidate.delay_time = (candidate.last_seen_time -
#                                     candidate.pcb.get_timestamp() + 1)
#             if candidate.delay_time > max_delay_time:
#                 max_delay_time = candidate.delay_time
#         for candidate in self.candidates:
#             candidate.delay_time /= max_delay_time
#
#     def _update_all_fidelity(self):
#         """Update the fidelity of all path candidates."""
#         self._update_disjointness_db()
#         self._update_all_disjointness()
#         self._update_all_delay_time()
#         for candidate in self.candidates:
#             candidate.update_fidelity(self.path_policy)
#
#     def get_best_segments(self, k=None, sending=True):
#         """
#         Return the k best paths from the temporary buffer.
#
#         Select the k best paths from the set of candidate paths. At the time of
#         selection, the PathStore computes the fidelity of all candidate path
#         segments and returns the k paths with the highest fidelity.
#
#         When computing the fidelity, only the path properties that vary in time
#         need to be recomputed: the freshness, delay, and disjointness. The
#         length and number of peering links is constant.
#
#         :param int k: default best set size.
#         """
#         if k is None:
#             k = self.path_policy.best_set_size
#         self._remove_expired_segments()
#         self._update_all_fidelity()
#         best_candidates = heapq.nlargest(k, self.candidates,
#                                          key=lambda y: y.fidelity)
#         if sending:
#             for candidate in best_candidates:
#                 candidate.sending()
#         return [x.pcb for x in best_candidates]
#
#     def get_latest_history_snapshot(self, k=None):
#         """
#         Return the latest k best paths from the history.
#
#         :param int k: default best set size.
#         """
#         if k is None:
#             k = self.path_policy.best_set_size
#         best_paths = []
#         if self.best_paths_history:
#             for candidate in self.best_paths_history[0][:k]:
#                 best_paths.append(candidate.pcb)
#         return best_paths
#
#     def _remove_expired_segments(self):
#         """Remove candidates if their expiration_time is up."""
#         rec_ids = []
#         now = SCIONTime.get_time()
#         for candidate in self.candidates:
#             if candidate.expiration_time <= now:
#                 rec_ids.append(candidate.id)
#         self.remove_segments(rec_ids)
#
#     def remove_segments(self, rec_ids):
#         """
#         Remove segments in 'rec_ids' from the candidates.
#
#         :param list rec_ids: list of record IDs to remove.
#         """
#         self.candidates[:] = [c for c in self.candidates if c.id not in rec_ids]
#         if self.candidates:
#             self._update_all_fidelity()
#             self.candidates = sorted(self.candidates, key=lambda x: x.fidelity,
#                                      reverse=True)
#
#     def get_segment(self, rec_id):
#         """
#         Return the segment for the corresponding record ID or None.
#
#         :param str rec_id: ID of the segment to return.
#         """
#         for record in self.candidates:
#             if record.id == rec_id:
#                 return record.pcb
#         return None
#
#     def __str__(self):
#         """
#         Return a string with the path store data.
#         """
#         ret = ["PathStore:"]
#         for candidate in self.candidates:
#             ret.append("  %s" % candidate)
#         return "\n".join(ret)
