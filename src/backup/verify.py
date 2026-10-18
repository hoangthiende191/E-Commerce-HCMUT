import os
import sys

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

RECOVERY_DB = "hm-ecommerce-recovery"

EXPECTED_TABLES = [
    "customer",
    "login_account",
    "transaction",
    "contains",
    "article",
    "product",
    "product_type",
    "product_group",
    "graphical_appearance",
    "colour_group",
    "perceived_colour_value",
    "perceived_colour_master",
    "department",
    "garment_group",
    "index",
    "section",
    "index_group",
]


def validate_environment():
    required = {
        "DB_HOST": DB_HOST,
        "DB_NAME": DB_NAME,
        "DB_USER": DB_USER,
        "DB_PASSWORD": DB_PASSWORD,
    }

    missing = [key for key, value in required.items() if not value]

    if missing:
        raise ValueError(
            "Missing environment variable(s): " + ", ".join(missing)
        )


def connect(database):
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=database,
        user=DB_USER,
        password=DB_PASSWORD,
    )


def get_public_tables(conn):
    query = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
        ORDER BY table_name;
    """

    with conn.cursor() as cur:
        cur.execute(query)
        return {row[0] for row in cur.fetchall()}


def get_row_count(conn, table_name):
    query = f'SELECT COUNT(*) FROM public."{table_name}";'

    with conn.cursor() as cur:
        cur.execute(query)
        return cur.fetchone()[0]


def get_constraint_count(conn):
    query = """
        SELECT COUNT(*)
        FROM information_schema.table_constraints
        WHERE table_schema = 'public';
    """

    with conn.cursor() as cur:
        cur.execute(query)
        return cur.fetchone()[0]


def get_foreign_key_count(conn):
    query = """
        SELECT COUNT(*)
        FROM information_schema.table_constraints
        WHERE table_schema = 'public'
          AND constraint_type = 'FOREIGN KEY';
    """

    with conn.cursor() as cur:
        cur.execute(query)
        return cur.fetchone()[0]


def run_representative_query(conn):
    query = """
        SELECT
            c.customer_id,
            a.prod_name,
            SUM(ct.price * ct.quantity) AS total_revenue
        FROM public."transaction" AS t
        JOIN public.customer AS c
            ON t.customer_id = c.customer_id
        JOIN public.contains AS ct
            ON t.transaction_id = ct.transaction_id
        JOIN public.article AS a
            ON ct.article_id = a.article_id
        GROUP BY
            c.customer_id,
            a.prod_name
        ORDER BY total_revenue DESC
        LIMIT 10;
    """

    with conn.cursor() as cur:
        cur.execute(query)
        return cur.fetchall()


def compare_sample_data(original_conn, recovery_conn):
    sample_tables = [
        ("customer", "customer_id"),
        ("article", "article_id"),
        ("product", "product_code"),
    ]

    results = []

    original_tables = get_public_tables(original_conn)
    recovery_tables = get_public_tables(recovery_conn)

    for table_name, pk_column in sample_tables:
        if table_name not in original_tables or table_name not in recovery_tables:
            results.append((table_name, "SKIP", "Table not found"))
            continue

        query = f"""
            SELECT *
            FROM public."{table_name}"
            ORDER BY "{pk_column}"
            LIMIT 5;
        """

        try:
            with original_conn.cursor() as cur:
                cur.execute(query)
                original_rows = cur.fetchall()

            with recovery_conn.cursor() as cur:
                cur.execute(query)
                recovery_rows = cur.fetchall()

            if original_rows == recovery_rows:
                results.append((table_name, "PASS", "First 5 rows match"))
            else:
                results.append((table_name, "FAIL", "Sample rows differ"))

        except Exception as exc:
            results.append((table_name, "FAIL", str(exc)))

    return results


def verify():
    original_conn = None
    recovery_conn = None

    try:
        validate_environment()

        print("=" * 65)
        print("DATABASE RECOVERY VERIFICATION")
        print("=" * 65)
        print(f"Original DB : {DB_NAME}")
        print(f"Recovery DB : {RECOVERY_DB}")
        print()

        print("[0] DATABASE CONNECTION")
        print("-" * 65)

        original_conn = connect(DB_NAME)
        recovery_conn = connect(RECOVERY_DB)

        print("✓ Original database connected")
        print("✓ Recovery database connected")
        print()

        all_passed = True

        print("[1] TABLE EXISTENCE")
        print("-" * 65)

        original_tables = get_public_tables(original_conn)
        recovery_tables = get_public_tables(recovery_conn)

        for table_name in EXPECTED_TABLES:
            original_exists = table_name in original_tables
            recovery_exists = table_name in recovery_tables

            if original_exists and recovery_exists:
                print(f"✓ {table_name:<30} exists in both databases")
            elif not original_exists:
                print(f"⚠ {table_name:<30} not found in original DB")
            else:
                print(f"✗ {table_name:<30} missing in recovery DB")
                all_passed = False

        print()

        print("[2] ROW COUNT COMPARISON")
        print("-" * 65)

        common_tables = sorted(original_tables.intersection(recovery_tables))

        for table_name in common_tables:
            try:
                original_count = get_row_count(original_conn, table_name)
                recovery_count = get_row_count(recovery_conn, table_name)

                if original_count == recovery_count:
                    print(
                        f"✓ {table_name:<30} "
                        f"{original_count:,} = {recovery_count:,}"
                    )
                else:
                    print(
                        f"✗ {table_name:<30} "
                        f"{original_count:,} != {recovery_count:,}"
                    )
                    all_passed = False

            except Exception as exc:
                print(f"✗ {table_name:<30} ERROR: {exc}")
                all_passed = False

        print()

        print("[3] CONSTRAINT VERIFICATION")
        print("-" * 65)

        original_constraints = get_constraint_count(original_conn)
        recovery_constraints = get_constraint_count(recovery_conn)

        original_fks = get_foreign_key_count(original_conn)
        recovery_fks = get_foreign_key_count(recovery_conn)

        if original_constraints == recovery_constraints:
            print(
                f"✓ Total constraints: "
                f"{original_constraints} = {recovery_constraints}"
            )
        else:
            print(
                f"✗ Total constraints: "
                f"{original_constraints} != {recovery_constraints}"
            )
            all_passed = False

        if original_fks == recovery_fks:
            print(
                f"✓ Foreign keys: "
                f"{original_fks} = {recovery_fks}"
            )
        else:
            print(
                f"✗ Foreign keys: "
                f"{original_fks} != {recovery_fks}"
            )
            all_passed = False

        print()

        print("[4] CRITICAL DATA SAMPLE")
        print("-" * 65)

        sample_results = compare_sample_data(
            original_conn,
            recovery_conn
        )

        for table_name, status, message in sample_results:
            if status == "PASS":
                symbol = "✓"
            elif status == "SKIP":
                symbol = "⚠"
            else:
                symbol = "✗"

            print(f"{symbol} {table_name:<30} {message}")

            if status == "FAIL":
                all_passed = False

        print()

        print("[5] REPRESENTATIVE QUERY")
        print("-" * 65)

        try:
            original_rows = run_representative_query(original_conn)
            recovery_rows = run_representative_query(recovery_conn)

            print(
                f"✓ Original DB query executed "
                f"({len(original_rows)} rows returned)"
            )
            print(
                f"✓ Recovery DB query executed "
                f"({len(recovery_rows)} rows returned)"
            )

            if original_rows == recovery_rows:
                print("✓ Query results match")
            else:
                print("✗ Query executed, but returned results differ")
                all_passed = False

        except Exception as exc:
            print(f"✗ Representative query failed: {exc}")
            all_passed = False

        print()
        print("=" * 65)

        if all_passed:
            print("VERIFICATION RESULT: PASS")
            print("The recovery database passed all verification checks.")
        else:
            print("VERIFICATION RESULT: FAIL")
            print("One or more verification checks failed.")

        print("=" * 65)

        sys.exit(0 if all_passed else 1)

    except Exception as exc:
        print()
        print("=" * 65)
        print("VERIFICATION ERROR")
        print("=" * 65)
        print(exc)
        sys.exit(1)

    finally:
        if original_conn is not None:
            original_conn.close()

        if recovery_conn is not None:
            recovery_conn.close()
