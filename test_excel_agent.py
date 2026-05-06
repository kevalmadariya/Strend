# -*- coding: utf-8 -*-
"""Quick import check for all new Excel Agent modules."""
import sys
import os
os.environ["PYTHONIOENCODING"] = "utf-8"
errors = []

# 1. Core
try:
    from src.core.sqlite_manager import create_temp_db, get_connection, destroy_temp_db
    print("[OK] core/sqlite_manager")
except Exception as e:
    errors.append(f"[FAIL] core/sqlite_manager: {e}")
    print(errors[-1])

# 2. Utils
try:
    from src.utils.excel_agent.excel_parser import parse_excel_json, normalize_column_name
    print("[OK] utils/excel_parser")
except Exception as e:
    errors.append(f"[FAIL] utils/excel_parser: {e}")
    print(errors[-1])

try:
    from src.utils.excel_agent.schema_ops import infer_column_types, create_table, bulk_insert
    print("[OK] utils/schema_ops")
except Exception as e:
    errors.append(f"[FAIL] utils/schema_ops: {e}")
    print(errors[-1])

try:
    from src.utils.excel_agent.validate_query import validate_query, sanitize_table_name
    print("[OK] utils/validate_query")
except Exception as e:
    errors.append(f"[FAIL] utils/validate_query: {e}")
    print(errors[-1])

try:
    from src.utils.excel_agent.query_executor import execute_read_query, format_result_as_json
    print("[OK] utils/query_executor")
except Exception as e:
    errors.append(f"[FAIL] utils/query_executor: {e}")
    print(errors[-1])

try:
    from src.utils.excel_agent.query_builder import build_sql_from_query
    print("[OK] utils/query_builder")
except Exception as e:
    errors.append(f"[FAIL] utils/query_builder: {e}")
    print(errors[-1])

# 3. Quick functional tests
try:
    assert normalize_column_name("Stock Price (%)") == "stock_price_pct"
    assert normalize_column_name("52W High") == "_52w_high"
    print("[OK] column normalization")
except Exception as e:
    errors.append(f"[FAIL] column normalization: {e}")
    print(errors[-1])

try:
    ok, err = validate_query("SELECT * FROM test")
    assert ok and err is None
    ok, err = validate_query("DROP TABLE test")
    assert not ok
    ok, err = validate_query("SELECT 1; DROP TABLE test")
    assert not ok
    ok, err = validate_query("ALTER TABLE t ADD COLUMN x TEXT")
    assert ok
    ok, err = validate_query("ALTER TABLE t DROP COLUMN x")
    assert not ok
    print("[OK] query validation")
except Exception as e:
    errors.append(f"[FAIL] query validation: {e}")
    print(errors[-1])

try:
    conn = create_temp_db("import_test_123")
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    destroy_temp_db("import_test_123")
    print("[OK] sqlite lifecycle")
except Exception as e:
    errors.append(f"[FAIL] sqlite lifecycle: {e}")
    print(errors[-1])

try:
    data = {"file": [{"Ticker": "AAPL", "Price": 150.5}, {"Ticker": "GOOG", "Price": 2800}]}
    cols, rows = parse_excel_json(data)
    assert cols == ["ticker", "price"]
    assert len(rows) == 2
    assert rows[0]["ticker"] == "AAPL"
    print("[OK] excel parser")
except Exception as e:
    errors.append(f"[FAIL] excel parser: {e}")
    print(errors[-1])

try:
    rows = [{"name": "AAPL", "price": 150.5, "volume": 1000}]
    schema = infer_column_types(rows)
    assert schema["name"] == "TEXT"
    assert schema["price"] == "REAL"
    assert schema["volume"] == "INTEGER"
    print("[OK] schema inference")
except Exception as e:
    errors.append(f"[FAIL] schema inference: {e}")
    print(errors[-1])

# 4. Integration test: parse -> infer -> create -> insert -> query
try:
    conn = create_temp_db("integration_test")
    data = {"file": [
        {"Symbol": "AAPL", "Price": 150.5, "Volume": 1000000},
        {"Symbol": "GOOG", "Price": 2800.0, "Volume": 500000},
        {"Symbol": "TSLA", "Price": 700.0, "Volume": 2000000},
    ]}
    cols, rows = parse_excel_json(data)
    schema = infer_column_types(rows[:2])
    create_table(conn, "excel_data", schema)
    count = bulk_insert(conn, "excel_data", rows)
    assert count == 3
    
    result = execute_read_query(conn, "SELECT * FROM excel_data WHERE price > 500")
    assert len(result) == 2  # GOOG and TSLA
    
    json_str = format_result_as_json(result)
    import json
    parsed = json.loads(json_str)
    assert len(parsed) == 2
    
    destroy_temp_db("integration_test")
    print("[OK] integration test (parse->infer->create->insert->query)")
except Exception as e:
    errors.append(f"[FAIL] integration test: {e}")
    print(errors[-1])

print(f"\n{'='*40}")
if errors:
    print(f"FAILED: {len(errors)} errors")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print("ALL CHECKS PASSED")
