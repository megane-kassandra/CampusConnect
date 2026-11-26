# `facial_auth`

Application Django de reconnaissance faciale du microservice Auth. Elle s'intègre au projet `auth_service` (même processus, configuration et base) ; elle ne possède pas de modèle ni de base de données indépendante.

## Flux

- `FaceAuthentication.enroll(user, image_bytes)` indexe la photo de référence dans la collection AWS Rekognition avec l'identifiant du compte comme `ExternalImageId`.
- `FaceAuthentication.authenticate(frame_bytes)` vérifie localement la présence d'un visage avec OpenCV, puis utilise `SearchFacesByImage` pour l'identifier dans la collection.
- Le résultat contient un statut et, si trouvé, un `user_id` candidat. Cette app ne délivre pas de JWT : `AuthenticationService` reste seul responsable de terminer la connexion et d'émettre les jetons.
- La caméra de démonstration est `GET /api/auth/face/camera/`; son endpoint JSON est `POST /api/auth/face/recognize/` avec un champ multipart `frame`.

L'enrôlement est une méthode de la stratégie, afin que l'app `inscription` puisse l'appeler après avoir créé le compte. L'identifiant transmis est l'identifiant stable de l'utilisateur dans la base Auth. Les métadonnées et le chemin de la photo de référence sont gérés par `authentication.models.FaceCredential`, pas par un modèle parallèle dans `facial_auth`.

## Appel depuis la future app `connexion`

`connexion` et `facial_auth` sont deux apps du même projet Django. La vue de connexion appelle donc la stratégie directement avec les octets de la capture caméra, puis demande à `AuthenticationService` de finaliser l'authentification :

```python
from authentication.container import build_authentication_factory
from authentication.strategies.base import AuthMethod


def login_with_face(request):
    frame = request.FILES.get("frame")
    if frame is None:
        # Répondre avec une erreur HTTP 400.
        ...

    face_auth = build_authentication_factory().create(AuthMethod.FACE)
    result = face_auth.authenticate(frame.read())

    if result["status"] != "recognized":
        # no_face, multiple_faces ou unknown : refuser la connexion.
        ...

    user_id = result["user_id"]
    # Vérifier que le compte est toujours actif, puis appeler
    # AuthenticationService pour l'audit et l'émission du JWT.
    ...
```

La vue `connexion` peut recevoir la capture directement du navigateur, ou le frontend peut utiliser la caméra préparée ici. Les routes de cette app sont montées sous `/api/auth/face/` : `GET /api/auth/face/camera/` affiche la caméra de démonstration et son JavaScript envoie les frames à `POST /api/auth/face/recognize/` (multipart, champ `frame`). L'endpoint de démonstration renvoie un `user_id` candidat, mais n'émet pas de JWT. Pour connecter réellement l'utilisateur, la future app `connexion` doit finaliser elle-même le résultat avec `AuthenticationService`.

Pour l'enrôlement, l'app `inscription` appelle la stratégie après avoir créé le compte :

```python
from authentication.container import build_authentication_factory
from authentication.strategies.base import AuthMethod


face_auth = build_authentication_factory().create(AuthMethod.FACE)
face_auth.enroll(user, photo_de_reference.read())
```

## Configuration

Le projet parent configure `AWS_REGION`, `AWS_REKOGNITION_COLLECTION` et `FACE_MATCH_THRESHOLD`. Boto3 lit les clés depuis l'environnement ou un rôle IAM. Le rôle doit autoriser `rekognition:CreateCollection`, `rekognition:IndexFaces` et `rekognition:SearchFacesByImage`.

Créer la collection depuis la racine de `auth_service` :

```bash
uv run python manage.py setup_face_collection
```

La caméra du navigateur nécessite `localhost` ou HTTPS. Les images capturées sont envoyées en JPEG, traitées puis supprimées ; elles ne sont pas enregistrées par l'app. Une recherche AWS est faite toutes les 1,8 secondes tant qu'un visage unique est détecté.
