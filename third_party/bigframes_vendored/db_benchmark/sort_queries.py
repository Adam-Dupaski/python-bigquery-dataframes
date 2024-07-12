# Contains code from https://github.com/duckdblabs/db-benchmark/blob/master/pandas/sort-pandas.py

import bigframes.pandas as bpd


def q1(table_id: str) -> None:
    print("Sort benchmark 1: sort by int id2")

    x = bpd.read_gbq(f"bigframes-dev-perf.dbbenchmark.{table_id}")

    ans = x.sort_values("id2")
    print(ans.shape)

    chk = [ans["v1"].sum()]
    print(chk)

    bpd.reset_session()
