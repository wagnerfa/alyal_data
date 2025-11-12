"""
Migration script to add new columns to the Sale table.
Run this script ONCE to update the database schema.

Usage: python migrate_sales_table.py
"""

import sqlite3
import sys
from pathlib import Path

# Database path
DB_PATH = Path(__file__).parent / 'instance' / 'database.db'

# New columns to add
NEW_COLUMNS = [
    # Foreign key
    ("company_id", "INTEGER"),

    # Colunas de Dados do Pedido
    ("numero_pedido", "VARCHAR(100)"),
    ("titulo_anuncio", "VARCHAR(500)"),
    ("numero_anuncio", "VARCHAR(100)"),
    ("unidades", "INTEGER"),

    # Colunas de Cliente
    ("comprador", "VARCHAR(255)"),
    ("cpf_comprador", "VARCHAR(20)"),

    # Colunas Financeiras
    ("total_brl", "NUMERIC(12, 2)"),
    ("receita_produtos", "NUMERIC(12, 2)"),
    ("receita_acrescimo_preco", "NUMERIC(12, 2)"),
    ("taxa_parcelamento", "NUMERIC(12, 2)"),
    ("tarifa_venda_impostos", "NUMERIC(12, 2)"),
    ("receita_envio", "NUMERIC(12, 2)"),
    ("tarifas_envio", "NUMERIC(12, 2)"),
    ("custo_envio", "NUMERIC(12, 2)"),
    ("custo_diferencas_peso", "NUMERIC(12, 2)"),
    ("cancelamentos_reembolsos", "NUMERIC(12, 2)"),
    ("preco_unitario", "NUMERIC(12, 2)"),

    # Colunas Geográficas
    ("estado_comprador", "VARCHAR(50)"),
    ("cidade_comprador", "VARCHAR(100)"),

    # Colunas de Envio
    ("forma_entrega", "VARCHAR(100)"),

    # Colunas Calculadas/Derivadas
    ("lucro_liquido", "NUMERIC(12, 2)"),
    ("margem_percentual", "NUMERIC(5, 2)"),
    ("faixa_preco", "VARCHAR(50)"),
]

# Indexes to create for performance
INDEXES = [
    ("idx_sale_numero_pedido", "numero_pedido"),
    ("idx_sale_comprador", "comprador"),
    ("idx_sale_estado_comprador", "estado_comprador"),
    ("idx_sale_cidade_comprador", "cidade_comprador"),
    ("idx_sale_company_id", "company_id"),
]


def check_column_exists(cursor, table_name, column_name):
    """Check if a column already exists in the table."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns


def add_column_if_not_exists(cursor, table_name, column_name, column_type):
    """Add a column to the table if it doesn't exist."""
    if check_column_exists(cursor, table_name, column_name):
        print(f"  ✓ Column '{column_name}' already exists, skipping...")
        return False

    try:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
        print(f"  ✓ Added column '{column_name}' ({column_type})")
        return True
    except sqlite3.OperationalError as e:
        print(f"  ✗ Error adding column '{column_name}': {e}")
        return False


def create_index_if_not_exists(cursor, index_name, table_name, column_name):
    """Create an index if it doesn't exist."""
    try:
        cursor.execute(
            f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name}({column_name})"
        )
        print(f"  ✓ Created index '{index_name}' on column '{column_name}'")
        return True
    except sqlite3.OperationalError as e:
        print(f"  ✗ Error creating index '{index_name}': {e}")
        return False


def main():
    print("=" * 60)
    print("Sale Table Migration Script")
    print("=" * 60)

    # Check if database exists
    if not DB_PATH.exists():
        print(f"\n✗ Database not found at: {DB_PATH}")
        print("  Please run the application first to create the database.")
        sys.exit(1)

    print(f"\n✓ Database found at: {DB_PATH}")

    # Connect to database
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        print("✓ Connected to database")
    except sqlite3.Error as e:
        print(f"✗ Error connecting to database: {e}")
        sys.exit(1)

    # Backup reminder
    print("\n" + "!" * 60)
    print("IMPORTANT: Make sure you have a backup of your database!")
    print("!" * 60)
    response = input("\nContinue with migration? (yes/no): ")
    if response.lower() != 'yes':
        print("Migration cancelled.")
        conn.close()
        sys.exit(0)

    # Add new columns
    print("\n" + "-" * 60)
    print("Adding new columns to 'sale' table...")
    print("-" * 60)

    added_count = 0
    for column_name, column_type in NEW_COLUMNS:
        if add_column_if_not_exists(cursor, "sale", column_name, column_type):
            added_count += 1

    # Commit column changes
    conn.commit()
    print(f"\n✓ Added {added_count} new columns")

    # Create indexes
    print("\n" + "-" * 60)
    print("Creating indexes for performance...")
    print("-" * 60)

    index_count = 0
    for index_name, column_name in INDEXES:
        if create_index_if_not_exists(cursor, index_name, "sale", column_name):
            index_count += 1

    # Commit index changes
    conn.commit()
    print(f"\n✓ Created {index_count} indexes")

    # Show table structure
    print("\n" + "-" * 60)
    print("Current Sale table structure:")
    print("-" * 60)
    cursor.execute("PRAGMA table_info(sale)")
    columns = cursor.fetchall()
    print(f"\nTotal columns: {len(columns)}\n")
    for col in columns:
        print(f"  {col[1]:30} {col[2]:20} {'NOT NULL' if col[3] else ''}")

    # Close connection
    conn.close()
    print("\n" + "=" * 60)
    print("✓ Migration completed successfully!")
    print("=" * 60)
    print("\nYou can now restart your Flask application.")


if __name__ == "__main__":
    main()
