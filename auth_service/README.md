# Auth Service — CampusConnect

Microservice d'authentification multi-méthodes du projet **CampusConnect** (TP 4057).
Implémentation Django + DRF, conforme au **cahier de conception v2.0** (section 5 :
patron Factory + Strategy).

---

## 1. Rôle dans l'architecture

Le service a pour objectif de gérer :

- l'**inscription par étapes** (identifiants + empreinte WebAuthn + enrôlement du visage) ;
- la **génération du QR code** personnel (jeton opaque signé, révocable) ;
- la **connexion multi-méthodes** : mot de passe, empreinte, visage ;
- l'émission et la révocation des **JWT** (access 15 min, refresh 7 jours avec rotation) ;
- la **journalisation d'audit** de tous les événements d'authentification.

Dans l’architecture cible, le service n’expose pas ses tables aux autres microservices. La reconnaissance faciale utilise néanmoins AWS Rekognition. Les autres microservices devront valider le JWT localement (HS256 pour la démo, RS256 + JWKS en production).

```text
[Frontend] → [API Gateway] → [Auth Service :8081] → [auth_db]
                                    ↑
                          (validation JWT locale)
                                    ↑
                       [Student] [Course] [Enrollment] ...
```

---

## 2. Stack technique

| Couche | Choix |
|---|---|
| Langage | Python 3.12 |
| Framework | Django + Django REST Framework |
| Base de données | PostgreSQL (`auth_db`) ; SQLite pour les tests locaux si configuré |
| Gestionnaire de paquets | **uv** (avec `requirements.txt` de secours pour pip) |
| Authentification | Sessions Django et stratégies biométriques de démo ; JWT HS256 / RS256 + JWKS prévus |
| Biométrie | WebAuthn (empreinte), index facial 1:N dans AWS Rekognition |
| Conteneurisation | Docker (prévu) |
| Configuration | `.env` en local ; Spring Cloud Config Server (intégration cible) |

**Conforme au cahier des charges** : Java 17/Spring Boot imposés pour les autres services,
**dérogation documentée** (D1 du cahier v2.0) pour Auth en Python — validée par l'enseignant.

---

## 3. Architecture interne (Factory + Strategy)

Le cahier v2.0 (section 5) impose le patron **Factory + Strategy**. Concrètement :

```text
authentication/                    ← app Django "cœur" (domaine auth)
├── strategies/
│   ├── base.py                    ← ABC Authentication + Enrollable + AuthMethod
│   ├── password.py                ← PasswordAuthentication
│   └── qr.py                      ← QRAuthentication
├── factories/
│   └── authentication_factory.py  ← registre AuthMethod → Authentication
├── services/
│   ├── authentication_service.py  ← SEUL à émettre des jetons, écrire l'audit
│   └── token_service.py
├── models.py                      ← User, FaceCredential et modèles WebAuthn (données centrales)
├── domain/exceptions.py
└── container.py                   ← SEULE racine de composition

facial_auth/                       ← app Django "stratégie visage"
├── strategy.py                    ← FaceAuthentication(Authentication, Enrollable)
├── rekognition.py                 ← détection OpenCV + enrôlement/recherche AWS 1:N
├── views.py / urls.py             ← caméra de démo et endpoint de reconnaissance
└── templates/ + static/           ← capture périodique webcam

fingerprint_auth/                  ← app Django "stratégie empreinte"
├── strategy.py                    ← FingerprintAuthentication(Authentication, Enrollable)
├── webauthn_service.py            ← challenges, enrôlement et vérification WebAuthn
├── serializers.py                 ← validation des requêtes
├── views.py / urls.py             ← API WebAuthn et interface de démonstration
├── templates/ + static/           ← interface navigateur et JavaScript WebAuthn
├── tests.py                       ← tests de logique et de sécurité
└── README.md                      ← documentation du module
```

### Règles de dépendance (à respecter impérativement)

1. **`facial_auth` et `fingerprint_auth` importent depuis `authentication`**, jamais l'inverse.
2. **`container.py` est le SEUL fichier qui importe les 3 apps** — c'est la racine de composition.
3. La Factory **ne connaît pas** les apps externes : elle reçoit un `Dict[AuthMethod, Callable]` déjà peuplé par `container.py`.
4. **Aucun modèle biométrique indépendant** dans `facial_auth` / `fingerprint_auth` (les modèles restent dans `authentication/models.py` ; `fingerprint_auth/models.py` ne définit pas de modèle).
5. Ajouter une méthode = **(a)** une valeur dans `AuthMethod`, **(b)** une stratégie dans l'app correspondante, **(c)** une ligne dans `container.py`, **(d)** ses tests.

---

## 4. Prérequis

- **Python 3.12** (`python3.12 --version`)
- **uv** (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **PostgreSQL 15+** avec une base `auth_db`, ou SQLite pour les tests locaux si `DB_ENGINE=sqlite` est pris en charge
- Navigateur compatible WebAuthn ; webcam et accès Internet pour le module facial
- **Git**

> Pour les coéquipiers qui préfèrent **pip** : un `requirements.txt` est fourni, généré
> depuis `uv.lock` avec `uv export --format requirements.txt`. Aucune incompatibilité.

---

## 5. Installation

### Avec uv (recommandé — 10× plus rapide)

```bash
git clone <repo-url> CampusConnect
cd CampusConnect/auth_service

# Installe Python 3.12 si absent + toutes les dépendances depuis uv.lock
uv sync
```

### Avec pip (pour les coéquipiers sans uv)

```bash
cd auth_service
python3.12 -m venv .venv
source .venv/bin/activate

# Installe exactement les versions du lockfile
pip install -r requirements.txt
```

---

## 6. Configuration

### Variables d'environnement (`.env` à la racine de `auth_service/`)

Créer un fichier `.env` (jamais commité — protégé par `.gitignore`) :

```bash
# Django
DJANGO_SECRET_KEY=changez-moi-en-production
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# Base de données
DB_NAME=auth_db
DB_USER=auth_user
DB_PASSWORD=changez-moi
DB_HOST=localhost
DB_PORT=5434

# JWT (HS256 démo — 32 caractères minimum)
JWT_SECRET=changez-moi-32-caracteres-minimum
JWT_ACCESS_TTL_MINUTES=15
JWT_REFRESH_TTL_DAYS=7

# WebAuthn (empreinte / passkey)
WEBAUTHN_RP_ID=localhost
WEBAUTHN_ORIGIN=http://localhost:8081
WEBAUTHN_DEMO_ENABLED=true

# AWS Rekognition (reconnaissance faciale 1:N)
AWS_REGION=eu-west-1
AWS_REKOGNITION_COLLECTION=campusconnect-auth-faces
FACE_MATCH_THRESHOLD=80.0
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...

# Config Server (Spring Cloud Config)
CONFIG_SERVER_URL=http://localhost:8888
CONFIG_CLIENT_PASSWORD=changez-moi
```

> Générer la clé JWT : `openssl rand -base64 32`. Pour AWS, privilégier un profil local ou
> un rôle IAM en déploiement plutôt que des clés statiques.

### Variante Config Server (production)

Dans l’architecture de production prévue, les valeurs **non sensibles** seront lues depuis le dépôt de configuration
`campusconnect-config-repo/auth-service.yml`. Les secrets (`JWT_SECRET`,
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` et `DB_PASSWORD`) restent en variables d'environnement.

Le branchement au Config Server est hors scope de ce README ; la configuration Django locale utilise `.env`.

---

## 7. Lancer le projet et tester les modules biométriques

Toutes les commandes suivantes s’exécutent depuis `CampusConnect/auth_service/`.
Pour un test indépendant des autres microservices, utiliser le compte Django existant.

**Option A — SQLite (développement)** : ajouter `DB_ENGINE=sqlite` au `.env` si le
sélecteur de base est présent dans `config/settings.py`.

**Option B — PostgreSQL** : créer le rôle et la base une seule fois, puis renseigner
les paramètres `DB_*` de la section 6 avec les valeurs réelles (dont le port).

```bash
sudo -u postgres createuser --pwprompt auth_user
sudo -u postgres createdb --owner=auth_user auth_db
```

**Démarrage commun :**

```bash
uv sync
uv run python manage.py check
uv run python manage.py migrate
# Seulement si aucun compte de test n'existe déjà :
uv run python manage.py createsuperuser
uv run python manage.py runserver 8081
```

Si les migrations du module `authentication` ne sont pas encore présentes dans
le dépôt, les générer avec `uv run python manage.py makemigrations authentication`
avant `migrate`. Le modèle utilisateur métier reste un chantier distinct ; ne pas
changer `AUTH_USER_MODEL` sur une base déjà migrée pour ce simple test.


Le service répond sur **http://localhost:8081**.
Endpoint de santé (à venir) : `/health`.

### 7.1. Module `facial_auth` — reconnaissance faciale

Cette application Django partage le processus, la configuration et la base de données du service Auth. Elle utilise OpenCV pour détecter la présence d’un visage et AWS Rekognition pour effectuer une identification 1:N.

- `FaceAuthentication.enroll(user, image_bytes)` associe une photo de référence à un compte existant. AWS indexe le visage avec l’identifiant du compte comme `ExternalImageId`.
- `FaceAuthentication.authenticate(frame_bytes)` détecte localement les visages, puis effectue une recherche `SearchFacesByImage` si un seul visage est présent.
- `authentication.models.FaceCredential` conserve la référence à l’utilisateur, le fichier photo, le `FaceId` AWS et l’état actif. Il n’existe pas de modèle indépendant dans `facial_auth`.
- La reconnaissance retourne un statut et, en cas de correspondance active, un identifiant de compte et un score de similarité. Elle ne délivre pas de JWT.

#### Endpoints de reconnaissance faciale

| Méthode | Route | Fonction |
|---|---|---|
| GET | `/api/auth/face/camera/` | Interface de démonstration avec webcam |
| POST | `/api/auth/face/recognize/` | Reconnaître un visage ; requête multipart, champ `frame` |

L’enrôlement s’effectue actuellement via la stratégie Python, pas via un endpoint HTTP public.

#### Étape 1 — Configurer AWS Rekognition

Renseigner `AWS_REGION`, `AWS_REKOGNITION_COLLECTION` et `FACE_MATCH_THRESHOLD` dans le `.env` (section 6). Boto3 utilise les identifiants AWS de l’environnement, d’un profil local ou d’un rôle IAM. L’identité doit disposer des permissions `rekognition:CreateCollection`, `rekognition:IndexFaces` et `rekognition:SearchFacesByImage`.

Ne jamais publier de véritables clés AWS. Vérifier la disponibilité des identifiants sans les afficher :

```bash
uv run python manage.py shell -c 'import boto3; print("Identifiants disponibles :", boto3.Session().get_credentials() is not None)'
uv run python manage.py setup_face_collection
```

Résultat attendu : `Collection Rekognition prête.` En cas de `NoCredentialsError`, configurer des identifiants AWS valides avant de poursuivre. Une connexion Internet est nécessaire.

#### Étape 2 — Enrôler un visage de référence

Utiliser exclusivement une photo de test d’une personne consentante, avec un seul visage et une taille maximale de 5 Mo. La placer temporairement dans `auth_service/` sous le nom `visage.jpg` (ne pas la commiter).

```bash
uv run python manage.py shell
```

```python
from django.contrib.auth import get_user_model
from authentication.container import build_authentication_factory
from authentication.strategies.base import AuthMethod
from pathlib import Path

User = get_user_model()
print(list(User.objects.values("id", "username")))
# Remplacer 1 par l'identifiant de son compte de test.
user = User.objects.get(pk=1)
face_auth = build_authentication_factory().create(AuthMethod.FACE)
credential = face_auth.enroll(user, Path("visage.jpg").read_bytes())
print(credential.rekognition_face_id)
```

Quitter le shell avec `exit()`. Si un visage a déjà été enrôlé pour ce compte, ne pas répéter l’enrôlement ; utiliser la référence existante. Un `FaceId` retourné confirme l’indexation et l’enregistrement local.

#### Étape 3 — Tester la webcam

Démarrer le serveur si nécessaire (`uv run python manage.py runserver 8081`), puis ouvrir :

**[http://localhost:8081/api/auth/face/camera/](http://localhost:8081/api/auth/face/camera/)**

Cliquer sur **Activer la caméra**, autoriser l’accès à la webcam et effectuer les scénarios suivants :

| Scénario | Statut attendu |
|---|---|
| Visage de référence reconnu | `recognized` + `user_id` + `similarity` |
| Visage non enrôlé, sans correspondance suffisante | `unknown` |
| Plusieurs visages détectés | `multiple_faces` |
| Aucun visage détecté | `no_face` |

Exemple de réponse attendue en cas de reconnaissance (valeurs illustratives) :

```json
{
  "status": "recognized",
  "face_count": 1,
  "user_id": "1",
  "similarity": 98.42
}
```

La caméra effectue des captures JPEG périodiques (intervalle de 1,8 seconde) et une recherche AWS lorsqu’un seul visage est détecté. Arrêter la caméra après le test pour limiter les requêtes facturables. Les captures de reconnaissance ne sont pas enregistrées par l’application, contrairement à la photo de référence. La caméra exige `localhost` ou un contexte HTTPS de confiance.

#### Dépannage et intégration future

```bash
uv run python -c "import cv2; print(cv2.__version__); print(hasattr(cv2, 'CascadeClassifier'))"
```

Un résultat `False` indique un problème avec l'installation OpenCV. Vérifier la dépendance `opencv-python-headless` puis, si elle est déclarée, essayer `uv sync --reinstall-package opencv-python-headless`.
Une réponse HTTP 502 du module facial peut indiquer un problème AWS (identifiants, permissions, collection ou réseau).

L’application `inscription` pourra appeler `face_auth.enroll(user, photo_de_reference.read())`. La future application `connexion` devra appeler `face_auth.authenticate(frame.read())`, vérifier le statut `recognized` et l’état du compte, puis confier l’audit et l’émission des jetons à `AuthenticationService`.

**Validation :** module implémenté, mais test AWS de bout en bout non confirmé (dernier blocage observé : `NoCredentialsError`). La détection du vivant et la protection contre la présentation de photos ne sont pas encore implémentées. Le seuil de 80 est une valeur de démonstration, non une garantie de sécurité. Ne pas utiliser ce flux seul pour une connexion en production.

Pour plus de détails : [`facial_auth/README.md`](facial_auth/README.md).

### 7.2. Module `fingerprint_auth` — authentification WebAuthn

Le module implémente l'enrôlement et la vérification des passkeys avec WebAuthn,
selon les patrons Factory + Strategy. La vérification utilisateur se déroule sur
l'appareil : empreinte digitale si l'authentificateur la propose, ou autre méthode
locale (PIN, visage, clé de sécurité). Aucune empreinte brute ni clé privée n'est
transmise au serveur par WebAuthn.

**Fonctionnalités implémentées :**

- Consentement de l'utilisateur avant enrôlement, avec possibilité de retrait.
- Enregistrement, vérification, consultation et révocation des passkeys.
- Challenges aléatoires de 32 octets, valables 5 minutes, à usage unique et liés à la session.
- Vérification de la signature, de l'origine, du RP ID, du compteur de signatures et de la vérification utilisateur (`required`).
- Limite de cinq passkeys par compte ; modèles `FingerprintConsent`, `FingerprintCredential` et `FingerprintChallenge` centralisés dans `authentication/models.py`.
- Interface web de démonstration utilisant les sessions Django et la protection CSRF.

#### Endpoints WebAuthn

| Méthode | Route | Fonction |
|---|---|---|
| GET | `/api/auth/fingerprint/demo/` | Interface de démonstration |
| POST / DELETE | `/api/auth/register/consent/` | Accepter / retirer le consentement |
| POST | `/api/auth/register/fingerprint/options/` | Générer les options d'enrôlement |
| POST | `/api/auth/register/fingerprint/verify/` | Vérifier et enregistrer la passkey |
| POST | `/api/auth/webauthn/login/options/` | Générer le challenge de connexion |
| POST | `/api/auth/webauthn/login/verify/` | Vérifier la preuve WebAuthn |
| GET | `/api/auth/webauthn/credentials/` | Lister les passkeys du compte connecté |
| DELETE | `/api/auth/webauthn/credentials/<id>/` | Révoquer une passkey du compte connecté |

#### Test local (SQLite)

Pour tester le module indépendamment de PostgreSQL, si le sélecteur de base de données
est présent dans `config/settings.py`, ajouter `DB_ENGINE=sqlite` au `.env`.
Conserver les paramètres WebAuthn de la section 6. Depuis `auth_service/` :

```bash
uv sync
# Si webauthn n'est pas encore déclaré dans pyproject.toml : uv add webauthn
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver 8081
```

Ouvrir [http://localhost:8081/api/auth/fingerprint/demo/](http://localhost:8081/api/auth/fingerprint/demo/).
Se connecter avec un compte Django, accepter le consentement, enregistrer une passkey,
fermer la session de démo puis cliquer sur **Vérifier ma passkey**. Le résultat attendu contient `status: recognized`,
`user_id` et `amr: webauthn`.

```json
{"status": "recognized", "user_id": "1", "amr": "webauthn"}
```

Tester également un enrôlement sans consentement (refus attendu), une vérification annulée ou un challenge expiré (échec attendu), et la révocation d’une passkey (elle ne doit plus être utilisable côté serveur).

#### Test sur Android via USB

Lancer Django, connecter le téléphone avec le débogage USB activé, puis exécuter :

```bash
adb devices -l
adb reverse tcp:8081 tcp:8081
```

Ouvrir la même URL `http://localhost:8081/api/auth/fingerprint/demo/` dans Chrome sur
le téléphone. WebAuthn exige un contexte sécurisé (localhost pour le développement,
HTTPS de confiance pour un déploiement). Le RP ID et l'origine doivent correspondre
à l'adresse utilisée par le navigateur.

#### Test sur PC Linux

Un lecteur reconnu par `fprintd` ne suffit pas à fournir WebAuthn. Sur la machine de test Dell Latitude 5580, le pilote CV2 a été compilé et le service `fprintd` configuré. Un authentificateur FIDO2 virtuel expérimental (`passkey-tpm`) a également été installé. Pour vérifier ces composants si déjà configurés :

```bash
fprintd-verify -f right-index-finger
fido2-token -L
```

Ouvrir ensuite la page de démo dans Chromium ou Firefox, choisir la clé de sécurité si proposée, puis tenter l’enrôlement et la vérification. Ne pas modifier les permissions du TPM ni désactiver les contrôles de sécurité pour faire fonctionner la démo.

#### Validation et limites

- Android : test WebAuthn réalisé avec succès.
- Linux : lecteur Broadcom ControlVault 2 du Dell Latitude 5580 validé avec le pilote CV2 et `fprintd` ; authentificateur FIDO2 virtuel `passkey-tpm` détecté. Le test WebAuthn complet dans le navigateur reste à valider. Cette configuration expérimentale n'est pas un prérequis général du projet.
- Le module retourne une preuve vérifiée et un identifiant de compte, mais ne délivre pas encore de JWT. L'intégration avec `AuthenticationService`, l'inscription définitive et les contrôles métier reste à réaliser.
- Les interfaces de démonstration sont réservées au développement (`DEBUG` et `WEBAUTHN_DEMO_ENABLED`). WebAuthn ne prouve pas à lui seul que la vérification locale a utilisé exclusivement une empreinte.

Pour plus de détails : [`fingerprint_auth/README.md`](fingerprint_auth/README.md).

---

## 8. Tests

```bash
# Toute la suite
uv run pytest

# Avec couverture (cible : ≥ 85 %, cahier NFR-06)
uv run pytest --cov=authentication --cov-report=html

# Ouvrir le rapport
xdg-open htmlcov/index.html
```

Tests du module empreinte (vérifications cryptographiques simulées ; à compléter par les tests navigateur) :

```bash
uv run python manage.py test fingerprint_auth
```

Les scénarios manuels de `facial_auth` sont décrits en section 7.1. Le test complet requiert une collection AWS et un visage de référence ; ne pas supposer que la suite automatique couvre déjà ce flux.

Structure des tests (à venir) :
- `authentication/tests/unit/` — stratégies isolées (pytest)
- `authentication/tests/integration/` — avec PostgreSQL réel
- `authentication/tests/api/` — endpoints DRF

---

## 9. Conventions de code

| Règle | Détail |
|---|---|
| **Une stratégie ne crée pas de jeton** | Elle retourne `AuthResult` ou lève `AuthenticationError` |
| **Seule `AuthenticationService` émet les jetons et écrit l'audit** | Aucune exception |
| **Validation d'entrée via serializer DRF** | Aucune stratégie ne reçoit de dict brut non validé |
| **Échec d'auth → toujours `INVALID_CREDENTIALS`** | Pas d'énumération de comptes ; la vraie raison va dans l'audit |
| **Aucun secret dans les logs** | NFR-08 : ni mot de passe, ni jeton, ni embedding |
| **Injection par constructeur** | Pas d'import global d'un moteur dans une stratégie ; assemblage dans `container.py` |

---

## 10. État d'avancement

| Élément | Statut |
|---|---|
| Projet Django + DRF sous uv | ✅ Fait |
| 3 apps : `authentication`, `facial_auth`, `fingerprint_auth` | ✅ Fait |
| Structure Factory + Strategy (dossiers + `container.py`) | ✅ Fait |
| Modèle `User` custom (`role`, `status`, `matricule`) | ⏳ À faire |
| Stratégies concrètes | ✅ Face et WebAuthn implémentés ; mot de passe métier et QR à intégrer |
| Endpoints `/api/auth/register`, `/login`, `/refresh`, `/logout` | ⏳ À faire |
| QR code personnel (génération, scan, révocation) | ⏳ À faire (P1 du cahier) |
| WebAuthn (empreinte) | ✅ Implémenté et testé sur Android ; intégration JWT et validation WebAuthn Linux à finaliser |
| Reconnaissance faciale 1:N (détection + recherche AWS) | ✅ Implémentée dans `facial_auth` ; validation AWS à finaliser |
| Détection de vivacité anti-spoofing | ⏳ À concevoir séparément |
| Tests ≥ 85 % | ⏳ À faire |
| Docker | ⏳ À faire |

Roadmap détaillée : voir `../cahier-conception-auth-service-v2.pdf`, section 11 (Contrat API)
et section 14 (Plan d'implémentation).

---

## 11. Confidentialité et publication Git

Ne pas versionner le fichier `.env`, les clés AWS, les secrets Django/JWT, les bases SQLite, les photos de référence (`media/`, `visage.jpg`) ni les exports contenant des secrets. Les images de référence sont des données biométriques sensibles : utiliser des comptes de test consentants, limiter les accès et prévoir leur suppression locale et dans la collection AWS après usage.

Les endpoints de démonstration doivent rester dans un environnement de développement. Pour le déploiement, désactiver les vues de démo, utiliser HTTPS, mettre en place le contrôle métier, l’audit et la limitation des tentatives, et vérifier l’intégration des deux stratégies à `AuthenticationService`.

---

## 12. Documents de référence

- [`../cahier_des_charges_CampusConnect.pdf`](../cahier_des_charges_CampusConnect.pdf) — cahier des charges global (section 3.1 = Auth Service)
- [`../cahier-conception-auth-service-v2.pdf`](../cahier-conception-auth-service-v2.pdf) — conception détaillée (Factory + Strategy, UML, contrat API)
- [`../CONFIG_GUIDE.md`](../CONFIG_GUIDE.md) — brancher un microservice sur le Config Server
- [`../config_service/README.md`](../config_service/README.md) — serveur de configuration

---

## 13. Contact

Équipe M2 — responsable Auth Service.
Relecteurs : M1 (infrastructure), M5 (qualité et tests).
