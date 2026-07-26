# Projet Trade - Agent Telegram

## Vision

Application web permettant de se connecter via Telegram, configurer des groupes sources à scraper, et rediriger les informations vers un groupe de destination via un compte Telegram dédié.

## Architecture

1. **Auth** — Login admin via mot de passe (ADMIN_PASSWORD)
2. **MTProto** — Connexion du compte Telegram admin (phone + code, Telethon)
3. **Group Discovery** — Liste des groupes/dialogs du compte, sélection des sources
4. **Scraper** — Collecte des messages depuis les groupes sources (Telethon)
5. **Database** — Stockage config uniquement (Neon PostgreSQL + SQLAlchemy)
6. **Forwarder** — Envoi temps réel des messages vers le groupe de destination (pas de stockage DB des messages)

## Stack

- **Frontend** : Jinja2 + HTMX + Tailwind CSS + DaisyUI
- **Backend** : FastAPI (Python 3.12+)
- **Database** : Neon PostgreSQL + SQLAlchemy (async)
- **Telegram** : Telethon (MTProto, compte admin)
- **Runtime** : Python 3.12+ / asyncio
- **Package Manager** : uv (ou pip + venv)

## Workflow

1. Login admin (mot de passe) → session protégée
2. Connexion du compte Telegram (phone + code) → String session stockée
3. Récupération de la liste des groupes du compte → sélection des sources à scraper
4. Scraping + forwarding temps réel des groupes sélectionnés vers la destination (pas de stockage DB des messages)
5. IHM de sélection du groupe de destination + filtres optionnels

## Plan

Voir `plan/architecture-workflow-stack.md` pour le détail complet.
