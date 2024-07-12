# Contains code from https://github.com/duckdblabs/db-benchmark/blob/master/pandas/join-pandas.py
# and https://github.com/duckdblabs/db-benchmark/blob/main/_helpers/helpers.py

import bigframes.pandas as bpd


def q1(table_id: str):
    print("Join benchmark 1: small inner on int")

    x = bpd.read_gbq(f"bigframes-dev-perf.dbbenchmark.{table_id}")
    small = bpd.read_gbq(
        f"bigframes-dev-perf.dbbenchmark.{_get_join_table_id(table_id, 'small')}"
    )

    ans = x.merge(small, on="id1")
    print(ans.shape)

    chk = [ans["v1"].sum(), ans["v2"].sum()]
    print(chk)

    bpd.reset_session()


def q2(table_id: str):
    print("Join benchmark 2: medium inner on int")

    x = bpd.read_gbq(f"bigframes-dev-perf.dbbenchmark.{table_id}")
    medium = bpd.read_gbq(
        f"bigframes-dev-perf.dbbenchmark.{_get_join_table_id(table_id, 'medium')}"
    )

    ans = x.merge(medium, on="id2")
    print(ans.shape)

    chk = [ans["v1"].sum(), ans["v2"].sum()]
    print(chk)

    bpd.reset_session()


def q3(table_id: str):
    print("Join benchmark 3: medium outer on int")

    x = bpd.read_gbq(f"bigframes-dev-perf.dbbenchmark.{table_id}")
    medium = bpd.read_gbq(
        f"bigframes-dev-perf.dbbenchmark.{_get_join_table_id(table_id, 'medium')}"
    )

    ans = x.merge(medium, how="left", on="id2")
    print(ans.shape)

    chk = [ans["v1"].sum(), ans["v2"].sum()]
    print(chk)

    bpd.reset_session()


def q4(table_id: str):
    print("Join benchmark 4: medium inner on factor")

    x = bpd.read_gbq(f"bigframes-dev-perf.dbbenchmark.{table_id}")
    medium = bpd.read_gbq(
        f"bigframes-dev-perf.dbbenchmark.{_get_join_table_id(table_id, 'medium')}"
    )

    ans = x.merge(medium, on="id5")
    print(ans.shape)

    chk = [ans["v1"].sum(), ans["v2"].sum()]
    print(chk)

    bpd.reset_session()


def q5(table_id: str):
    print("Join benchmark 5: big inner on int")

    x = bpd.read_gbq(f"bigframes-dev-perf.dbbenchmark.{table_id}")
    big = bpd.read_gbq(
        f"bigframes-dev-perf.dbbenchmark.{_get_join_table_id(table_id, 'big')}"
    )

    ans = x.merge(big, on="id3")
    print(ans.shape)

    chk = [ans["v1"].sum(), ans["v2"].sum()]
    print(chk)

    bpd.reset_session()


def _get_join_table_id(table_id, join_size):
    x_n = int(float(table_id.split("_")[1]))

    if join_size == "small":
        y_n = "{:.0e}".format(x_n / 1e6)
    elif join_size == "medium":
        y_n = "{:.0e}".format(x_n / 1e3)
    else:
        y_n = "{:.0e}".format(x_n)
    return table_id.replace("NA", y_n).replace("+0", "")
