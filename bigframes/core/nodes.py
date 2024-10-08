# Copyright 2023 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import abc
from dataclasses import dataclass, field, fields, replace
import datetime
import functools
import itertools
import typing
from typing import Callable, Iterable, Sequence, Tuple

import google.cloud.bigquery as bq

import bigframes.core.expression as ex
import bigframes.core.guid
import bigframes.core.identifiers
import bigframes.core.identifiers as bfet_ids
from bigframes.core.ordering import OrderingExpression
import bigframes.core.schema as schemata
import bigframes.core.window_spec as window
import bigframes.dtypes
import bigframes.operations.aggregations as agg_ops

if typing.TYPE_CHECKING:
    import bigframes.core.ordering as orderings
    import bigframes.session


# A fixed number of variable to assume for overhead on some operations
OVERHEAD_VARIABLES = 5

COLUMN_SET = frozenset[bfet_ids.ColumnId]


@dataclass(frozen=True)
class Field:
    id: bfet_ids.ColumnId
    dtype: bigframes.dtypes.Dtype


@dataclass(eq=False, frozen=True)
class BigFrameNode(abc.ABC):
    """
    Immutable node for representing 2D typed array as a tree of operators.

    All subclasses must be hashable so as to be usable as caching key.
    """

    @property
    def deterministic(self) -> bool:
        """Whether this node will evaluates deterministically."""
        return True

    @property
    def row_preserving(self) -> bool:
        """Whether this node preserves input rows."""
        return True

    @property
    def non_local(self) -> bool:
        """
        Whether this node combines information across multiple rows instead of processing rows independently.
        Used as an approximation for whether the expression may require shuffling to execute (and therefore be expensive).
        """
        return False

    @property
    def child_nodes(self) -> typing.Sequence[BigFrameNode]:
        """Direct children of this node"""
        return tuple([])

    @functools.cached_property
    def session(self):
        sessions = []
        for child in self.child_nodes:
            if child.session is not None:
                sessions.append(child.session)
        unique_sessions = len(set(sessions))
        if unique_sessions > 1:
            raise ValueError("Cannot use combine sources from multiple sessions.")
        elif unique_sessions == 1:
            return sessions[0]
        return None

    def _as_tuple(self) -> Tuple:
        """Get all fields as tuple."""
        return tuple(getattr(self, field.name) for field in fields(self))

    def __hash__(self) -> int:
        # Custom hash that uses cache to avoid costly recomputation
        return self._cached_hash

    def __eq__(self, other) -> bool:
        # Custom eq that tries to short-circuit full structural comparison
        if not isinstance(other, self.__class__):
            return False
        if self is other:
            return True
        if hash(self) != hash(other):
            return False
        return self._as_tuple() == other._as_tuple()

    # BigFrameNode trees can be very deep so its important avoid recalculating the hash from scratch
    # Each subclass of BigFrameNode should use this property to implement __hash__
    # The default dataclass-generated __hash__ method is not cached
    @functools.cached_property
    def _cached_hash(self):
        return hash(self._as_tuple())

    @property
    def roots(self) -> typing.Set[BigFrameNode]:
        roots = itertools.chain.from_iterable(
            map(lambda child: child.roots, self.child_nodes)
        )
        return set(roots)

    # TODO: For deep trees, this can create a lot of overhead, maybe use zero-copy persistent datastructure?
    @property
    @abc.abstractmethod
    def fields(self) -> Tuple[Field, ...]:
        ...

    @property
    def ids(self) -> Iterable[bfet_ids.ColumnId]:
        return (field.id for field in self.fields)

    @property
    @abc.abstractmethod
    def variables_introduced(self) -> int:
        """
        Defines number of values created by the current node. Helps represent the "width" of a query
        """
        ...

    @property
    def relation_ops_created(self) -> int:
        """
        Defines the number of relational ops generated by the current node. Used to estimate query planning complexity.
        """
        return 1

    @property
    def joins(self) -> bool:
        """
        Defines whether the node joins data.
        """
        return False

    @property
    @abc.abstractmethod
    def order_ambiguous(self) -> bool:
        """
        Whether row ordering is potentially ambiguous. For example, ReadTable (without a primary key) could be ordered in different ways.
        """
        ...

    @property
    @abc.abstractmethod
    def explicitly_ordered(self) -> bool:
        """
        Whether row ordering is potentially ambiguous. For example, ReadTable (without a primary key) could be ordered in different ways.
        """
        ...

    @functools.cached_property
    def total_variables(self) -> int:
        return self.variables_introduced + sum(
            map(lambda x: x.total_variables, self.child_nodes)
        )

    @functools.cached_property
    def total_relational_ops(self) -> int:
        return self.relation_ops_created + sum(
            map(lambda x: x.total_relational_ops, self.child_nodes)
        )

    @functools.cached_property
    def total_joins(self) -> int:
        return int(self.joins) + sum(map(lambda x: x.total_joins, self.child_nodes))

    @functools.cached_property
    def schema(self) -> schemata.ArraySchema:
        # TODO: Make schema just a view on fields
        return schemata.ArraySchema(
            tuple(schemata.SchemaItem(i.id.name, i.dtype) for i in self.fields)
        )

    @property
    def planning_complexity(self) -> int:
        """
        Empirical heuristic measure of planning complexity.

        Used to determine when to decompose overly complex computations. May require tuning.
        """
        return self.total_variables * self.total_relational_ops * (1 + self.total_joins)

    @abc.abstractmethod
    def transform_children(
        self, t: Callable[[BigFrameNode], BigFrameNode]
    ) -> BigFrameNode:
        """Apply a function to each child node."""
        ...

    @property
    def defines_namespace(self) -> bool:
        """
        If true, this node establishes a new column id namespace.

        If false, this node consumes and produces ids in the namespace
        """
        return False

    @functools.cached_property
    def defined_variables(self) -> set[str]:
        """Full set of variables defined in the namespace, even if not selected."""
        self_defined_variables = set(self.schema.names)
        if self.defines_namespace:
            return self_defined_variables
        return self_defined_variables.union(
            *(child.defined_variables for child in self.child_nodes)
        )

    def get_type(self, id: bfet_ids.ColumnId) -> bigframes.dtypes.Dtype:
        return self._dtype_lookup[id]

    @functools.cached_property
    def _dtype_lookup(self):
        return {field.id: field.dtype for field in self.fields}

    def prune(self, used_cols: COLUMN_SET) -> BigFrameNode:
        return self.transform_children(lambda x: x.prune(used_cols))


@dataclass(frozen=True, eq=False)
class UnaryNode(BigFrameNode):
    child: BigFrameNode

    @property
    def child_nodes(self) -> typing.Sequence[BigFrameNode]:
        return (self.child,)

    @functools.cached_property
    def fields(self) -> Tuple[Field, ...]:
        return self.child.fields

    @property
    def explicitly_ordered(self) -> bool:
        return self.child.explicitly_ordered

    def transform_children(
        self, t: Callable[[BigFrameNode], BigFrameNode]
    ) -> BigFrameNode:
        return replace(self, child=t(self.child))

    @property
    def order_ambiguous(self) -> bool:
        return self.child.order_ambiguous


@dataclass(frozen=True, eq=False)
class JoinNode(BigFrameNode):
    left_child: BigFrameNode
    right_child: BigFrameNode
    conditions: typing.Tuple[typing.Tuple[ex.DerefOp, ex.DerefOp], ...]
    type: typing.Literal["inner", "outer", "left", "right", "cross"]

    def __post_init__(self):
        assert not (
            set(self.left_child.ids) & set(self.right_child.ids)
        ), "Join ids collide"

    @property
    def row_preserving(self) -> bool:
        return False

    @property
    def non_local(self) -> bool:
        return True

    @property
    def child_nodes(self) -> typing.Sequence[BigFrameNode]:
        return (self.left_child, self.right_child)

    @property
    def order_ambiguous(self) -> bool:
        return True

    @property
    def explicitly_ordered(self) -> bool:
        # Do not consider user pre-join ordering intent - they need to re-order post-join in unordered mode.
        return False

    @functools.cached_property
    def fields(self) -> Tuple[Field, ...]:
        return tuple(itertools.chain(self.left_child.fields, self.right_child.fields))

    @functools.cached_property
    def variables_introduced(self) -> int:
        """Defines the number of variables generated by the current node. Used to estimate query planning complexity."""
        return OVERHEAD_VARIABLES

    @property
    def joins(self) -> bool:
        return True

    def transform_children(
        self, t: Callable[[BigFrameNode], BigFrameNode]
    ) -> BigFrameNode:
        return replace(
            self, left_child=t(self.left_child), right_child=t(self.right_child)
        )

    @property
    def defines_namespace(self) -> bool:
        return True

    def prune(self, used_cols: COLUMN_SET) -> BigFrameNode:
        # If this is a cross join, make sure to select at least one column from each side
        new_used = used_cols.union(
            map(lambda x: x.id, itertools.chain.from_iterable(self.conditions))
        )
        return self.transform_children(lambda x: x.prune(new_used))


@dataclass(frozen=True, eq=False)
class ConcatNode(BigFrameNode):
    # TODO: Explcitly map column ids from each child
    children: Tuple[BigFrameNode, ...]

    def __post_init__(self):
        if len(self.children) == 0:
            raise ValueError("Concat requires at least one input table. Zero provided.")
        child_schemas = [child.schema.dtypes for child in self.children]
        if not len(set(child_schemas)) == 1:
            raise ValueError("All inputs must have identical dtypes. {child_schemas}")

    @property
    def child_nodes(self) -> typing.Sequence[BigFrameNode]:
        return self.children

    @property
    def order_ambiguous(self) -> bool:
        return any(child.order_ambiguous for child in self.children)

    @property
    def explicitly_ordered(self) -> bool:
        # Consider concat as an ordered operations (even though input frames may not be ordered)
        return True

    @functools.cached_property
    def fields(self) -> Tuple[Field, ...]:
        # TODO: Output names should probably be aligned beforehand or be part of concat definition
        return tuple(
            Field(bfet_ids.ColumnId(f"column_{i}"), field.dtype)
            for i, field in enumerate(self.children[0].fields)
        )

    @functools.cached_property
    def variables_introduced(self) -> int:
        """Defines the number of variables generated by the current node. Used to estimate query planning complexity."""
        return len(self.schema.items) + OVERHEAD_VARIABLES

    def transform_children(
        self, t: Callable[[BigFrameNode], BigFrameNode]
    ) -> BigFrameNode:
        return replace(self, children=tuple(t(child) for child in self.children))

    def prune(self, used_cols: COLUMN_SET) -> BigFrameNode:
        # TODO: Make concat prunable, probably by redefining
        return self


@dataclass(frozen=True, eq=False)
class FromRangeNode(BigFrameNode):
    # TODO: Enforce single-row, single column constraint
    start: BigFrameNode
    end: BigFrameNode
    step: int

    @property
    def roots(self) -> typing.Set[BigFrameNode]:
        return {self}

    @property
    def child_nodes(self) -> typing.Sequence[BigFrameNode]:
        return (self.start, self.end)

    @property
    def order_ambiguous(self) -> bool:
        return False

    @property
    def explicitly_ordered(self) -> bool:
        return True

    @functools.cached_property
    def fields(self) -> Tuple[Field, ...]:
        return (Field(bfet_ids.ColumnId("labels"), self.start.fields[0].dtype),)

    @functools.cached_property
    def variables_introduced(self) -> int:
        """Defines the number of variables generated by the current node. Used to estimate query planning complexity."""
        return len(self.schema.items) + OVERHEAD_VARIABLES

    def transform_children(
        self, t: Callable[[BigFrameNode], BigFrameNode]
    ) -> BigFrameNode:
        return replace(self, start=t(self.start), end=t(self.end))

    def prune(self, used_cols: COLUMN_SET) -> BigFrameNode:
        # TODO: Make FromRangeNode prunable (or convert to other node types)
        return self


# Input Nodex
# TODO: Most leaf nodes produce fixed column names based on the datasource
# They should support renaming
@dataclass(frozen=True, eq=False)
class LeafNode(BigFrameNode):
    @property
    def roots(self) -> typing.Set[BigFrameNode]:
        return {self}

    @property
    def supports_fast_head(self) -> bool:
        return False

    def transform_children(
        self, t: Callable[[BigFrameNode], BigFrameNode]
    ) -> BigFrameNode:
        return self

    @property
    def row_count(self) -> typing.Optional[int]:
        """How many rows are in the data source. None means unknown."""
        return None


class ScanItem(typing.NamedTuple):
    id: bfet_ids.ColumnId
    dtype: bigframes.dtypes.Dtype  # Might be multiple logical types for a given physical source type
    source_id: str  # Flexible enough for both local data and bq data


@dataclass(frozen=True)
class ScanList:
    items: typing.Tuple[ScanItem, ...]


@dataclass(frozen=True, eq=False)
class ReadLocalNode(LeafNode):
    feather_bytes: bytes
    data_schema: schemata.ArraySchema
    n_rows: int
    # Mapping of local ids to bfet id.
    scan_list: ScanList
    session: typing.Optional[bigframes.session.Session] = None

    @functools.cached_property
    def fields(self) -> Tuple[Field, ...]:
        return tuple(Field(col_id, dtype) for col_id, dtype, _ in self.scan_list.items)

    @functools.cached_property
    def variables_introduced(self) -> int:
        """Defines the number of variables generated by the current node. Used to estimate query planning complexity."""
        return len(self.scan_list.items) + 1

    @property
    def supports_fast_head(self) -> bool:
        return True

    @property
    def order_ambiguous(self) -> bool:
        return False

    @property
    def explicitly_ordered(self) -> bool:
        return True

    @property
    def row_count(self) -> typing.Optional[int]:
        return self.n_rows

    def prune(self, used_cols: COLUMN_SET) -> BigFrameNode:
        new_scan_list = ScanList(
            tuple(item for item in self.scan_list.items if item.id in used_cols)
        )
        return ReadLocalNode(
            self.feather_bytes,
            self.data_schema,
            self.n_rows,
            new_scan_list,
            self.session,
        )


@dataclass(frozen=True)
class GbqTable:
    project_id: str = field()
    dataset_id: str = field()
    table_id: str = field()
    physical_schema: Tuple[bq.SchemaField, ...] = field()
    n_rows: int = field()
    is_physical_table: bool = field()
    cluster_cols: typing.Optional[Tuple[str, ...]]

    @staticmethod
    def from_table(table: bq.Table, columns: Sequence[str] = ()) -> GbqTable:
        # Subsetting fields with columns can reduce cost of row-hash default ordering
        if columns:
            schema = tuple(item for item in table.schema if item.name in columns)
        else:
            schema = tuple(table.schema)
        return GbqTable(
            project_id=table.project,
            dataset_id=table.dataset_id,
            table_id=table.table_id,
            physical_schema=schema,
            n_rows=table.num_rows,
            is_physical_table=(table.table_type == "TABLE"),
            cluster_cols=None
            if table.clustering_fields is None
            else tuple(table.clustering_fields),
        )


@dataclass(frozen=True)
class BigqueryDataSource:
    """
    Google BigQuery Data source.

    This should not be modified once defined, as all attributes contribute to the default ordering.
    """

    table: GbqTable
    at_time: typing.Optional[datetime.datetime] = None
    # Added for backwards compatibility, not validated
    sql_predicate: typing.Optional[str] = None
    ordering: typing.Optional[orderings.RowOrdering] = None


## Put ordering in here or just add order_by node above?
@dataclass(frozen=True, eq=False)
class ReadTableNode(LeafNode):
    source: BigqueryDataSource
    # Subset of physical schema column
    # Mapping of table schema ids to bfet id.
    scan_list: ScanList

    table_session: bigframes.session.Session = field()

    def __post_init__(self):
        # enforce invariants
        physical_names = set(map(lambda i: i.name, self.source.table.physical_schema))
        if not set(scan.source_id for scan in self.scan_list.items).issubset(
            physical_names
        ):
            raise ValueError(
                f"Requested schema {self.scan_list} cannot be derived from table schemal {self.source.table.physical_schema}"
            )

    @property
    def session(self):
        return self.table_session

    @functools.cached_property
    def fields(self) -> Tuple[Field, ...]:
        return tuple(Field(col_id, dtype) for col_id, dtype, _ in self.scan_list.items)

    @property
    def relation_ops_created(self) -> int:
        # Assume worst case, where readgbq actually has baked in analytic operation to generate index
        return 3

    @property
    def supports_fast_head(self) -> bool:
        # Fast head is only supported when row offsets are available.
        # In the future, ORDER BY+LIMIT optimizations may allow fast head when
        # clustered and/or partitioned on ordering key
        return (self.source.ordering is not None) and self.source.ordering.is_sequential

    @property
    def order_ambiguous(self) -> bool:
        return (
            self.source.ordering is None
        ) or not self.source.ordering.is_total_ordering

    @property
    def explicitly_ordered(self) -> bool:
        return self.source.ordering is not None

    @functools.cached_property
    def variables_introduced(self) -> int:
        return len(self.scan_list.items) + 1

    @property
    def row_count(self) -> typing.Optional[int]:
        if self.source.sql_predicate is None and self.source.table.is_physical_table:
            return self.source.table.n_rows
        return None

    def prune(self, used_cols: COLUMN_SET) -> BigFrameNode:
        new_scan_list = ScanList(
            tuple(item for item in self.scan_list.items if item.id in used_cols)
        )
        return ReadTableNode(self.source, new_scan_list, self.table_session)


@dataclass(frozen=True, eq=False)
class CachedTableNode(ReadTableNode):
    # The original BFET subtree that was cached
    # note: this isn't a "child" node.
    original_node: BigFrameNode = field()

    def prune(self, used_cols: COLUMN_SET) -> BigFrameNode:
        new_scan_list = ScanList(
            tuple(item for item in self.scan_list.items if item.id in used_cols)
        )
        return CachedTableNode(
            self.source, new_scan_list, self.table_session, self.original_node
        )


# Unary nodes
@dataclass(frozen=True, eq=False)
class PromoteOffsetsNode(UnaryNode):
    col_id: bigframes.core.identifiers.ColumnId

    @property
    def non_local(self) -> bool:
        return True

    @property
    def fields(self) -> Tuple[Field, ...]:
        return (*self.child.fields, Field(self.col_id, bigframes.dtypes.INT_DTYPE))

    @property
    def relation_ops_created(self) -> int:
        return 2

    @functools.cached_property
    def variables_introduced(self) -> int:
        return 1

    def prune(self, used_cols: COLUMN_SET) -> BigFrameNode:
        if self.col_id not in used_cols:
            return self.child.prune(used_cols)
        else:
            new_used = used_cols.difference([self.col_id])
            return self.transform_children(lambda x: x.prune(new_used))


@dataclass(frozen=True, eq=False)
class FilterNode(UnaryNode):
    predicate: ex.Expression

    @property
    def row_preserving(self) -> bool:
        return False

    @property
    def variables_introduced(self) -> int:
        return 1

    def prune(self, used_cols: COLUMN_SET) -> BigFrameNode:
        consumed_ids = used_cols.union(self.predicate.column_references)
        pruned_child = self.child.prune(consumed_ids)
        return FilterNode(pruned_child, self.predicate)


@dataclass(frozen=True, eq=False)
class OrderByNode(UnaryNode):
    by: Tuple[OrderingExpression, ...]

    @property
    def variables_introduced(self) -> int:
        return 0

    @property
    def relation_ops_created(self) -> int:
        # Doesnt directly create any relational operations
        return 0

    @property
    def explicitly_ordered(self) -> bool:
        return True

    def prune(self, used_cols: COLUMN_SET) -> BigFrameNode:
        ordering_cols = itertools.chain.from_iterable(
            map(lambda x: x.referenced_columns, self.by)
        )
        consumed_ids = used_cols.union(ordering_cols)
        pruned_child = self.child.prune(consumed_ids)
        return OrderByNode(pruned_child, self.by)


@dataclass(frozen=True, eq=False)
class ReversedNode(UnaryNode):
    # useless field to make sure has distinct hash
    reversed: bool = True

    @property
    def variables_introduced(self) -> int:
        return 0

    @property
    def relation_ops_created(self) -> int:
        # Doesnt directly create any relational operations
        return 0


@dataclass(frozen=True, eq=False)
class SelectionNode(UnaryNode):
    input_output_pairs: typing.Tuple[
        typing.Tuple[ex.DerefOp, bigframes.core.identifiers.ColumnId], ...
    ]

    @functools.cached_property
    def fields(self) -> Tuple[Field, ...]:
        return tuple(
            Field(output, self.child.get_type(input.id))
            for input, output in self.input_output_pairs
        )

    @property
    def variables_introduced(self) -> int:
        # This operation only renames variables, doesn't actually create new ones
        return 0

    # TODO: Reuse parent namespace
    # Currently, Selection node allows renaming an reusing existing names, so it must establish a
    # new namespace.
    @property
    def defines_namespace(self) -> bool:
        return True

    def prune(self, used_cols: COLUMN_SET) -> BigFrameNode:
        pruned_selections = tuple(
            select for select in self.input_output_pairs if select[1] in used_cols
        )
        consumed_ids = frozenset(i[0].id for i in pruned_selections)

        pruned_child = self.child.prune(consumed_ids)
        return SelectionNode(pruned_child, pruned_selections)


@dataclass(frozen=True, eq=False)
class ProjectionNode(UnaryNode):
    """Assigns new variables (without modifying existing ones)"""

    assignments: typing.Tuple[
        typing.Tuple[ex.Expression, bigframes.core.identifiers.ColumnId], ...
    ]

    def __post_init__(self):
        input_types = self.child._dtype_lookup
        for expression, id in self.assignments:
            # throws TypeError if invalid
            _ = expression.output_type(input_types)
        # Cannot assign to existing variables - append only!
        assert all(name not in self.child.schema.names for _, name in self.assignments)

    @functools.cached_property
    def fields(self) -> Tuple[Field, ...]:
        input_types = self.child._dtype_lookup
        new_fields = (
            Field(id, bigframes.dtypes.dtype_for_etype(ex.output_type(input_types)))
            for ex, id in self.assignments
        )
        return (*self.child.fields, *new_fields)

    @property
    def variables_introduced(self) -> int:
        # ignore passthrough expressions
        new_vars = sum(1 for i in self.assignments if not i[0].is_identity)
        return new_vars

    def prune(self, used_cols: COLUMN_SET) -> BigFrameNode:
        pruned_assignments = tuple(i for i in self.assignments if i[1] in used_cols)
        if len(pruned_assignments) == 0:
            return self.child.prune(used_cols)
        consumed_ids = itertools.chain.from_iterable(
            i[0].column_references for i in pruned_assignments
        )
        pruned_child = self.child.prune(used_cols.union(consumed_ids))
        return ProjectionNode(pruned_child, pruned_assignments)


# TODO: Merge RowCount into Aggregate Node?
# Row count can be compute from table metadata sometimes, so it is a bit special.
@dataclass(frozen=True, eq=False)
class RowCountNode(UnaryNode):
    @property
    def row_preserving(self) -> bool:
        return False

    @property
    def non_local(self) -> bool:
        return True

    @functools.cached_property
    def fields(self) -> Tuple[Field, ...]:
        return (Field(bfet_ids.ColumnId("count"), bigframes.dtypes.INT_DTYPE),)

    @property
    def variables_introduced(self) -> int:
        return 1

    @property
    def defines_namespace(self) -> bool:
        return True


@dataclass(frozen=True, eq=False)
class AggregateNode(UnaryNode):
    aggregations: typing.Tuple[
        typing.Tuple[ex.Aggregation, bigframes.core.identifiers.ColumnId], ...
    ]
    by_column_ids: typing.Tuple[ex.DerefOp, ...] = tuple([])
    dropna: bool = True

    @property
    def row_preserving(self) -> bool:
        return False

    @property
    def non_local(self) -> bool:
        return True

    @functools.cached_property
    def fields(self) -> Tuple[Field, ...]:
        by_items = (
            Field(ref.id, self.child.get_type(ref.id)) for ref in self.by_column_ids
        )
        agg_items = (
            Field(
                id,
                bigframes.dtypes.dtype_for_etype(
                    agg.output_type(self.child._dtype_lookup)
                ),
            )
            for agg, id in self.aggregations
        )
        return (*by_items, *agg_items)

    @property
    def variables_introduced(self) -> int:
        return len(self.aggregations) + len(self.by_column_ids)

    @property
    def order_ambiguous(self) -> bool:
        return False

    @property
    def explicitly_ordered(self) -> bool:
        return True

    @property
    def defines_namespace(self) -> bool:
        return True

    def prune(self, used_cols: COLUMN_SET) -> BigFrameNode:
        by_ids = (ref.id for ref in self.by_column_ids)
        pruned_aggs = tuple(agg for agg in self.aggregations if agg[1] in used_cols)
        agg_inputs = itertools.chain.from_iterable(
            agg.column_references for agg, _ in pruned_aggs
        )
        consumed_ids = frozenset(itertools.chain(by_ids, agg_inputs))
        pruned_child = self.child.prune(consumed_ids)
        return AggregateNode(pruned_child, pruned_aggs, self.by_column_ids, self.dropna)


@dataclass(frozen=True, eq=False)
class WindowOpNode(UnaryNode):
    column_name: ex.DerefOp
    op: agg_ops.UnaryWindowOp
    window_spec: window.WindowSpec
    output_name: bigframes.core.identifiers.ColumnId
    never_skip_nulls: bool = False
    skip_reproject_unsafe: bool = False

    @property
    def non_local(self) -> bool:
        return True

    @functools.cached_property
    def fields(self) -> Tuple[Field, ...]:
        input_type = self.child.get_type(self.column_name.id)
        new_item_dtype = self.op.output_type(input_type)
        return (*self.child.fields, Field(self.output_name, new_item_dtype))

    @property
    def variables_introduced(self) -> int:
        return 1

    @property
    def relation_ops_created(self) -> int:
        # Assume that if not reprojecting, that there is a sequence of window operations sharing the same window
        return 0 if self.skip_reproject_unsafe else 4

    def prune(self, used_cols: COLUMN_SET) -> BigFrameNode:
        if self.output_name not in used_cols:
            return self.child
        consumed_ids = used_cols.difference([self.output_name]).union(
            [self.column_name.id]
        )
        return self.transform_children(lambda x: x.prune(consumed_ids))


# TODO: Remove this op
@dataclass(frozen=True, eq=False)
class ReprojectOpNode(UnaryNode):
    @property
    def variables_introduced(self) -> int:
        return 0

    @property
    def relation_ops_created(self) -> int:
        # This op is not a real transformation, just a hint to the sql generator
        return 0


@dataclass(frozen=True, eq=False)
class RandomSampleNode(UnaryNode):
    fraction: float

    @property
    def deterministic(self) -> bool:
        return False

    @property
    def row_preserving(self) -> bool:
        return False

    @property
    def variables_introduced(self) -> int:
        return 1


# TODO: Explode should create a new column instead of overriding the existing one
@dataclass(frozen=True, eq=False)
class ExplodeNode(UnaryNode):
    column_ids: typing.Tuple[ex.DerefOp, ...]

    @property
    def row_preserving(self) -> bool:
        return False

    @functools.cached_property
    def fields(self) -> Tuple[Field, ...]:
        return tuple(
            Field(
                field.id,
                bigframes.dtypes.arrow_dtype_to_bigframes_dtype(
                    self.child.get_type(field.id).pyarrow_dtype.value_type  # type: ignore
                ),
            )
            if field.id in set(map(lambda x: x.id, self.column_ids))
            else field
            for field in self.child.fields
        )

    @property
    def relation_ops_created(self) -> int:
        return 3

    @functools.cached_property
    def variables_introduced(self) -> int:
        return len(self.column_ids) + 1

    @property
    def defines_namespace(self) -> bool:
        return True

    def prune(self, used_cols: COLUMN_SET) -> BigFrameNode:
        # Cannot prune explode op
        return self.transform_children(
            lambda x: x.prune(used_cols.union(ref.id for ref in self.column_ids))
        )
