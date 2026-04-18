import pymysql
from config import Config

def patch_db():
    conn = pymysql.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB,
        cursorclass=pymysql.cursors.DictCursor
    )
    try:
        with conn.cursor() as cursor:
            # Ensure the columns allow NULL explicitly
            cursor.execute("ALTER TABLE resources MODIFY available_from DATE NULL;")
            cursor.execute("ALTER TABLE resources MODIFY available_until DATE NULL;")
        conn.commit()
        print("Database patched successfully.")
    except Exception as e:
        print(f"Error patching database: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    patch_db()
