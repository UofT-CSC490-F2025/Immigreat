"""Lambda: lightweight DB admin/query helper.

Event contract:
- action: "tables" | "describe"
- table: required when action == "describe"

Returns JSON serializable dict with results or error.
"""

# View documents table details using:
# aws lambda invoke --region us-east-1 `
#   --function-name db-admin-function-prod `
#   --cli-binary-format raw-in-base64-out `
#   --payload '{\"action\":\"describe\",\"table\":\"documents\"}' out.json

# Then:
# (Get-Content out.json | ConvertFrom-Json).body | ConvertFrom-Json | ConvertTo-Json -Depth 6
from __future__ import annotations

import json
import os
import boto3
import psycopg2


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
        else:
            return {"statusCode": 400, "body": json.dumps({"error": "Unknown action. Use 'tables' or 'describe'"})}
    except Exception as e:
        # Minimal error shaping for quick debugging
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
