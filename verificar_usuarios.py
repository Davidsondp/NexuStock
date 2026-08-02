from app import app
from models import Usuario


with app.app_context():

    usuarios = Usuario.query.all()

    print("Usuarios encontrados:", len(usuarios))

    for u in usuarios:
        print(
            u.id,
            u.email,
            u.rol
        )