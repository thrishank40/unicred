import pymysql
import pymysql.cursors
from config import Config

def get_db():
    """Get a new database connection."""
    conn = pymysql.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        db=Config.MYSQL_DB,
        port=Config.MYSQL_PORT,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False
    )
    return conn

def query_db(sql, args=(), one=False, commit=False):
    """Execute a query and return results."""
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, args)
            if commit:
                conn.commit()
                return cursor.lastrowid
            rv = cursor.fetchall()
            return (rv[0] if rv else None) if one else rv
    except Exception as e:
        if commit:
            conn.rollback()
        raise e
    finally:
        conn.close()

def execute_db(sql, args=(), get_id=False):
    """Execute an INSERT/UPDATE/DELETE and optionally return last insert id."""
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, args)
        conn.commit()
        if get_id:
            return cursor.lastrowid
        return cursor.rowcount
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
