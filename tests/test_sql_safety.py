"""
Tests for agent/tools/sql_query.py's application-level safety gate.

These deliberately never touch a real database -- is_safe_select() is a pure
function, and sql_query() rejects unsafe input BEFORE attempting any DB
connection, so we can verify the whole rejection path with zero infrastructure.
The database-level readonly_agent role (Day 18) is the second, independent
layer of defense and isn't something a unit test can meaningfully verify --
that one is inherently an integration-level guarantee.
"""

import pytest

from agent.tools.sql_query import is_safe_select, sql_query


class TestIsSafeSelect:
    def test_accepts_simple_select(self):
        assert is_safe_select("SELECT * FROM agent_runs") is True

    def test_accepts_select_with_trailing_semicolon(self):
        assert is_safe_select("SELECT id FROM agent_runs;") is True

    def test_accepts_select_case_insensitively(self):
        assert is_safe_select("select id from agent_runs") is True

    def test_rejects_delete(self):
        assert is_safe_select("DELETE FROM agent_runs") is False

    def test_rejects_update(self):
        assert is_safe_select("UPDATE agent_runs SET status = 'FAILED'") is False

    def test_rejects_drop_table(self):
        assert is_safe_select("DROP TABLE agent_runs") is False

    def test_rejects_insert(self):
        assert is_safe_select("INSERT INTO agent_runs (query) VALUES ('x')") is False

    def test_rejects_grant(self):
        assert is_safe_select("GRANT ALL ON agent_runs TO someone") is False

    def test_rejects_stacked_statement_after_select(self):
        # A single string trying to smuggle a second statement in after a
        # legitimate-looking SELECT -- this is the classic injection shape.
        assert is_safe_select("SELECT * FROM agent_runs; DROP TABLE agent_runs;") is False

    def test_rejects_forbidden_keyword_inside_a_subquery(self):
        # The keyword doesn't have to be the first word to be dangerous --
        # is_safe_select scans the whole string, not just the prefix.
        sql = "SELECT * FROM agent_runs WHERE id IN (DELETE FROM users RETURNING id)"
        assert is_safe_select(sql) is False

    def test_rejects_non_select_statement_entirely(self):
        assert is_safe_select("EXPLAIN SELECT * FROM agent_runs") is False

    def test_rejects_empty_string(self):
        assert is_safe_select("") is False

    def test_column_name_containing_a_keyword_substring_does_not_false_positive(self):
        # "updated_at" genuinely contains "UPDATE" as its literal prefix --
        # word-boundary matching must recognize that "update" glued directly
        # to "d_at" isn't a standalone UPDATE keyword, and let this through.
        assert is_safe_select("SELECT updated_at FROM agent_runs") is True
        assert is_safe_select("SELECT created_at FROM agent_runs") is True


class TestSqlQueryRejection:
    """
    sql_query() itself, specifically the path where unsafe input never
    reaches the database at all. No DB connection is mocked here on purpose --
    if is_safe_select() correctly gates the call, execution never gets far
    enough to need one.
    """

    @pytest.mark.asyncio
    async def test_delete_is_rejected_before_any_db_call(self):
        result = await sql_query("DELETE FROM agent_runs")
        assert "rejected" in result
        assert "DELETE FROM agent_runs" in result

    @pytest.mark.asyncio
    async def test_stacked_statement_is_rejected_before_any_db_call(self):
        result = await sql_query("SELECT * FROM agent_runs; DROP TABLE agent_runs;")
        assert "rejected" in result
