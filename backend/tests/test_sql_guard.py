from __future__ import annotations

import pytest

from app.core.errors import SqlForbiddenError
from app.core.sql_guard import validate_sql


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "SELECT * FROM t",
        "WITH x AS (SELECT 1) SELECT * FROM x",
        """
        WITH sample AS (
          SELECT 's1' AS session_id, 1 AS msg_idx, 'system' AS role, 'one' AS content
          UNION ALL SELECT 's1', 2, 'user', 'two'
          UNION ALL SELECT 's2', 1, 'assistant', 'three'
        )
        SELECT * FROM sample
        ORDER BY session_id, msg_idx
        """,
        "-- leading comment\nSeLeCt\n  *\nFROM t",
        "/* block comment */\nselect 1",
        "SELECT 'sleep' AS txt",
        "SELECT 'INTO OUTFILE' AS txt",
        "SELECT 'GET_LOCK(1)' AS txt",
        "SELECT 'FOR UPDATE' AS txt",
        "SELECT 'INTO @x' AS txt",
        "SELECT ':=' AS txt",
        "SELECT t.into FROM t",
        "SELECT db.t.into FROM db.t",
        "SELECT col AS into FROM t",
        "SELECT '/*!50000 SLEEP(1) */' AS txt",
        "SELECT 1 /* SLEEP(10) */",
    ],
)
def test_validate_sql_allows_select_and_with(sql: str) -> None:
    validate_sql(sql)


@pytest.mark.parametrize(
    "sql,statement_type",
    [
        ("UPDATE t SET x=1", "UPDATE"),
        ("DELETE FROM t", "DELETE"),
        ("DROP TABLE t", "DROP"),
        ("CREATE TABLE t (id int)", "CREATE"),
        ("WITH x AS (SELECT 1) DELETE FROM t", "DELETE"),
        ("WITH x AS (SELECT 1) UPDATE t SET x=1", "UPDATE"),
    ],
)
def test_validate_sql_rejects_non_select(sql: str, statement_type: str) -> None:
    with pytest.raises(SqlForbiddenError) as exc_info:
        validate_sql(sql)

    assert exc_info.value.code == "SQL_FORBIDDEN_STATEMENT"
    assert exc_info.value.detail == {"statement_type": statement_type}


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1; DELETE FROM t",
        "SELECT 1;SELECT 2",
    ],
)
def test_validate_sql_rejects_multiple_statements(sql: str) -> None:
    with pytest.raises(SqlForbiddenError) as exc_info:
        validate_sql(sql)

    assert exc_info.value.code == "SQL_FORBIDDEN_STATEMENT"
    assert exc_info.value.detail == {"statement_type": "MULTI_STATEMENT"}


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * INTO OUTFILE '/tmp/x' FROM t",
        "SELECT * INTO DUMPFILE '/tmp/x' FROM t",
        "SELECT * INTO/**/OUTFILE '/tmp/x' FROM t",
        "SELECT LOAD_FILE('/etc/passwd')",
        "SELECT SLEEP(10)",
        "SELECT SLEEP/**/(10)",
        "SELECT BENCHMARK(1000000, MD5('x'))",
        "SELECT GET_LOCK('agentlens', 30)",
        "SELECT RELEASE_LOCK('agentlens')",
        "SELECT RELEASE_ALL_LOCKS()",
        "SELECT WAIT_FOR_EXECUTED_GTID_SET('uuid:1', 10)",
        "SELECT MASTER_POS_WAIT('mysql-bin.000001', 10)",
        "SELECT SOURCE_POS_WAIT('mysql-bin.000001', 10)",
        "SELECT * INTO @x FROM t",
        "SELECT col INTO @x FROM t",
        "SELECT @x := 1",
        "SELECT (@x := id) FROM t",
        "SELECT * FROM t FOR UPDATE",
        "SELECT * FROM t FOR SHARE",
        "SELECT * FROM t LOCK IN SHARE MODE",
        "SELECT /*!50000 SLEEP(1) */ 1",
        "SELECT 1 /*!50000 + SLEEP(10) */",
        "SELECT 1 /*!50000 INTO OUTFILE '/tmp/x' */",
        "SELECT * INTO/*!50000 OUTFILE*/ '/tmp/x' FROM t",
        "SELECT /*+ MAX_EXECUTION_TIME(1000) */ 1",
    ],
)
def test_validate_sql_rejects_dangerous_keywords(sql: str) -> None:
    with pytest.raises(SqlForbiddenError) as exc_info:
        validate_sql(sql)

    assert exc_info.value.code == "SQL_DANGEROUS_FUNCTION"


@pytest.mark.parametrize("sql", ["", "   ", "-- only comment\n", "/* only */", ";", " ; ; "])
def test_validate_sql_rejects_empty_comment_or_semicolon_only(sql: str) -> None:
    with pytest.raises(SqlForbiddenError) as exc_info:
        validate_sql(sql)

    assert exc_info.value.code == "SQL_FORBIDDEN_STATEMENT"
    assert exc_info.value.detail == {"statement_type": "EMPTY"}
