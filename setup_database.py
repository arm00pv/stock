from app import init_db, initial_populate_db

def main():
    """
    Runs the initial database setup.
    This should be run once when deploying the application for the first time.
    """
    print("--- Running Database Setup ---")

    print("\nStep 1: Initializing database schema (creating tables)...")
    init_db()
    print("Schema initialization complete.")

    print("\nStep 2: Populating database with starter ticker lists...")
    initial_populate_db()
    print("Starter data population complete.")

    print("\n--- Database Setup Finished ---")

if __name__ == '__main__':
    main()
