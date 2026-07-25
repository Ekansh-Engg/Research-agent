import asyncio

from agent.tools.sql_query import sql_query


async def main():
    print("Safe query:")
    print(await sql_query("SELECT status, COUNT(*) FROM agent_runs GROUP BY status"))

    print("\nUnsafe query (should be rejected):")
    print(await sql_query("DELETE FROM agent_runs"))

    print("\nUnsafe query with stacked statement (should be rejected):")
    print(await sql_query("SELECT * FROM agent_runs; DROP TABLE agent_runs;"))


if __name__ == "__main__":
    asyncio.run(main())