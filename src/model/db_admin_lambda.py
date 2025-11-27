"""Lambda: lightweight DB admin/query helper.

Event contract:
- action: "tables" | "describe" | "first"
- table: required when action in {"describe", "first"}
- order_by: optional column name for "first" action (defaults to physical first row)
- columns: optional list[str] of columns to select for "first" (defaults to all columns)

Returns JSON serializable dict with results or error.
"""

# View documents table metadata details using:
# aws lambda invoke --region us-east-1 `
#   --function-name db-admin-function-prod `
#   --cli-binary-format raw-in-base64-out `
#   --payload '{\"action\":\"describe\",\"table\":\"documents\"}' out.json

# View first row from documents table using:
# aws lambda invoke --region us-east-1 `
#   --function-name db-admin-function-prod `
#   --cli-binary-format raw-in-base64-out `
#   --payload '{\"action\":\"first\",\"table\":\"documents\",\"order_by\":\"id\"}' out.json

# Then:
# (Get-Content out.json | ConvertFrom-Json).body | ConvertFrom-Json | ConvertTo-Json -Depth 6

# Get first row from documents (optionally order by a column):
# aws lambda invoke --region us-east-1 `
#   --function-name db-admin-function-prod `
#   --cli-binary-format raw-in-base64-out `
#   --payload '{\"action\":\"first\",\"table\":\"documents\",\"order_by\":\"id\"}' out.json
from __future__ import annotations

import json
import os
import boto3
import psycopg2
from psycopg2 import sql


_secrets = boto3.client("secretsmanager")


def _get_db_conn():
    secret_arn = os.environ["PGVECTOR_SECRET_ARN"]
    sec = _secrets.get_secret_value(SecretId=secret_arn)
    creds = json.loads(sec["SecretString"])  # host, port, dbname, username, password
    return psycopg2.connect(
        host=creds["host"], port=creds["port"], dbname=creds["dbname"],
        user=creds["username"], password=creds["password"], sslmode="require",
    )


def _list_tables():
    with _get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema='public' AND table_type='BASE TABLE'
                ORDER BY table_name
                """
            )
            return [r[0] for r in cur.fetchall()]


def _describe_table(table: str):
    with _get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema='public' AND table_name=%s
                ORDER BY ordinal_position
                """,
                (table,),
            )
            cols = [
                {"name": name, "type": dtype, "nullable": (nullable == "YES")}
                for name, dtype, nullable in cur.fetchall()
            ]

            cur.execute(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname='public' AND tablename=%s
                ORDER BY indexname
                """,
                (table,),
            )
            idxs = [
                {"name": name, "definition": definition}
                for name, definition in cur.fetchall()
            ]

            return {"columns": cols, "indexes": idxs}


def _first_row(table: str, order_by: str | None = None, columns: list[str] | None = None):
    """Return the first row from a table as a dict.

    Notes:
    - Uses LIMIT 1; if order_by is provided, orders ascending by that column.
    - If columns is provided, only selects those identifiers; otherwise selects all (*).
    - All identifiers are safely quoted using psycopg2.sql.Identifier.
    """
    with _get_db_conn() as conn:
        with conn.cursor() as cur:
            # Build SELECT list
            if columns:
                col_sql = sql.SQL(", ").join(sql.Identifier(c) for c in columns)
            else:
                col_sql = sql.SQL("*")

            # Optional ORDER BY
            order_sql = sql.SQL("")
            if order_by:
                order_sql = sql.SQL(" ORDER BY {} ASC").format(sql.Identifier(order_by))

            query = sql.SQL("SELECT {cols} FROM {tbl}{order} LIMIT 1").format(
                cols=col_sql,
                tbl=sql.Identifier(table),
                order=order_sql,
            )

            cur.execute(query)
            row = cur.fetchone()
            if row is None:
                return {"row": None, "count": 0}

            col_names = [desc[0] for desc in cur.description]
            rec = {k: v for k, v in zip(col_names, row)}
            return {"row": rec, "count": 1}


def handler(event, context):
    action = (event or {}).get("action")
    try:
        if action == "tables":
            tables = _list_tables()
            return {"statusCode": 200, "body": json.dumps({"tables": tables})}
        elif action == "describe":
            table = (event or {}).get("table")
            if not table:
                return {"statusCode": 400, "body": json.dumps({"error": "Missing 'table' for describe"})}
            desc = _describe_table(table)
            return {"statusCode": 200, "body": json.dumps({"table": table, **desc})}
        elif action == "first":
            payload = event or {}
            table = payload.get("table")
            if not table:
                return {"statusCode": 400, "body": json.dumps({"error": "Missing 'table' for first"})}
            order_by = payload.get("order_by")
            columns = payload.get("columns")
            result = _first_row(table, order_by=order_by, columns=columns)
            return {"statusCode": 200, "body": json.dumps({"table": table, **result}, default=str)}
        else:
            return {"statusCode": 400, "body": json.dumps({"error": "Unknown action. Use 'tables', 'describe', or 'first'"})}
    except Exception as e:
        # Minimal error shaping for quick debugging
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
