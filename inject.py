import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv

load_dotenv()


def main():
    password = os.getenv("DB_PASSWORD")


    df = pd.read_csv("data/covid_19_data.csv")
    df.columns = [c.strip().replace('/', '_').replace(' ', '_') for c in df.columns]

    engine = create_engine(f"postgresql://postgres:{password}@localhost:5432/covid_db")

    df.to_sql("covid_data", engine, if_exists="replace", index=False)
    print("Loaded succesfully")


if __name__ == "__main__":
    main()
