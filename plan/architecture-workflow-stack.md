---
goal: Définir l'architecture, le workflow et la stack technique du projet Trade
version: 2.0
date_created: 2026-07-26
status: 'In progress'
tags: architecture, design, stack
---

# Introduction

![Status: In progress](https://img.shields.io/badge/status-In%20progress-yellow)

Plan d'architecture pour l'application **Trade** (mono-admin) : web app avec login admin, connexion du compte Telegram de l'admin via MTProto (Telethon), découverte et sélection de groupes sources à scraper, forwarding temps réel vers un groupe de destination.

## 1. Stack Technique

| Couche | Technologie | Justification |
|--------|-------------|---------------|
| **Runtime** | Python 3.12+ | Async natif via asyncio, écosystème mature pour MTProto |
| **Web Framework** | FastAPI | Async, autodoc, validation Pydantic intégrée |
| **Frontend** | Jinja2 + HTMX + Alpine.js | Pas de SPA lourde, UI réactive sans JS bundler |
| **CSS** | Tailwind CSS + DaisyUI | Utility-first + composants prêts à l'emploi |
| **Database** | Neon PostgreSQL (serverless) | Postgres compatible, scaling auto, pool serverless |
| **ORM** | SQLAlchemy 2.0 (async) | Mature, flexible, excellent support PostgreSQL |
| **Telegram MTProto** | Telethon | Client MTProto Python mature, events asynchrones, sessions persistantes |
| **Auth** | Mot de passe admin (ADMIN_PASSWORD) | Login simple, session en cookie signé (itsdangerous) |
| **Package Manager** | uv | Rapide, gestion des dépendances Python moderne |

## 2. Architecture Globale

```
┌─────────────────────────────────────────────────────────┐
│                    Fly.io (1 service)                    │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │              FastAPI App (Uvicorn)                │   │
│  │                                                   │   │
│  │  ┌──────────────────────┐  ┌──────────────────┐  │   │
│  │  │  Jinja2 Templates    │  │  API Routes      │  │   │
│  │  │  + HTMX              │  │  /auth/*         │  │   │
│  │  │  + Tailwind/DaisyUI  │  │  /api/mtproto/*  │  │   │
│  │  │                      │  │  /api/groups/*   │  │   │
│  │  │  Pages :             │  │  /api/config/*   │  │   │
│  │  │  - /login            │  └────────┬─────────┘  │   │
│  │  │  - /dashboard        │           │            │   │
│  │  └──────────────────────┘           │            │   │
│  │                                     │            │   │
│  │  ┌──────────────────────────────────▼──────────┐ │   │
│  │  │         Telethon Client (worker)             │ │   │
│  │  │  - Connexion MTProto persistante             │ │   │
│  │  │  - Écoute des groupes sources                │ │   │
│  │  │  - Filtrage optionnel (keywords)             │ │   │
│  │  │  - Forwarding temps réel vers destination    │ │   │
│  │  │  - Cache mémoire de déduplication            │ │   │
│  │  └──────────────────────────────────────────────┘ │   │
│  └─────────────────────────────────────────────────┘   │
│                        │                               │
│  ┌─────────────────────▼───────────────────────────┐   │
│  │          Neon PostgreSQL (SQLAlchemy async)      │   │
│  │  - mtproto_session (string session chiffrée)    │   │
│  │  - source_groups (groupes sélectionnés)          │   │
│  │  - relay_config (destination + filtres)          │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## 3. Workflow Utilisateur

```
1. Login admin (mot de passe)
   └→ Saisie du mot de passe ADMIN_PASSWORD
   └→ Session signée via cookie (itsdangerous)

2. Connexion du compte Telegram (MTProto)
   └→ Saisie du numéro de téléphone
   └→ Appel Telethon send_code_request() → code reçu sur Telegram
   └→ Saisie du code → sign_in() → String session stockée (chiffrée en DB)
   └→ Indicateur de statut : connecté / déconnecté

3. Découverte des groupes
   └→ Récupération de tous les dialogs du compte (client.get_dialogs())
   └→ Affichage dans une UI listant les groupes avec checkbox
   └→ L'admin coche les groupes sources à scraper

4. Configuration du relay
   └→ Sélection du groupe de destination (parmi les dialogs)
   └→ Filtres optionnels (mots-clés séparés par virgule)

5. Exécution (temps réel)
   └→ Le worker Telethon écoute les messages via @client.on(events.NewMessage)
   └→ À chaque message : vérification source → filtres → déduplication → forward
   └→ Cache mémoire Set[int] des (chat_id * 2^32 + message_id) déjà forwardés
```

## 4. Database Schema (SQLAlchemy async)

Uniquement la config — pas de stockage de messages.

```python
# mtproto_session (single row, upsert)
class MTProtoSession(Base):
    __tablename__ = "mtproto_session"
    id: Mapped[int] = mapped_column(primary_key=True)
    phone_number: Mapped[str]
    string_session: Mapped[str]       # chiffré au niveau applicatif
    is_connected: Mapped[bool] = False
    updated_at: Mapped[datetime]

# source_groups (groupes sources à écouter)
class SourceGroup(Base):
    __tablename__ = "source_groups"
    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(unique=True)  # Telegram chat_id
    title: Mapped[str]
    is_active: Mapped[bool] = False
    created_at: Mapped[datetime]

# relay_config (destination + filtres, single row)
class RelayConfig(Base):
    __tablename__ = "relay_config"
    id: Mapped[int] = mapped_column(primary_key=True)
    destination_group_id: Mapped[int | None]
    destination_title: Mapped[str | None]
    filter_keywords: Mapped[str | None]   # optionnel, "mot1,mot2"
    is_running: Mapped[bool] = False
    updated_at: Mapped[datetime]
```

## 5. Phases d'Implémentation

### Phase 1 — Scaffolding & Base

- GOAL: Initialiser le projet Python, la DB, et le squelette FastAPI

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Initialiser projet Python (uv + pyproject.toml) | | |
| TASK-002 | Structure FastAPI + Uvicorn (mode app factory) | | |
| TASK-003 | Configurer SQLAlchemy async + Neon PostgreSQL | | |
| TASK-004 | Configurer Tailwind CSS + DaisyUI (via CDN ou build) | | |
| TASK-005 | Créer les modèles SQLAlchemy (mtproto_session, source_groups, relay_config) | | |
| TASK-006 | Configurer les variables d'environnement (.env.example) | | |
| TASK-007 | Scripts : `uv run dev`, `uv run db-create` | | |

### Phase 2 — Authentification Admin

- GOAL: Login admin par mot de passe + middleware de protection

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-008 | Page login en Jinja2 + DaisyUI (formulaire mot de passe) | | |
| TASK-009 | Route POST /login avec validation ADMIN_PASSWORD | | |
| TASK-010 | Session cookie signée (itsdangerous) + middleware de protection | | |
| TASK-011 | Page dashboard protégée (redirection vers /login si non auth) | | |
| TASK-012 | Route GET /logout | | |

### Phase 3 — Client MTProto (Telethon)

- GOAL: Connecter un compte Telegram via Telethon et gérer les sessions

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-013 | Module Telethon client : création + connexion avec String session | | |
| TASK-014 | Route POST /api/mtproto/send-code (phone → envoi code) | | |
| TASK-015 | Route POST /api/mtproto/verify (code → sign_in → session) | | |
| TASK-016 | Stockage de la String session (chiffrée) en DB | | |
| TASK-017 | Background task : connexion persistante Telethon au démarrage | | |
| TASK-018 | UI : formulaire phone + code dans le dashboard (HTMX) | | |

### Phase 4 — Group Discovery

- GOAL: Récupérer les dialogs du compte Telegram et sélectionner les sources

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-019 | Route GET /api/groups → liste des dialogs (client.get_dialogs()) | | |
| TASK-020 | Route POST /api/groups/toggle → activer/désactiver un groupe source | | |
| TASK-021 | Route POST /api/groups/set-destination → définir groupe destination | | |
| TASK-022 | UI : page de configuration avec liste des groupes (checkboxes + destination) | | |

### Phase 5 — Relay (Scraper + Forwarder)

- GOAL: Brancher l'écoute des groupes sources → filtrage → forwarding temps réel

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-023 | Module relay : event handler events.NewMessage sur les groupes actifs | | |
| TASK-024 | Filtrage par mots-clés (vérification case-insensitive dans le texte) | | |
| TASK-025 | Cache mémoire de déduplication (Set des message.id vus, TTL configurable) | | |
| TASK-026 | Fonction de forwarding client.forward_messages() vers destination | | |
| TASK-027 | Route POST /api/relay/start + /api/relay/stop | | |
| TASK-028 | UI : statut du relay (actif/inactif) + indicateur de connexion | | |

### Phase 6 — Polish & Production

- GOAL: Robustesse, erreurs, déploiement

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-029 | Gestion des erreurs Telethon (disconnect, reconnect auto) | | |
| TASK-030 | Déploiement Fly.io (Dockerfile, fly.toml) | | |
| TASK-031 | README + instructions de déploiement | | |

## 6. Alternatives Considérées

- **ALT-001**: Node.js (Next.js + GramJS) — Stack initiale, abandonnée car Telethon est plus mature pour MTProto et un seul service Fly.io simplifie le déploiement.
- **ALT-002**: Bot API au lieu de MTProto — Impossible de scraper des groupes sans être admin. Rejeté.
- **ALT-003**: PostgreSQL classique (Supabase) au lieu de Neon — Neon offre un pooling serverless natif, mieux adapté à Fly.io.
- **ALT-004**: React/Vite au lieu de HTMX — SPA plus lourde pour une UI de config, HTMX suffit amplement.

## 7. Dépendances Python

- **DEP-001**: `fastapi` + `uvicorn[standard]` — Web framework + serveur ASGI
- **DEP-002**: `telethon` — Client MTProto pour Telegram
- **DEP-003**: `sqlalchemy[asyncio]` + `asyncpg` — ORM + driver PostgreSQL
- **DEP-004**: `jinja2` — Templates HTML
- **DEP-005**: `python-dotenv` — Variables d'environnement
- **DEP-006**: `itsdangerous` — Sessions signées (cookies)
- **DEP-007**: `cryptography` — Chiffrement de la string session

## 8. Fichiers Clés

- **FILE-001**: `app/main.py` — Point d'entrée FastAPI
- **FILE-002**: `app/routes/` — Routes (auth, mtproto, groups, relay)
- **FILE-003**: `app/templates/` — Templates Jinja2 (login, dashboard, config)
- **FILE-004**: `app/db/` — Modèles SQLAlchemy + session
- **FILE-005**: `app/telegram/` — Client Telethon + relay
- **FILE-006**: `app/config.py` — Config via Pydantic Settings

## 9. Tests

- **TEST-001**: Login admin (mot de passe correct / incorrect)
- **TEST-002**: Middleware protège les routes
- **TEST-003**: Connexion MTProto (phone → code → session)
- **TEST-004**: Récupération des dialogs
- **TEST-005**: Activation/désactivation d'un groupe source
- **TEST-006**: Déduplication mémoire (même message ignoré)
- **TEST-007**: Forwarding d'un message vers le groupe destination

## 10. Risques & Hypothèses

- **RISK-001**: Telethon peut être bloqué par Telegram si trop de requêtes — Respecter les rate limits, espacer les actions.
- **RISK-002**: Neon serverless peut avoir du cold start — Utiliser le pool async avec une connexion maintenue.
- **RISK-003**: La String session Telethon est sensible — Chiffrement AES en base obligatoire.
- **RISK-004**: Fly.io free tier a 3 VMs partagées — Suffisant pour un worker léger, mais surveiller la RAM.
- **ASSUMPTION-001**: L'admin utilise son propre compte Telegram, déjà membre des groupes à scraper.
- **ASSUMPTION-002**: Les groupes sources sont accessibles depuis le compte.
