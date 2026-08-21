import chromadb

client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection(name="schema_descriptions")

# Manually written descriptions of your table(s) — this is the RAG "documents"
schema_docs = [
    {
        "id": "covid_data_table",
        "text": (
            "Table: covid_data. Contains daily cumulative COVID-19 case data "
            "per country/province, including columns: observationdate (date), "
            "province_state, country_region, confirmed (cumulative total cases), "
            "deaths (cumulative deaths), recovered (cumulative recoveries). "
            "Note: values are running totals per day, not daily new cases."
        ),
    },
]

def build_schema_index():
    collection.upsert(
        ids=[doc["id"] for doc in schema_docs],
        documents=[doc["text"] for doc in schema_docs],
    )

if __name__ == "__main__":
    build_schema_index()