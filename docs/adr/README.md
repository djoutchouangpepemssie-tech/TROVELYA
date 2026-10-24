# Décisions d'architecture (ADR)

Format : contexte, décision, conséquences. Une décision qui change donne un nouvel ADR qui remplace l'ancien.

| N° | Décision | Statut |
|---|---|---|
| [0001](0001-monolithe-modulaire.md) | Monolithe modulaire FastAPI | Acceptée (cahier 5.2) |
| [0002](0002-postgresql-source-unique.md) | PostgreSQL, source de vérité unique | Acceptée (cahier 5.2) |
| [0003](0003-recherche-postgresql-dabord.md) | Recherche : PostgreSQL d'abord | Acceptée (cahier 5.2), mise en œuvre en P3 |
| [0004](0004-contrat-openapi.md) | Contrat API OpenAPI et client généré | Acceptée (cahier 5.2), en place depuis P0-T12 |
| [0005](0005-argent-centimes-grand-livre.md) | Argent : centimes entiers et grand livre en partie double | Acceptée (cahier 5.2), socle en place depuis P0-T07 |
| [0006](0006-temps-reel.md) | Temps réel : WebSocket et un seul écrivain par enchère | Acceptée (cahier 5.2), mise en œuvre en P12-P13 |
| [0007](0007-arq-outbox.md) | Tâches asynchrones avec arq et outbox transactionnelle | Acceptée (cahier 5.2), en place depuis P0-T06 |
| [0008](0008-sessions-opaques.md) | Authentification par sessions opaques | Acceptée (cahier 5.2), mise en œuvre en P1 |
| [0009](0009-sqlalchemy-alembic.md) | ORM SQLAlchemy 2 asynchrone et migrations Alembic | Acceptée (cahier 5.2), écart E6 |
| [0010](0010-prestataire-paiement.md) | Prestataire de paiement derrière une interface | Proposée — choix final à valider par Arcel |
| [0011](0011-image-postgresql-17.md) | Notre image PostgreSQL 17 (PostGIS, pgvector, h3) | Acceptée (décision V2 d'Arcel) |
| [0012](0012-cle-idempotence.md) | Clé d'idempotence : identifiant technique et unicité NULLS NOT DISTINCT | Acceptée (écart E1) |
| [0013](0013-branche-release.md) | Production sur la branche `release` | Acceptée (écart E5) |
| [0014](0014-chaine-audit-en-base.md) | Chaîne du journal d'audit calculée en base | Acceptée (écart E2) |
| [0015](0015-relais-same-origin.md) | Relais same-origin entre le web et l'API, IP de confiance | Acceptée (écarts E1 à E4 du plan P1) |
| [0016](0016-export-rgpd.md) | Export RGPD chiffré, stocké en base jusqu'au stockage de fichiers | Acceptée (Q16, E8) |
| [0017](0017-resend-provisoire.md) | E-mails par Resend, écart temporaire à la résidence UE | Acceptée, provisoire (décision Q6) |
| [0018](0018-comptes-staff.md) | Comptes staff : passkey seule, création et enrôlement par script | Acceptée (Q18, E9) |
