import os
import sys
import mysql.connector
from dotenv import load_dotenv

def check_environment():
    print("--- Starting Deployment Pre-Flight Check ---")

    # 1. Check .env
    if not os.path.exists('.env'):
        print("[FAIL] .env file not found.")
        return False
    load_dotenv()
    print("[PASS] .env file found.")

    # 2. Check Database Connection
    db_host = os.environ.get('DB_HOST')
    db_user = os.environ.get('DB_USER')
    db_name = os.environ.get('DB_NAME')

    if not all([db_host, db_user, db_name]):
        print("[FAIL] Missing DB config in .env")
        return False

    try:
        conn = mysql.connector.connect(
            host=db_host, user=db_user,
            password=os.environ.get('DB_PASSWORD'), database=db_name,
            connection_timeout=5
        )
        conn.close()
        print(f"[PASS] Successfully connected to database '{db_name}' at '{db_host}'.")
    except Exception as e:
        print(f"[FAIL] Database connection failed: {e}")
        return False

    # 3. Check Dependencies (Imports)
    required_modules = ['flask', 'yfinance', 'pandas', 'sklearn', 'scipy', 'dotenv']
    missing_modules = []
    for mod in required_modules:
        try:
            __import__(mod)
        except ImportError:
            missing_modules.append(mod)

    if missing_modules:
        print(f"[FAIL] Missing Python modules: {', '.join(missing_modules)}")
        return False
    print("[PASS] All critical Python modules importable.")

    # 4. Check Directories
    dirs = ['static', 'templates']
    for d in dirs:
        if not os.path.isdir(d):
            print(f"[FAIL] Directory '{d}' missing.")
            return False
    print("[PASS] Static directories present.")

    print("\n[SUCCESS] Environment looks ready for deployment!")
    return True

if __name__ == "__main__":
    if not check_environment():
        sys.exit(1)
