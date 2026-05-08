from __future__ import annotations

from collections.abc import Sequence
from typing import cast

import sqlparse
from sqlparse import tokens
from sqlparse.sql import Statement

from app.core.errors import SqlForbiddenError

_ALLOWED_STATEMENT_TYPES = frozenset({"SELECT"})
_OUTER_STATEMENT_KEYWORDS = frozenset(
    {
        "ALTER",
        "CREATE",
        "DELETE",
        "DROP",
        "INSERT",
        "REPLACE",
        "SELECT",
        "TRUNCATE",
        "UPDATE",
    }
)
_DANGEROUS_FUNCTIONS = frozenset(
    {
        "BENCHMARK",
        "GET_LOCK",
        "LOAD_FILE",
        "MASTER_POS_WAIT",
        "RELEASE_ALL_LOCKS",
        "RELEASE_LOCK",
        "SLEEP",
        "SOURCE_POS_WAIT",
        "WAIT_FOR_EXECUTED_GTID_SET",
        "WAIT_UNTIL_SQL_THREAD_AFTER_GTIDS",
    }
)
_LOCKING_READ_CLAUSES = (
    ("FOR", "UPDATE"),
    ("FOR", "SHARE"),
    ("LOCK", "IN", "SHARE", "MODE"),
)
_MYSQL_EXECUTABLE_COMMENT_PREFIXES = ("/*!", "/*+")


def validate_sql(sql: str) -> None:
    parsed_statements = list(sqlparse.parse(sql))
    executable_comment = _find_mysql_executable_comment(parsed_statements)
    if executable_comment is not None:
        raise SqlForbiddenError(
            code="SQL_DANGEROUS_FUNCTION",
            message="MySQL executable comments and optimizer hints are not allowed.",
            detail={"keyword": executable_comment},
        )

    statements = [statement for statement in parsed_statements if _has_effective_tokens(statement)]
    dangerous_keyword = _find_dangerous_keyword(statements)
    if dangerous_keyword is not None:
        raise SqlForbiddenError(
            code="SQL_DANGEROUS_FUNCTION",
            message="Dangerous SQL function or export operation is not allowed.",
            detail={"keyword": dangerous_keyword},
        )

    if len(statements) != 1:
        raise SqlForbiddenError(
            code="SQL_FORBIDDEN_STATEMENT",
            detail={"statement_type": "EMPTY" if not statements else "MULTI_STATEMENT"},
        )

    statement = statements[0]
    statement_type = cast(str, statement.get_type()).upper()  # type: ignore[no-untyped-call]
    first_keyword = _first_effective_keyword(statement)
    if statement_type in _ALLOWED_STATEMENT_TYPES:
        return
    if first_keyword == "WITH" and _outer_keyword_after_with(statement) == "SELECT":
        return

    raise SqlForbiddenError(
        code="SQL_FORBIDDEN_STATEMENT",
        detail={"statement_type": statement_type},
    )


def _has_effective_tokens(statement: Statement) -> bool:
    return _first_effective_keyword(statement) is not None


def _first_effective_keyword(statement: Statement) -> str | None:
    for token_value in _effective_token_values(statement):
        return token_value
    return None


def _outer_keyword_after_with(statement: Statement) -> str | None:
    seen_with = False
    depth = 0
    for token in statement.flatten():  # type: ignore[no-untyped-call]
        if token.is_whitespace or token.ttype in tokens.Comment:
            continue
        if token.ttype is tokens.Punctuation and token.value == ";":
            continue

        token_value = str(token.value).upper()
        if not seen_with:
            seen_with = token_value == "WITH"
            continue
        if token.ttype is tokens.Punctuation:
            if token.value == "(":
                depth += 1
            elif token.value == ")":
                depth = max(0, depth - 1)
            continue
        if depth > 0 or token_value == "RECURSIVE":
            continue
        if token_value in _OUTER_STATEMENT_KEYWORDS:
            return token_value
    return None


def _find_mysql_executable_comment(statements: Sequence[Statement]) -> str | None:
    for statement in statements:
        for token in statement.flatten():  # type: ignore[no-untyped-call]
            if token.ttype not in tokens.Comment:
                continue
            token_value = str(token.value).lstrip()
            if token_value.startswith(_MYSQL_EXECUTABLE_COMMENT_PREFIXES):
                return "MYSQL_EXECUTABLE_COMMENT"
    return None


def _find_dangerous_keyword(statements: Sequence[Statement]) -> str | None:
    for statement in statements:
        values = _effective_token_values(statement)
        for index, token_value in enumerate(values):
            previous_value = values[index - 1] if index > 0 else None
            next_value = values[index + 1] if index + 1 < len(values) else None
            if token_value == ":=":
                return "ASSIGNMENT"
            if token_value == "INTO" and previous_value not in {".", "AS"}:
                return "INTO"
            if token_value in _DANGEROUS_FUNCTIONS and next_value == "(":
                return token_value
            for clause in _LOCKING_READ_CLAUSES:
                if _tokens_start_with(values, index, clause):
                    return " ".join(clause)
    return None


def _tokens_start_with(values: Sequence[str], index: int, expected: Sequence[str]) -> bool:
    return tuple(values[index : index + len(expected)]) == tuple(expected)


def _effective_token_values(statement: Statement) -> list[str]:
    values: list[str] = []
    for token in statement.flatten():  # type: ignore[no-untyped-call]
        if token.is_whitespace or token.ttype in tokens.Comment:
            continue
        if token.ttype is tokens.Punctuation and token.value == ";":
            continue
        values.append(str(token.value).upper())
    return values
