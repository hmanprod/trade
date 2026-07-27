---
goal: Multi-comptes Telegram (connexion, déconnexion, suppression, group discovery)
version: 1.0
date_created: 2026-07-27
status: 'Planned'
tags: feature, telegram, accounts
---

# Introduction

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

Permettre à l'admin de connecter plusieurs comptes Telegram (pour la collecte), de les lister, de déconnecter/supprimer un compte individuellement ou tous les comptes. Le modèle `MTProtoSession` est déjà une table (multi-lignes), mais le code est construit autour d'un singleton. À refactorer en registre multi-clients.

## 1. Requirements & Constraints

- **REQ-001**: Ajouter un compte Telegram (phone → send-code → verify → session stockée)
- **REQ-002**: Lister tous les comptes avec leur statut (connecté/déconnecté)
- **REQ-003**: Déconnecter un compte spécifique (client Telethon déconnecté, `is_connected=False`)
- **REQ-004**: Déconnecter tous les comptes
- **REQ-005**: Supprimer définitivement un compte (session effacée de la DB)
- **REQ-006**: Supprimer tous les comptes
- **REQ-007**: Au démarrage, restaurer tous les comptes marqués `is_connected=True`
- **REQ-008**: Associer chaque groupe source au compte Telegram qui y a accès (`session_id` FK)
- **REQ-009**: Le relay doit pouvoir écouter `events.NewMessage` sur tous les clients connectés
- **REQ-010**: Forwarder utilise le bon client (celui qui a accès au groupe source)
- **CON-001**: Un seul groupe de destination global (pas par compte)
- **CON-002**: Un seul jeu de filtres global
- **CON-003**: UI en HTMX (pas de SPA), chaque action swap du HTML
- **PAT-001**: Même pattern de routes que l'existant : `_guard()` + `HTMLResponse`

## 2. Implementation Steps

### Implementation Phase 1 — Refactor TelethonManager en registre multi-clients

- GOAL-001: Remplacer `TelethonManager` (singleton) par `MultiTelethonManager` (dict de clients)

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Créer `MultiTelethonManager` avec dict `_clients: dict[int, TelegramClient]` et `_phones: dict[int, str]` | | |
| TASK-002 | `add(session_id, client, phone)` → ajoute au dict | | |
| TASK-003 | `remove(session_id)` → déconnecte + retire du dict | | |
| TASK-004 | `get(session_id)` → retourne le client ou None | | |
| TASK-005 | `get_all()` → liste des (session_id, client, phone) | | |
| TASK-006 | `disconnect_all()` → déconnecte tous les clients, vide les dicts | | |
| TASK-007 | `is_connected(session_id)` → statut d'un client spécifique | | |
| TASK-008 | `connected_count()` → nombre de clients connectés | | |
| TASK-009 | Mettre à jour `app/telegram/__init__.py` pour exporter `multi_telethon_manager` | | |

### Implementation Phase 2 — Refactor routes MTProto (send-code/verify)

- GOAL-002: Adapter les routes d'authentification Telegram pour gérer plusieurs comptes

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-010 | `POST /api/mtproto/send-code` → crée un client temporaire, stocke phone+hash en session cookie ou en mémoire, retourne formulaire verify | | |
| TASK-011 | `POST /api/mtproto/verify` → sign_in, sauvegarde en DB (nouveau row `MTProtoSession`), ajoute client au manager, retourne HTML avec statut + bouton disconnect | | |
| TASK-012 | `GET /api/mtproto/accounts` → liste tous les comptes (id, phone, status, boutons disconnect/delete) | | |
| TASK-013 | `POST /api/mtproto/{id}/disconnect` → déconnecte un compte spécifique, met `is_connected=False` en DB | | |
| TASK-014 | `POST /api/mtproto/disconnect-all` → déconnecte tous les comptes, met tous `is_connected=False` | | |
| TASK-015 | `DELETE /api/mtproto/{id}` → supprime définitivement un compte + sa session (row supprimé de la DB) | | |
| TASK-016 | `DELETE /api/mtproto/all` → supprime tous les comptes | | |
| TASK-017 | `GET /api/mtproto/status` → remplace par affichage du nombre de comptes connectés/total (ex: "2/3 connected") | | |

### Implementation Phase 3 — DB Schema : associer groupes au compte

- GOAL-003: Ajouter `session_id` FK à `SourceGroup`, ajouter les colonnes de gestion de comptes

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-018 | Ajouter `session_id: Mapped[int]` + FK → `mtproto_session.id` à `SourceGroup` | | |
| TASK-019 | Rendre `(group_id, session_id)` unique (un même groupe peut être scrappé par plusieurs comptes) | | |
| TASK-020 | Ajouter `label: Mapped[str | None]` à `MTProtoSession` (nom personnalisé optionnel pour identifier le compte) | | |
| TASK-021 | Ajouter `created_at: Mapped[datetime]` à `MTProtoSession` | | |
| TASK-022 | Mettre à jour le lifespan dans `main.py` pour restaurer TOUS les clients connectés, pas seulement le premier | | |

### Implementation Phase 4 — Adapter les routes groups au multi-compte

- GOAL-004: La découverte et sélection des groupes se fait par compte

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-023 | `GET /api/groups/{session_id}` → liste des dialogs d'un compte spécifique | | |
| TASK-024 | `POST /api/groups/toggle` → `session_id` inclus dans les vals, `SourceGroup.session_id` rempli | | |
| TASK-025 | `POST /api/groups/set-destination` → pas de changement (destination globale) | | |
| TASK-026 | Afficher le nom du compte à côté de chaque groupe dans la UI | | |

### Implementation Phase 5 — Adapter le relay au multi-compte

- GOAL-005: Le relay écoute tous les clients connectés et forwarde avec le bon client

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-027 | `start_relay()` → itère `multi_telethon_manager.get_all()`, pour chaque client : `client.on(events.NewMessage)` avec handler qui utilise le session_id du client | | |
| TASK-028 | Handler consulte `SourceGroup` pour vérifier que `(group_id, session_id)` est actif | | |
| TASK-029 | Forwarding via `client.forward_messages()` du client propriétaire du groupe source | | |
| TASK-030 | `stop_relay()` → retire tous les event handlers de tous les clients | | |
| TASK-031 | Cache de déduplication : inchangé (Set global) | | |

### Implementation Phase 6 — UI : section comptes + liste groupes par compte

- GOAL-006: Mettre à jour `dashboard.html` pour gérer la sélection de compte et l'affichage multi-compte

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-032 | Remplacer la section "Telegram Connection" par "Accounts" avec liste des comptes + "Add Account" | | |
| TASK-033 | Template `_account_row.html` : phone, label, badge connected/disconnected, bouton disconnect, delete | | |
| TASK-034 | Template `_add_account_form.html` : send-code / verify flow (comme existant) | | |
| TASK-035 | "Disconnect All" et "Delete All" buttons avec modals de confirmation | | |
| TASK-036 | Section "Groups" : dropdown/select pour choisir le compte, puis affichage des dialogs de ce compte | | |

### Implementation Phase 7 — Ajustements finaux

- GOAL-007: Nettoyage, migration DB, rollback safe

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-037 | Ajouter un script de migration DB (ALTER TABLE) pour `source_groups.session_id` | | |
| TASK-038 | Vérifier que les anciennes données sans `session_id` continuent de fonctionner (valeur par défaut = 1 ou NULL) | | |
| TASK-039 | Tester en local le flow complet : 2 comptes → discovery → relay | | |
| TASK-040 | Déployer sur Fly.io | | |

## 3. Alternatives

- **ALT-001**: Un TelethonManager avec un seul client qu'on reconnecte dynamiquement selon le groupe à scraper — Trop complexe, perte des events en temps réel.
- **ALT-002**: Stocker les clients dans Redis (hors-process) — Overkill, aucun besoin de persistance inter-process pour ce use case.
- **ALT-003**: Garder un seul compte Telegram mais permettre de le changer — L'utilisateur veut explicitement plusieurs comptes simultanés.

## 4. Dependencies

- **DEP-001**: `Telethon` déjà installé
- **DEP-002**: `cryptography` déjà installé (chiffrement sessions)
- **DEP-003**: Aucun nouveau package nécessaire.

## 5. Files

| File | Action | Description |
|------|--------|-------------|
| `app/telegram/client.py` | REFACTOR | Remplacer `TelethonManager` par `MultiTelethonManager` |
| `app/db/models.py` | MODIFY | Ajouter `session_id` FK à `SourceGroup`, `label` et `created_at` à `MTProtoSession` |
| `app/main.py` | MODIFY | Lifespan : restaurer tous les clients |
| `app/routes/mtproto.py` | REWRITE | Routes multi-comptes (send-code/verify/accounts/disconnect/delete) |
| `app/routes/groups.py` | MODIFY | Ajouter `session_id` aux params |
| `app/telegram/relay.py` | MODIFY | Support multi-clients |
| `app/routes/relay.py` | MODIFY | Ajustements mineurs |
| `app/templates/dashboard.html` | REWRITE | Section accounts + groups par compte |
| `app/templates/_account_row.html` | CREATE | Fragment HTMX pour un compte |
| `app/templates/_add_account_form.html` | CREATE | Fragment HTMX formulaire ajout |
| `plan/architecture-workflow-stack.md` | MODIFY | Mettre à jour le schema DB et l'architecture |

## 6. Testing

- **TEST-001**: Ajout de 2 comptes via send-code → verify
- **TEST-002**: Déconnexion individuelle d'un compte
- **TEST-003**: Déconnexion de tous les comptes
- **TEST-004**: Suppression d'un compte (row supprimé)
- **TEST-005**: Suppression de tous les comptes
- **TEST-006**: Restauration automatique des sessions au démarrage
- **TEST-007**: Groups : sélection de compte → liste des dialogs
- **TEST-008**: Relay : messages forwardés depuis des groupes de comptes différents

## 7. Risks & Assumptions

- **RISK-001**: Chaque client Telethon maintient une connexion MTProto → 2 clients = 2 connexions. Vérifier que Fly.io 512MB suffit pour ~5 clients.
- **RISK-002**: Plusieurs clients Telethon = plus de requêtes vers Telegram. Surveiller les rate limits.
- **ASSUMPTION-001**: Les sessions Telethon peuvent être créées simultanément sans conflit (chaque session est indépendante).
- **ASSUMPTION-002**: L'admin peut ajouter des comptes dont il possède le téléphone et peut recevoir le code.

## 8. Related Specifications / Further Reading

- `plan/architecture-workflow-stack.md` — Architecture globale du projet
- [Telethon Documentation](https://docs.telethon.dev) — Client MTProto
- [Fly.io Docs](https://fly.io/docs/) — Déploiement
