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

"""Helpers to join ArrayValue objects."""

from __future__ import annotations

from typing import Literal, Tuple

import ibis
import ibis.expr.datatypes as ibis_dtypes
import ibis.expr.types as ibis_types

import bigframes.core.compile.compiled as compiled
import bigframes.core.guid as guids
import bigframes.core.identifiers as ids
import bigframes.core.ordering as orderings


def join_by_column_ordered(
    left: compiled.OrderedIR,
    right: compiled.OrderedIR,
    conditions: Tuple[Tuple[int, int], ...],
    type: Literal["inner", "outer", "left", "right", "cross"],
) -> compiled.OrderedIR:
    """Join two expressions by column equality.

    Arguments:
        left: Expression for left table to join.
        left_column_ids: Column IDs (not label) to join by.
        right: Expression for right table to join.
        right_column_ids: Column IDs (not label) to join by.
        how: The type of join to perform.
        allow_row_identity_join (bool):
            If True, allow matching by row identity. Set to False to always
            perform a true JOIN in generated SQL.
    Returns:
        The joined expression. The resulting columns will be, in order,
        first the coalesced join keys, then, all the left columns, and
        finally, all the right columns.
    """

    # Do not reset the generator
    id_generator = ids.standard_identifiers()
    l_value_mapping = dict(zip(left.column_ids, id_generator))
    r_value_mapping = dict(zip(right.column_ids, id_generator))

    l_hidden_mapping = {
        id: guids.generate_guid("hidden_") for id in left._hidden_column_ids
    }
    r_hidden_mapping = {
        id: guids.generate_guid("hidden_") for id in right._hidden_column_ids
    }

    l_mapping = {**l_value_mapping, **l_hidden_mapping}
    r_mapping = {**r_value_mapping, **r_hidden_mapping}

    left_table = left._to_ibis_expr(
        ordering_mode="unordered",
        expose_hidden_cols=True,
        col_id_overrides=l_mapping,
    )
    right_table = right._to_ibis_expr(
        ordering_mode="unordered",
        expose_hidden_cols=True,
        col_id_overrides=r_mapping,
    )
    join_conditions = [
        value_to_join_key(left_table[left_table.columns[left_index]])
        == value_to_join_key(right_table[right_table.columns[right_index]])
        for left_index, right_index in conditions
    ]

    combined_table = ibis.join(
        left_table,
        right_table,
        predicates=join_conditions,
        how=type,  # type: ignore
    )

    # Preserve ordering accross joins.
    ordering = orderings.join_orderings(
        left._ordering,
        right._ordering,
        l_mapping,
        r_mapping,
        left_order_dominates=(type != "right"),
    )

    # We could filter out the original join columns, but predicates/ordering
    # might still reference them in implicit joins.
    columns = [combined_table[l_mapping[col.get_name()]] for col in left.columns] + [
        combined_table[r_mapping[col.get_name()]] for col in right.columns
    ]
    hidden_ordering_columns = [
        *[
            combined_table[l_hidden_mapping[col.get_name()]]
            for col in left._hidden_ordering_columns
        ],
        *[
            combined_table[r_hidden_mapping[col.get_name()]]
            for col in right._hidden_ordering_columns
        ],
    ]
    return compiled.OrderedIR(
        combined_table,
        columns=columns,
        hidden_ordering_columns=hidden_ordering_columns,
        ordering=ordering,
    )


def join_by_column_unordered(
    left: compiled.UnorderedIR,
    right: compiled.UnorderedIR,
    conditions: Tuple[Tuple[int, int], ...],
    type: Literal["inner", "outer", "left", "right", "cross"],
) -> compiled.UnorderedIR:
    """Join two expressions by column equality.

    Arguments:
        left: Expression for left table to join.
        left_column_ids: Column IDs (not label) to join by.
        right: Expression for right table to join.
        right_column_ids: Column IDs (not label) to join by.
        how: The type of join to perform.
        allow_row_identity_join (bool):
            If True, allow matching by row identity. Set to False to always
            perform a true JOIN in generated SQL.
    Returns:
        The joined expression. The resulting columns will be, in order,
        first the coalesced join keys, then, all the left columns, and
        finally, all the right columns.
    """
    id_generator = ids.standard_identifiers()
    l_mapping = dict(zip(left.column_ids, id_generator))
    r_mapping = dict(zip(right.column_ids, id_generator))
    left_table = left._to_ibis_expr(
        col_id_overrides=l_mapping,
    )
    right_table = right._to_ibis_expr(
        col_id_overrides=r_mapping,
    )
    join_conditions = [
        value_to_join_key(left_table[left_table.columns[left_index]])
        == value_to_join_key(right_table[right_table.columns[right_index]])
        for left_index, right_index in conditions
    ]

    combined_table = ibis.join(
        left_table,
        right_table,
        predicates=join_conditions,
        how=type,  # type: ignore
    )
    # We could filter out the original join columns, but predicates/ordering
    # might still reference them in implicit joins.
    columns = [combined_table[l_mapping[col.get_name()]] for col in left.columns] + [
        combined_table[r_mapping[col.get_name()]] for col in right.columns
    ]
    return compiled.UnorderedIR(
        combined_table,
        columns=columns,
    )


def value_to_join_key(value: ibis_types.Value):
    """Converts nullable values to non-null string SQL will not match null keys together - but pandas does."""
    if not value.type().is_string():
        value = value.cast(ibis_dtypes.str)
    return value.fillna(ibis_types.literal("$NULL_SENTINEL$"))
