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

"""Private module: Helpers for I/O operations."""

from __future__ import annotations

import datetime
import itertools
import textwrap
import types
from typing import Callable, Dict, Iterable, Optional, Sequence, Union
import uuid

import google.cloud.bigquery as bigquery
import ibis
import ibis.expr.types as ibis_types
import pandas

import bigframes.constants as constants

IO_ORDERING_ID = "bqdf_row_nums"
MAX_LABELS_COUNT = 64
TEMP_TABLE_PREFIX = "bqdf{date}_{random_id}"


def create_job_configs_labels(
    job_configs_labels: Optional[Dict[str, str]],
    api_methods: Sequence[str],
) -> Dict[str, str]:
    if job_configs_labels is None:
        job_configs_labels = {}

    labels = list(
        itertools.chain(
            job_configs_labels.keys(),
            (f"recent-bigframes-api-{i}" for i in range(len(api_methods))),
        )
    )
    values = list(itertools.chain(job_configs_labels.values(), api_methods))
    return dict(zip(labels[:MAX_LABELS_COUNT], values[:MAX_LABELS_COUNT]))


def create_export_csv_statement(
    table_id: str, uri: str, field_delimiter: str, header: bool
) -> str:
    return create_export_data_statement(
        table_id,
        uri,
        "CSV",
        {
            "field_delimiter": field_delimiter,
            "header": header,
        },
    )


def create_export_data_statement(
    table_id: str, uri: str, format: str, export_options: Dict[str, Union[bool, str]]
) -> str:
    all_options: Dict[str, Union[bool, str]] = {
        "uri": uri,
        "format": format,
        # TODO(swast): Does pandas have an option not to overwrite files?
        "overwrite": True,
    }
    all_options.update(export_options)
    export_options_str = ", ".join(
        format_option(key, value) for key, value in all_options.items()
    )
    # Manually generate ORDER BY statement since ibis will not always generate
    # it in the top level statement. This causes BigQuery to then run
    # non-distributed sort and run out of memory.
    return textwrap.dedent(
        f"""
        EXPORT DATA
        OPTIONS (
            {export_options_str}
        ) AS
        SELECT * EXCEPT ({IO_ORDERING_ID})
        FROM `{table_id}`
        ORDER BY {IO_ORDERING_ID}
        """
    )


def random_table(dataset: bigquery.DatasetReference) -> bigquery.TableReference:
    """Generate a random table ID with BigQuery DataFrames prefix.
    Args:
        dataset (google.cloud.bigquery.DatasetReference):
            The dataset to make the table reference in. Usually the anonymous
            dataset for the session.
    Returns:
        google.cloud.bigquery.TableReference:
            Fully qualified table ID of a table that doesn't exist.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    random_id = uuid.uuid4().hex
    table_id = TEMP_TABLE_PREFIX.format(
        date=now.strftime("%Y%m%d"), random_id=random_id
    )
    return dataset.table(table_id)


def table_ref_to_sql(table: bigquery.TableReference) -> str:
    """Format a table reference as escaped SQL."""
    return f"`{table.project}`.`{table.dataset_id}`.`{table.table_id}`"


def create_snapshot_sql(
    table_ref: bigquery.TableReference, current_timestamp: datetime.datetime
) -> str:
    """Query a table via 'time travel' for consistent reads."""
    # If we have an anonymous query results table, it can't be modified and
    # there isn't any BigQuery time travel.
    if table_ref.dataset_id.startswith("_"):
        return f"SELECT * FROM `{table_ref.project}`.`{table_ref.dataset_id}`.`{table_ref.table_id}`"

    return textwrap.dedent(
        f"""
        SELECT *
        FROM `{table_ref.project}`.`{table_ref.dataset_id}`.`{table_ref.table_id}`
        FOR SYSTEM_TIME AS OF TIMESTAMP({repr(current_timestamp.isoformat())})
        """
    )


def create_temp_table(
    bqclient: bigquery.Client,
    dataset: bigquery.DatasetReference,
    expiration: datetime.datetime,
    *,
    schema: Optional[Iterable[bigquery.SchemaField]] = None,
    cluster_columns: Optional[list[str]] = None,
) -> str:
    """Create an empty table with an expiration in the desired dataset."""
    table_ref = random_table(dataset)
    destination = bigquery.Table(table_ref)
    destination.expires = expiration
    destination.schema = schema
    if cluster_columns:
        destination.clustering_fields = cluster_columns
    bqclient.create_table(destination)
    return f"{table_ref.project}.{table_ref.dataset_id}.{table_ref.table_id}"


def set_table_expiration(
    bqclient: bigquery.Client,
    table_ref: bigquery.TableReference,
    expiration: datetime.datetime,
) -> None:
    """Set an expiration time for an existing BigQuery table."""
    table = bqclient.get_table(table_ref)
    table.expires = expiration
    bqclient.update_table(table, ["expires"])


# BigQuery REST API returns types in Legacy SQL format
# https://cloud.google.com/bigquery/docs/data-types but we use Standard SQL
# names
# https://cloud.google.com/bigquery/docs/reference/standard-sql/data-types
BQ_STANDARD_TYPES = types.MappingProxyType(
    {
        "BOOLEAN": "BOOL",
        "INTEGER": "INT64",
        "FLOAT": "FLOAT64",
    }
)


def bq_field_to_type_sql(field: bigquery.SchemaField):
    if field.mode == "REPEATED":
        nested_type = bq_field_to_type_sql(
            bigquery.SchemaField(
                field.name, field.field_type, mode="NULLABLE", fields=field.fields
            )
        )
        return f"ARRAY<{nested_type}>"

    if field.field_type == "RECORD":
        nested_fields_sql = ", ".join(
            bq_field_to_sql(child_field) for child_field in field.fields
        )
        return f"STRUCT<{nested_fields_sql}>"

    type_ = field.field_type
    return BQ_STANDARD_TYPES.get(type_, type_)


def bq_field_to_sql(field: bigquery.SchemaField):
    name = field.name
    type_ = bq_field_to_type_sql(field)
    return f"`{name}` {type_}"


def bq_schema_to_sql(schema: Iterable[bigquery.SchemaField]):
    return ", ".join(bq_field_to_sql(field) for field in schema)


def format_option(key: str, value: Union[bool, str]) -> str:
    if isinstance(value, bool):
        return f"{key}=true" if value else f"{key}=false"
    return f"{key}={repr(value)}"


def pandas_to_bigquery_load(
    *,
    api_name: str,
    bqclient: bigquery.Client,
    dataframe: pandas.DataFrame,
    dataset: bigquery.DatasetReference,
    ibis_client: ibis.BaseBackend,
    ordering_col: str,
    schema: Sequence[bigquery.SchemaField],
    wait_for_job: Callable,
) -> ibis_types.Table:
    """Load a pandas DataFrame to BigQuery.

    It is assumed that the pandas DataFrame has already been pre-processed to
    include an ordering ID column as well as column names which are valid in
    SQL.

    Args:
        api_name (str):
            Public function used to initiate this load job. Used for telemetry.
        bqclient (google.cloud.bigquery.Client):
            Client to make API requests.
        dataframe (pandas.DataFrame):
            Pre-processed DataFrame to load into BigQuery.
        dataset (google.cloud.bigquery.DatasetReference):
            Staging dataset to create the new table in.
        ibis_client (ibis.BaseBackend):
            Ibis client to create the expression.
        ordering_col (str):
            ID of the column used for the ordering ID.
        schema (Sequence[google.cloud.bigquery.SchemaField]):
            Expected schema of the table to be created. Used as hints by the
            BigQuery client library in serializing the DataFrame to parquet.
        wait_for_job (Callable):
            A function that waits for the job object to finish. Used to show
            progress to the user.

    Returns:
        ibis.expr.types.Table:
            An ibis table expression representing the loaded table.
    """
    job_config = bigquery.LoadJobConfig(schema=schema)
    job_config.clustering_fields = [ordering_col]
    job_config.labels = {"bigframes-api": api_name}

    destination = random_table(dataset)
    load_job = bqclient.load_table_from_dataframe(
        dataframe,
        destination,
        job_config=job_config,
    )
    wait_for_job(load_job)

    return ibis_client.table(  # type: ignore
        destination.table_id,
        # TODO: use "dataset_id" as the "schema"
        database=f"{destination.project}.{destination.dataset_id}",
    )


def pandas_to_bigquery_streaming(
    *,
    bqclient: bigquery.Client,
    dataframe: pandas.DataFrame,
    dataset: bigquery.DatasetReference,
    ibis_client: ibis.BaseBackend,
    ordering_col: str,
    schema: Sequence[bigquery.SchemaField],
) -> ibis_types.Table:
    """Same as pandas_to_bigquery_load, but uses the BQ legacy streaming API."""

    destination = bigquery.Table(random_table(dataset))
    destination.schema = schema
    destination.clustering_fields = [ordering_col]
    bqclient.create_table(destination)

    # TODO(swast): Confirm that the index is written.
    for errors in bqclient.insert_rows_from_dataframe(
        destination,
        dataframe,
    ):
        if errors:
            raise ValueError(
                f"Problem loading at least one row from DataFrame: {errors}. {constants.FEEDBACK_LINK}"
            )

    # There may be duplicate rows because of hidden retries, so use a query to
    # deduplicate based on the ordering ID, which is guaranteed to be unique.
    table_expression = ibis_client.table(  # type: ignore
        destination.table_id,
        # TODO: use "dataset_id" as the "schema"
        database=f"{destination.project}.{destination.dataset_id}",
    )
    grouped = table_expression.group_by(ordering_col)
    return grouped.aggregate(
        **{column: grouped[column].arbitrary() for column in grouped.columns}
    )
