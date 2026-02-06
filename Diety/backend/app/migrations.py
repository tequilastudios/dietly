from sqlalchemy import inspect, text

from .database import engine


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return False
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    return column_name in columns


def _add_column_if_missing(table_name: str, column_name: str, ddl_type: str) -> None:
    if _column_exists(table_name, column_name):
        return

    statement = text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl_type}")
    with engine.begin() as connection:
        connection.execute(statement)


def run_startup_migrations() -> None:
    # Lightweight schema drift handling for ai_settings in MVP setup without Alembic.
    table = "ai_settings"
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return
    _add_column_if_missing(table, "age_years", "INT NULL")
    _add_column_if_missing(table, "sex", "VARCHAR(32) NULL")
    _add_column_if_missing(table, "height_cm", "FLOAT NULL")
    _add_column_if_missing(table, "weight_kg", "FLOAT NULL")
    _add_column_if_missing(table, "target_weight_kg", "FLOAT NULL")
    _add_column_if_missing(table, "activity_level", "VARCHAR(32) NULL")
    _add_column_if_missing(table, "goals", "TEXT NULL")
    _add_column_if_missing(table, "dietary_preferences", "TEXT NULL")
    _add_column_if_missing(table, "allergies", "TEXT NULL")
    _add_column_if_missing(table, "response_language", "VARCHAR(16) NOT NULL DEFAULT 'it'")
    _add_column_if_missing(table, "system_prompt", "TEXT NULL")
    _add_column_if_missing(table, "reasoning_cycles", "INT NOT NULL DEFAULT 1")
    _add_column_if_missing(table, "smart_routine_enabled", "TINYINT(1) NOT NULL DEFAULT 0")
