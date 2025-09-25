import sqlite3
import pandas as pd
import os

DB_FILE = 'bookkeeping.db'
EXPORT_DIR = 'data_export'
OUTPUT_FILE = os.path.join(EXPORT_DIR, 'data_export.xlsx')

def export_database_to_excel():
    if not os.path.exists(DB_FILE):
        print(f"Error: Database file '{DB_FILE}' not found.")
        return

    if not os.path.exists(EXPORT_DIR):
        os.makedirs(EXPORT_DIR)

    conn = sqlite3.connect(DB_FILE)

    # Get a list of all tables
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()

    with pd.ExcelWriter(OUTPUT_FILE, engine='openpyxl') as writer:
        for table_name_tuple in tables:
            table_name = table_name_tuple[0]
            if table_name.startswith('alembic_') or table_name.startswith('sqlite_'):
                print(f"Skipping system table: {table_name}")
                continue

            print(f"Exporting table: {table_name}...")
            
            try:
                # Use pandas to read the SQL table into a DataFrame
                df = pd.read_sql_query(f'SELECT * FROM "{table_name}" ', conn)
                
                # Write the DataFrame to a sheet in the Excel file
                df.to_excel(writer, sheet_name=table_name, index=False)
                
                print(f" -> Successfully exported {len(df)} rows to sheet '{table_name}'")

            except Exception as e:
                print(f" -> An error occurred while exporting {table_name}: {e}")

    conn.close()
    print(f"\nExport complete. Data saved to {OUTPUT_FILE}")

if __name__ == '__main__':
    export_database_to_excel()