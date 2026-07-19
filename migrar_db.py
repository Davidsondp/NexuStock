import sqlite3

conexion = sqlite3.connect(
    "instance/optistock.db"
)

cursor = conexion.cursor()

try:

    cursor.execute("""
        ALTER TABLE movimiento
        ADD COLUMN usuario_id INTEGER
    """)

    print(
        "✅ Columna usuario_id agregada"
    )

except Exception as e:

    print(
        "⚠️ usuario_id:",
        e
    )

conexion.commit()
conexion.close()

print(
    "✅ Migración terminada"
)