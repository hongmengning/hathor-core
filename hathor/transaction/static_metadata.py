#  Copyright 2024 Hathor Labs
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

from __future__ import annotations

import dataclasses
from abc import ABC
from dataclasses import dataclass
from itertools import chain, starmap, zip_longest
from operator import add
from typing import TYPE_CHECKING, Callable

from typing_extensions import Self

from hathor.feature_activation.feature import Feature
from hathor.feature_activation.model.feature_state import FeatureState
from hathor.types import VertexId
from hathor.util import json_dumpb, json_loadb

if TYPE_CHECKING:
    from hathor.conf.settings import HathorSettings
    from hathor.transaction import BaseTransaction, Block, Transaction
    from hathor.transaction.storage import TransactionStorage


@dataclass(slots=True, frozen=True, kw_only=True)
class VertexStaticMetadata(ABC):
    """
    Static Metadata represents vertex attributes that are not intrinsic to the vertex data, but can be calculated from
    only the vertex itself and its dependencies, and whose values never change.

    This class is an abstract base class for all static metadata types that includes attributes common to all vertex
    types.
    """

    # XXX: this is only used to defer the reward-lock verification from the transaction spending a reward to the first
    # block that confirming this transaction, it is important to always have this set to be able to distinguish an old
    # metadata (that does not have this calculated, from a tx with a new format that does have this calculated)
    min_height: int

    def to_bytes(self) -> bytes:
        """Convert this static metadata instance to a json bytes representation."""
        return json_dumpb(dataclasses.asdict(self))

    @classmethod
    def from_bytes(cls, data: bytes, *, target: 'BaseTransaction') -> 'VertexStaticMetadata':
        """Create a static metadata instance from a json bytes representation, with a known vertex type target."""
        from hathor.transaction import Block, Transaction
        json_dict = json_loadb(data)

        if isinstance(target, Block):
            return BlockStaticMetadata(**json_dict)

        if isinstance(target, Transaction):
            return TransactionStaticMetadata(**json_dict)

        raise NotImplementedError


@dataclass(slots=True, frozen=True, kw_only=True)
class BlockStaticMetadata(VertexStaticMetadata):
    height: int

    # A list of feature activation bit counts.
    # Each list index corresponds to a bit position, and its respective value is the rolling count of active bits from
    # the previous boundary block up to this block, including it. LSB is on the left.
    feature_activation_bit_counts: list[int]

    # A dict of features in the feature activation process and their respective state.
    feature_states: dict[Feature, FeatureState]

    @classmethod
    def create_from_storage(cls, block: 'Block', settings: HathorSettings, storage: 'TransactionStorage') -> Self:
        """Create a `BlockStaticMetadata` using dependencies provided by a storage."""
        return cls.create(block, settings, storage.get_vertex)

    @classmethod
    def create(
        cls,
        block: 'Block',
        settings: HathorSettings,
        vertex_getter: Callable[[VertexId], 'BaseTransaction']
    ) -> Self:
        """Create a `BlockStaticMetadata` using dependencies provided by a `vertex_getter`.
        This must be fast, ideally O(1)."""
        height = cls._calculate_height(block, vertex_getter)
        min_height = cls._calculate_min_height(block, vertex_getter)
        feature_activation_bit_counts = cls._calculate_feature_activation_bit_counts(
            block,
            height,
            settings,
            vertex_getter,
        )

        return cls(
            height=height,
            min_height=min_height,
            feature_activation_bit_counts=feature_activation_bit_counts,
            feature_states={},  # This will be populated in the next PR
        )

    @staticmethod
    def _calculate_height(block: 'Block', vertex_getter: Callable[[VertexId], 'BaseTransaction']) -> int:
        """Return the height of the block, i.e., the number of blocks since genesis"""
        if block.is_genesis:
            return 0

        from hathor.transaction import Block
        parent_hash = block.get_block_parent_hash()
        parent_block = vertex_getter(parent_hash)
        assert isinstance(parent_block, Block)
        return parent_block.static_metadata.height + 1

    @staticmethod
    def _calculate_min_height(block: 'Block', vertex_getter: Callable[[VertexId], 'BaseTransaction']) -> int:
        """The minimum height the next block needs to have, basically the maximum min-height of this block's parents.
        """
        # maximum min-height of any parent tx
        min_height = 0
        for tx_hash in block.get_tx_parents():
            tx = vertex_getter(tx_hash)
            min_height = max(min_height, tx.static_metadata.min_height)

        return min_height

    @classmethod
    def _calculate_feature_activation_bit_counts(
        cls,
        block: 'Block',
        height: int,
        settings: HathorSettings,
        vertex_getter: Callable[[VertexId], 'BaseTransaction'],
    ) -> list[int]:
        """
        Lazily calculates the feature_activation_bit_counts metadata attribute, which is a list of feature activation
        bit counts. After it's calculated for the first time, it's persisted in block metadata and must not be changed.

        Each list index corresponds to a bit position, and its respective value is the rolling count of active bits
        from the previous boundary block up to this block, including it. LSB is on the left.
        """
        previous_counts = cls._get_previous_feature_activation_bit_counts(block, height, settings, vertex_getter)
        bit_list = block._get_feature_activation_bit_list()

        count_and_bit_pairs = zip_longest(previous_counts, bit_list, fillvalue=0)
        updated_counts = starmap(add, count_and_bit_pairs)
        return list(updated_counts)

    @staticmethod
    def _get_previous_feature_activation_bit_counts(
        block: 'Block',
        height: int,
        settings: HathorSettings,
        vertex_getter: Callable[[VertexId], 'BaseTransaction'],
    ) -> list[int]:
        """
        Returns the feature_activation_bit_counts metadata attribute from the parent block,
        or no previous counts if this is a boundary block.
        """
        evaluation_interval = settings.FEATURE_ACTIVATION.evaluation_interval
        is_boundary_block = height % evaluation_interval == 0

        if is_boundary_block:
            return []

        from hathor.transaction import Block
        parent_hash = block.get_block_parent_hash()
        parent_block = vertex_getter(parent_hash)
        assert isinstance(parent_block, Block)

        return parent_block.static_metadata.feature_activation_bit_counts


@dataclass(slots=True, frozen=True, kw_only=True)
class TransactionStaticMetadata(VertexStaticMetadata):
    @classmethod
    def create_from_storage(cls, tx: 'Transaction', settings: HathorSettings, storage: 'TransactionStorage') -> Self:
        """Create a `TransactionStaticMetadata` using dependencies provided by a storage."""
        return cls.create(tx, settings, storage.get_vertex)

    @classmethod
    def create(
        cls,
        tx: 'Transaction',
        settings: HathorSettings,
        vertex_getter: Callable[[VertexId], 'BaseTransaction'],
    ) -> Self:
        """Create a `TransactionStaticMetadata` using dependencies provided by a `vertex_getter`.
        This must be fast, ideally O(1)."""
        min_height = cls._calculate_min_height(
            tx,
            settings,
            vertex_getter=vertex_getter,
        )

        return cls(
            min_height=min_height
        )

    @classmethod
    def _calculate_min_height(
        cls,
        tx: 'Transaction',
        settings: HathorSettings,
        vertex_getter: Callable[[VertexId], 'BaseTransaction'],
    ) -> int:
        """Calculates the min height the first block confirming this tx needs to have for reward lock verification."""
        if tx.is_genesis:
            return 0

        return max(
            # 1) don't drop the min height of any parent tx or input tx
            cls._calculate_inherited_min_height(tx, vertex_getter),
            # 2) include the min height for any reward being spent
            cls._calculate_my_min_height(tx, settings, vertex_getter),
        )

    @staticmethod
    def _calculate_inherited_min_height(
        tx: 'Transaction',
        vertex_getter: Callable[[VertexId], 'BaseTransaction']
    ) -> int:
        """ Calculates min height inherited from any input or parent"""
        min_height = 0
        iter_parents = tx.get_tx_parents()
        iter_inputs = (tx_input.tx_id for tx_input in tx.inputs)
        for vertex_id in chain(iter_parents, iter_inputs):
            vertex = vertex_getter(vertex_id)
            min_height = max(min_height, vertex.static_metadata.min_height)
        return min_height

    @staticmethod
    def _calculate_my_min_height(
        tx: 'Transaction',
        settings: HathorSettings,
        vertex_getter: Callable[[VertexId], 'BaseTransaction'],
    ) -> int:
        """ Calculates min height derived from own spent block rewards"""
        from hathor.transaction import Block
        min_height = 0
        for tx_input in tx.inputs:
            spent_tx = vertex_getter(tx_input.tx_id)
            if isinstance(spent_tx, Block):
                min_height = max(min_height, spent_tx.static_metadata.height + settings.REWARD_SPEND_MIN_BLOCKS + 1)
        return min_height
