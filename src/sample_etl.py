"""Sample ETL job deployed by the bundle to dev / uat / prod."""
import argparse
import os
import sys

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
except NameError:  # __file__ not defined in some interactive contexts
    pass

from pyspark.sql import SparkSession  # noqa: E402

from transformations import calculate_net_amount, classify_order_size  # noqa: E402

SAMPLE_ORDERS = [
    ("O-1001", 50.0, 10.0),
    ("O-1002", 250.0, 0.0),
    ("O-1003", 1500.0, 20.0),
    ("O-1004", 999.99, 5.0),
]


def build_rows():
    rows = []
    for order_id, amount, discount in SAMPLE_ORDERS:
        net = calculate_net_amount(amount, discount)
        rows.append((order_id, amount, discount, net, classify_order_size(net)))
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--env", required=True)
    args = parser.parse_args()

    spark = SparkSession.builder.getOrCreate()
    df = spark.createDataFrame(
        build_rows(),
        "order_id string, amount double, discount_pct double, net_amount double, order_size string",
    )
    table = f"{args.catalog}.{args.schema}.jira2code_sample_orders_{args.env}"
    df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(table)
    print(f"Wrote {df.count()} rows to {table}")


if __name__ == "__main__":
    main()
