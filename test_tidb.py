import os
import pymysql  # type: ignore[reportMissingModuleSource]
from dotenv import load_dotenv

load_dotenv()

conn = pymysql.connect(
    host=os.getenv("TIDB_HOST"),
    port=int(os.getenv("TIDB_PORT")),
    user=os.getenv("TIDB_USER"),
    password=os.getenv("TIDB_PASSWORD"),
    database=os.getenv("TIDB_DATABASE"),
    ssl={"ca": os.getenv("TIDB_CA_PATH")},
)
with conn.cursor() as cur:
    cur.execute("SELECT VERSION()")
    print("Terhubung ke TiDB:", cur.fetchone()[0])
conn.close()