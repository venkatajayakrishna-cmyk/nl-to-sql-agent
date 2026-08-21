import psycopg
from psycopg import sql
from langchain.tools import tool
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver


load_dotenv()  # Load environment variables from .env file

model = init_chat_model("google_genai:gemini-3.1-flash-lite")

SYSTEM_PROMPT = """
You are an agent designed to interact with a SQL database.
Given an input question, create a syntactically correct {dialect} query to run,
then look at the results of the query and return the answer. Unless the user
specifies a specific number of examples they wish to obtain, always limit your
query to at most {top_k} results.

You can order the results by a relevant column to return the most interesting
examples in the database. Never query for all the columns from a specific table,
only ask for the relevant columns given the question.

You MUST double check your query before executing it. If you get an error while
executing a query, rewrite the query and try again.

DO NOT make any DML statements (INSERT, UPDATE, DELETE, DROP etc.) to the
database.

To start you should ALWAYS look at the tables in the database to see what you
can query. Do NOT skip this step.

Then you should query the schema of the most relevant tables.
""".format(
    dialect="postgresql",
    top_k=5,
)


# PostgreSQL connection details
import os
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
}


def get_connection():
    return psycopg.connect(**DB_CONFIG)


@tool
def sql_db_list_tables() -> str:
    """Input is an empty string, output is a comma-separated list of tables in the database."""

    con = get_connection()

    try:
        cursor = con.cursor()

        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """)

        tables = [row[0] for row in cursor.fetchall()]

        return ", ".join(tables)

    finally:
        con.close()


@tool
def sql_db_schema(table_names: str) -> str:
    """Input is a comma-separated list of tables, output is the schema and sample rows.
    Be sure that the tables actually exist by calling sql_db_list_tables first.
    Example Input: table1, table2, table3
    """

    con = get_connection()

    try:
        cursor = con.cursor()

        # Get valid tables
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE';
        """)

        valid_tables = {row[0] for row in cursor.fetchall()}

        results = []

        for table in table_names.split(","):
            table = table.strip()

            if table not in valid_tables:
                results.append(
                    f"Error: table_names {{{table!r}}} not found in database"
                )
                continue

            # Get column information
            cursor.execute("""
                SELECT
                    column_name,
                    data_type,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s
                ORDER BY ordinal_position;
            """, (table,))

            columns = cursor.fetchall()

            schema = f"Table: {table}\n"

            for column in columns:
                column_name, data_type, nullable, default = column

                schema += (
                    f"  {column_name} {data_type}"
                    f" {'NULL' if nullable == 'YES' else 'NOT NULL'}"
                )

                if default:
                    schema += f" DEFAULT {default}"

                schema += "\n"

            results.append(schema)

            # Get sample rows
            try:
                query = sql.SQL(
                    "SELECT * FROM {} LIMIT 3"
                ).format(
                    sql.Identifier(table)
                )

                cursor.execute(query)

                rows = cursor.fetchall()

                if rows:
                    col_names = [
                        description.name
                        for description in cursor.description
                    ]

                    sample = (
                        f"/*\n"
                        f"3 rows from {table} table:\n"
                        + "\t".join(col_names)
                        + "\n"
                        + "\n".join(
                            "\t".join(str(x) for x in row)
                            for row in rows
                        )
                        + "\n*/"
                    )

                    results.append(sample)

            except Exception as e:
                results.append(
                    f"Error fetching sample rows: {e}"
                )

        return "\n\n".join(results)

    finally:
        con.close()


@tool
def sql_db_query(query: str) -> str:
    """Input is a detailed and correct PostgreSQL SQL query.
    Output is the result from the database.

    If the query is not correct, an error message will be returned.
    If an error is returned, rewrite the query, check the query,
    and try again.
    """

    con = get_connection()

    try:
        cursor = con.cursor()

        cursor.execute(query)

        res = cursor.fetchall()

        return str(res)

    except Exception as e:
        return f"Error: {e}"

    finally:
        con.close()


@tool
def sql_db_query_checker(query: str) -> str:
    """Use this tool to double check if your PostgreSQL query is correct
    before executing it with sql_db_query.

    Always use this tool before executing a query with sql_db_query.
    """

    trigger_prompt = f"""
{query}

Double check the PostgreSQL query above for common mistakes, including:

- Using NOT IN with NULL values
- Using UNION when UNION ALL should have been used
- Using BETWEEN for exclusive ranges
- Data type mismatch in predicates
- Properly quoting identifiers
- Using the correct number of arguments for functions
- Casting to the correct data type
- Using the proper columns for joins
- PostgreSQL-specific syntax
- Correct table and column names

If there are any mistakes, rewrite the query.

If there are no mistakes, reproduce the original query.

Output the final SQL query only.

SQL Query:
"""

    response = model.invoke(trigger_prompt)

    return response.text.strip()


tools = [
    sql_db_list_tables,
    sql_db_schema,
    sql_db_query,
    sql_db_query_checker,
]


for t in tools:
    print(f"{t.name}: {t.description}\n")




agent = create_agent(
    model,
    tools,
    system_prompt=SYSTEM_PROMPT,
    checkpointer=InMemorySaver()
)