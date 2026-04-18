import os
import pymysql
from dotenv import load_dotenv

load_dotenv()

# Connect without DB to create it
conn = pymysql.connect(
    host=os.environ.get('MYSQL_HOST', 'localhost'),
    user=os.environ.get('MYSQL_USER', 'root'),
    password=os.environ.get('MYSQL_PASSWORD', 'root@123'),
    port=int(os.environ.get('MYSQL_PORT', 3306)),
    autocommit=True
)

db_name = os.environ.get('MYSQL_DB', 'unicred')

with conn.cursor() as cursor:
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")

conn.close()

# Connect to the DB to run schema
conn = pymysql.connect(
    host=os.environ.get('MYSQL_HOST', 'localhost'),
    user=os.environ.get('MYSQL_USER', 'root'),
    password=os.environ.get('MYSQL_PASSWORD', 'root@123'),
    db=db_name,
    port=int(os.environ.get('MYSQL_PORT', 3306)),
    autocommit=True
)

# Load schema.sql and execute
with open('schema.sql', 'r', encoding='utf-8') as f:
    sql_script = f.read()

# Execute each statement
# Split by ';' but avoid empty statements
statements = [s.strip() for s in sql_script.split(';') if s.strip()]

with conn.cursor() as cursor:
    for statement in statements:
        try:
            cursor.execute(statement)
        except Exception as e:
            print(f"Error executing statement:\\n{statement}\\n{e}")

conn.close()
print("Database initialized successfully.")
