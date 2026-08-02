from app import app
from models import Usuario

print("=== Inicio del script ===")

with app.app_context():

    usuarios = Usuario.query.all()

    print("Cantidad de usuarios:", len(usuarios))

    for u in usuarios:
        print(
            u.id,
            u.nombre,
            u.email,
            u.rol
        )

print("=== Fin del script ===")