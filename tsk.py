from app import db, app  # Import the Flask app
from models import Project
from sqlalchemy import text  # Import text for raw SQL queries

def migrate():
    # Push the application context
    with app.app_context():
        # Check if the 'duely_signed_forms' column exists
        with db.engine.connect() as connection:
            result = connection.execute(
                text("PRAGMA table_info(project);")
            )
            columns = [row[1] for row in result]  # Access column names using index 1
            column_exists = "duely_signed_forms" in columns

        # If the column doesn't exist, add it
        if not column_exists:
            with db.engine.connect() as connection:
                connection.execute(
                    text("ALTER TABLE project ADD COLUMN duely_signed_forms TEXT;")
                )
            print("Migration completed: 'duely_signed_forms' column added.")
        else:
            print("Migration skipped: 'duely_signed_forms' column already exists.")

if __name__ == "__main__":
    migrate()