import sqlite3

def upgrade_database():
    conn = sqlite3.connect("donors.db")
    c = conn.cursor()

    # Check donors table columns
    c.execute("PRAGMA table_info(donors)")
    existing_cols = [row[1] for row in c.fetchall()]

    new_cols = [
        ("age", "INTEGER DEFAULT 28"),
        ("gender", "TEXT DEFAULT 'Not Specified'"),
        ("status", "TEXT DEFAULT 'Available'"),
        ("last_donated", "TEXT DEFAULT ''"),
        ("total_donations", "INTEGER DEFAULT 1")
    ]

    for col_name, col_def in new_cols:
        if col_name not in existing_cols:
            c.execute(f"ALTER TABLE donors ADD COLUMN {col_name} {col_def}")
            print(f"Added column {col_name} to donors")

    # Uppercase existing blood groups for consistency
    c.execute("UPDATE donors SET blood = UPPER(TRIM(blood))")

    # Create blood_requests table
    c.execute("""
    CREATE TABLE IF NOT EXISTS blood_requests(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_name TEXT NOT NULL,
        blood_group TEXT NOT NULL,
        units INTEGER NOT NULL DEFAULT 1,
        hospital TEXT NOT NULL,
        city TEXT NOT NULL,
        contact_phone TEXT NOT NULL,
        urgency TEXT NOT NULL DEFAULT 'Urgent',
        status TEXT NOT NULL DEFAULT 'Pending',
        notes TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Check users table columns
    c.execute("PRAGMA table_info(users)")
    user_cols = [row[1] for row in c.fetchall()]
    if "role" not in user_cols:
        c.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'admin'")
        print("Added role column to users")

    conn.commit()

    # Check data
    rows = c.execute("SELECT * FROM donors").fetchall()
    print("Database upgrade complete! Total donors:", len(rows))
    for r in rows:
        print("Donor:", r)

    conn.close()

if __name__ == "__main__":
    upgrade_database()
