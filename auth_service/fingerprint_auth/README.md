# fingerprint_auth — CampusConnect

Module WebAuthn de démonstration : challenge 32 octets, 5 minutes, usage unique,
RP ID/origine configurés, vérification utilisateur obligatoire, compteur de
signatures, consentement et maximum de cinq passkeys. Aucun gabarit biométrique.
Une passkey peut utiliser une empreinte, un visage, une clé physique ou un PIN.

## Démarrage local

    uv sync
    uv add webauthn
    uv run python manage.py makemigrations authentication
    uv run python manage.py migrate
    uv run python manage.py shell

Dans le shell :

    from django.contrib.auth import get_user_model
    get_user_model().objects.create_user(username='demo_fingerprint', password='ChangeThisDemoPassword123!')
    exit()

    uv run python manage.py runserver 8081

Ouvrir http://localhost:8081/api/auth/fingerprint/demo/ (pas 127.0.0.1).
Se connecter, donner son consentement, enregistrer une passkey, fermer la session,
puis vérifier la passkey. La preuve renvoie recognized/user_id/amr, pas de JWT.

## Configuration

    WEBAUTHN_RP_ID=localhost
    WEBAUTHN_ORIGIN=http://localhost:8081
    WEBAUTHN_DEMO_ENABLED=true

Sur téléphone : HTTPS de confiance, nom de domaine stable, RP ID = nom de domaine
sans schéma ni port, origin = origine exacte visible par le navigateur. Les valeurs
sont lues via l'environnement existant. Ne pas désactiver les vérifications TLS/CSRF.

## Intégration future

Les vues actuelles utilisent la session Django, uniquement en DEBUG. Elles sont
désactivées en production. Remplacer cette adaptation HTTP par la validation des
jetons d'inscription et d'accès, et transmettre au moteur uniquement l'utilisateur
et un binding validés côté serveur. Ne jamais accepter un user_id fourni par le
client comme preuve de possession du compte. Le service central doit contrôler
le statut métier, les étapes d'inscription, l'audit, le throttling et émettre les JWT.
Le moteur consomme le challenge en autocommit avant toute transaction de verify ;
ne pas l'appeler depuis une transaction externe qui annulerait cette consommation.
L'enrôlement et la connexion sont exposés dans la Factory ; aucune dépendance
vers fingerprint_auth depuis le domaine hors container.py.

La limitation IP de démo utilise le cache Django local ; en production utiliser un
cache partagé et le contrôle par identifiant/IP prévu au cahier. Les logs sont
sans secrets, pas encore la table auth_events. Prévoir purge périodique des challenges
et des données d'inscriptions expirées. Les identifiants de challenge et les options
sont enveloppés dans {challengeId, publicKey}; vérifier le contrat avec l'équipe.
Les routes ont un slash final et utilisent /api/auth/ comme facial_auth. Le routage
Gateway doit être aligné (StripPrefix=1 est incompatible avec ces URLs directes).

## Tests

    uv run python manage.py test fingerprint_auth

Tests de logique Django avec vérifications crypto simulées ; compléter par un test
réel du navigateur et des tests cryptographiques, de charge et d'intégration JWT.
