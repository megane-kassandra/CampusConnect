# Auth Service — CampusConnect

Microservice d'authentification multi-méthodes du projet **CampusConnect** (TP 4057).
Implémentation Django 5 + DRF, conforme au **cahier de conception v2.0** (section 5 :
patron Factory + Strategy).

---

## 1. Rôle dans l'architecture

Le service gère :

- l'**inscription par étapes** (identifiants + empreinte WebAuthn + visage avec vivacité) ;
- la **génération du QR code** personnel (jeton opaque signé, révocable) ;
- la **connexion multi-méthodes** : mot de passe, empreinte, visage ;
- l'émission et la révocation des **JWT** (access 15 min, refresh 7 jours avec rotation) ;
- la **journalisation d'audit** de tous les événements d'authentification.

Il **n'appelle aucun autre service** et n'expose pas ses tables. Les autres microservices
valident le JWT localement (HS256 pour la démo, RS256 + JWKS en production).

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
| Framework | Django 5 + Django REST Framework |
| Base de données | PostgreSQL (`auth_db`) |
| Gestionnaire de paquets | **uv** (avec `requirements.txt` de secours pour pip) |
| Authentification | JWT HS256 (démo) / RS256 (prod) |
| Biométrie | WebAuthn (empreinte), embeddings faciaux chiffrés AES/Fernet (visage) |
| Conteneurisation | Docker (une image, une base) |
| Configuration | Spring Cloud Config Server (config centralisée) |

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
├── domain/exceptions.py
└── container.py                   ← SEULE racine de composition

facial_auth/                       ← app Django "stratégie visage"
└── strategy.py                    ← FaceAuthentication(Authentication, Enrollable)

fingerprint_auth/                  ← app Django "stratégie empreinte"
└── strategy.py                    ← FingerprintAuthentication(Authentication, Enrollable)
```

### Règles de dépendance (à respecter impérativement)

1. **`facial_auth` et `fingerprint_auth` importent depuis `authentication`**, jamais l'inverse.
2. **`container.py` est le SEUL fichier qui importe les 3 apps** — c'est la racine de composition.
3. La Factory **ne connaît pas** les apps externes : elle reçoit un `Dict[AuthMethod, Callable]` déjà peuplé par `container.py`.
4. **Aucun `models.py`** dans `facial_auth` / `fingerprint_auth` (les templates restent dans `authentication/models.py`).
5. Ajouter une méthode = **(a)** une valeur dans `AuthMethod`, **(b)** une classe dans `strategies/`, **(c)** une ligne dans `container.py`, **(d)** ses tests.

---

## 4. Prérequis

- **Python 3.12** (`python3.12 --version`)
- **uv** (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **PostgreSQL 15+** en local, base `auth_db` créée
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

# Biométrie (chiffrement des embeddings)
BIOMETRIC_KEY=changez-moi-cle-fernet

# Config Server (Spring Cloud Config)
CONFIG_SERVER_URL=http://localhost:8888
CONFIG_CLIENT_PASSWORD=changez-moi
```

> Générer les clés : `openssl rand -base64 32` (JWT_SECRET) et
> `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
> (BIOMETRIC_KEY).

### Variante Config Server (production)

En production, les valeurs **non sensibles** sont lues depuis le dépôt de configuration
`campusconnect-config-repo/auth-service.yml`. Les secrets (`JWT_SECRET`,
`BIOMETRIC_KEY`, `DB_PASSWORD`) restent en variables d'environnement.

Le branchement se fait via `spring.config.import` (côté client) — hors scope de ce README.

---

## 7. Lancer le projet

```bash
cd auth_service

# 1. Créer la base PostgreSQL (une seule fois)
sudo -u postgres createdb auth_db
sudo -u postgres createuser auth_user -P

# 2. Appliquer les migrations
uv run python manage.py migrate

# 3. Créer un superutilisateur admin (accès /admin Django)
uv run python manage.py createsuperuser

# 4. Lancer le serveur de dev (port 8081, cohérent avec Auth Service dans le cahier)
uv run python manage.py runserver 8081
```

Le service répond sur **http://localhost:8081**.
Endpoint de santé (à venir) : `/health`.

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
| Stratégies concrètes (`PasswordAuthentication`, `FaceAuthentication`, …) | ⏳ À faire |
| Endpoints `/api/auth/register`, `/login`, `/refresh`, `/logout` | ⏳ À faire |
| QR code personnel (génération, scan, révocation) | ⏳ À faire (P1 du cahier) |
| WebAuthn (empreinte) | ⏳ P2 |
| Reconnaissance faciale (avec vivacité) | ⏳ P3 |
| Tests ≥ 85 % | ⏳ À faire |
| Docker | ⏳ À faire |

Roadmap détaillée : voir `../cahier-conception-auth-service-v2.pdf`, section 11 (Contrat API)
et section 14 (Plan d'implémentation).

---

## 11. Documents de référence

- [`../cahier_des_charges_CampusConnect.pdf`](../cahier_des_charges_CampusConnect.pdf) — cahier des charges global (section 3.1 = Auth Service)
- [`../cahier-conception-auth-service-v2.pdf`](../cahier-conception-auth-service-v2.pdf) — conception détaillée (Factory + Strategy, UML, contrat API)
- [`../CONFIG_GUIDE.md`](../CONFIG_GUIDE.md) — brancher un microservice sur le Config Server
- [`../config_service/README.md`](../config_service/README.md) — serveur de configuration

---

## 12. Contact

Équipe M2 — responsable Auth Service.
Relecteurs : M1 (infrastructure), M5 (qualité et tests).
