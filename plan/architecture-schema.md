---
title: Schéma d'architecture Trade
---

# Schéma d'architecture — Trade

## 1. Architecture globale

```mermaid
graph TB
    subgraph "Fly.io (1 service — tout dans FastAPI)"
        FASTAPI[FastAPI App<br/>Uvicorn]
        TEMPLATES[Jinja2 + HTMX<br/>Login / Dashboard / Config]
        API[API Routes<br/>/auth /mtproto /groups /relay]
        WORKER[Telethon Client<br/>Écoute + Relay temps réel]
        FASTAPI --> TEMPLATES
        FASTAPI --> API
        FASTAPI --> WORKER
    end

    subgraph "Neon (PostgreSQL)"
        DB[(Neon DB<br/>Session + Groups + Config)]
    end

    subgraph "Telegram"
        TG_SRC[Groupes sources]
        TG_DST[Groupe destination]
    end

    ADMIN[Admin<br/>via navigateur]

    ADMIN -->|HTTPS| FASTAPI
    FASTAPI -->|SQLAlchemy async| DB
    WORKER -->|écoute messages| TG_SRC
    WORKER -->|forwardMessages| TG_DST
```

---

## 2. Workflow complet

```mermaid
sequenceDiagram
    actor Admin
    participant Web as FastAPI (Jinja2 + API)
    participant DB as Neon PostgreSQL
    participant Worker as Telethon Client
    participant TG as Telegram MTProto

    Admin->>Web: 1. Login (ADMIN_PASSWORD)
    Web->>Web: Cookie signé (itsdangerous)
    Web-->>Admin: Dashboard

    Admin->>Web: 2. Envoi numéro téléphone
    Web->>Worker: send_code_request(phone)
    Worker->>TG: Demander code
    TG-->>Admin: Code via Telegram
    Admin->>Web: 3. Saisie code
    Web->>Worker: sign_in(phone, code)
    Worker->>TG: Authentification
    TG-->>Worker: String session
    Worker->>DB: Stocker session chiffrée

    Admin->>Web: 4. Voir mes groupes
    Web->>Worker: get_dialogs()
    Worker->>TG: Récupérer dialogs
    TG-->>Worker: Liste groupes/channels
    Worker-->>Web: Liste retournée
    Web-->>Admin: Affiche groupes avec checkbox

    Admin->>Web: 5. Sélection sources
    Web->>DB: Sauve source_groups

    Admin->>Web: 6. Sélection destination
    Web->>DB: Sauve relay_config

    Admin->>Web: 7. Démarrer relay
    Web->>Worker: Lancer l'écoute

    loop À chaque nouveau message
        TG-->>Worker: events.NewMessage
        Worker->>Worker: Vérifie groupe source actif
        Worker->>Worker: Vérifie filtres keywords
        Worker->>Worker: Vérifie cache déduplication
        Worker->>TG: forward_messages(dest, msg)
    end
```

---

## 3. Stack technique

```mermaid
graph LR
    subgraph Python
        FASTAPI[FastAPI]
        UVICORN[Uvicorn]
        SQLA[SQLAlchemy async]
        TELETHON[Telethon]
        JINJA2[Jinja2]
        HTMX[HTMX + Alpine.js]
    end

    subgraph Infra
        FLY[Fly.io]
        NEON[Neon PostgreSQL]
    end

    subgraph CSS
        TW[Tailwind CSS]
        DAISY[DaisyUI]
    end

    FASTAPI --> UVICORN
    FASTAPI --> JINJA2
    FASTAPI --> SQLA
    FASTAPI --> TELETHON

    SQLA --> NEON
    JINJA2 --> HTMX
    JINJA2 --> TW
    TW --> DAISY

    FASTAPI --> FLY
```

---

## 4. Modèle de données (DB)

```mermaid
erDiagram
    mtproto_session {
        int id PK
        string phone_number
        text string_session "chiffré AES"
        boolean is_connected
        timestamp updated_at
    }

    source_groups {
        int id PK
        bigint group_id UK "Telegram chat_id"
        string title
        boolean is_active
        timestamp created_at
    }

    relay_config {
        int id PK
        bigint destination_group_id "nullable"
        string destination_title "nullable"
        text filter_keywords "optionnel, virgules"
        boolean is_running
        timestamp updated_at
    }
```

---

## 5. Flux des données (runtime)

```mermaid
flowchart LR
    TG1[Groupe A] -->|message| TELETHON
    TG2[Groupe B] -->|message| TELETHON
    TG3[Groupe C] -->|message| TELETHON

    TELETHON --> CHECK{Vérifications}
    CHECK -->|Groupe source actif ?| FILTER
    CHECK -->|Non| IGNORE[Ignoré]
    FILTER -->|Keywords match ?| DEDUP
    FILTER -->|Pas de filtre| DEDUP
    DEDUP -->|Déjà forwardé ?| IGNORE
    DEDUP -->|Nouveau| FORWARD[forward_messages]
    FORWARD --> TG_DEST[Groupe Destination]

    style IGNORE fill:#f88,stroke:#333
    style FORWARD fill:#8f8,stroke:#333
    style TELETHON fill:#58f,stroke:#333,color:#fff
    style TG_DEST fill:#fa0,stroke:#333
```

---

## 6. Structure du projet

```
trade/
├── app/
│   ├── main.py                 # App FastAPI + lifespan
│   ├── config.py               # Settings (ADMIN_PASSWORD, DB, API_ID, etc.)
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py             # /login, /logout
│   │   ├── mtproto.py          # /api/mtproto/send-code, /verify
│   │   ├── groups.py           # /api/groups, /toggle
│   │   └── relay.py            # /api/relay/start, /stop
│   ├── templates/
│   │   ├── base.html           # Layout global
│   │   ├── login.html          # Page login
│   │   └── dashboard.html      # Page principale
│   ├── db/
│   │   ├── __init__.py
│   │   ├── engine.py           # Engine SQLAlchemy async
│   │   └── models.py           # Définitions des tables
│   ├── telegram/
│   │   ├── __init__.py
│   │   ├── client.py           # Connexion Telethon
│   │   └── relay.py            # Event handler + forwarding
│   └── static/
│       └── css/                # Tailwind output si build local
├── pyproject.toml
├── uv.lock
├── .env.example
├── Dockerfile
├── fly.toml
└── README.md
```

---

## 7. Telethon — cœur du relay

```mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> Connecting: send_code / sign_in
    Connecting --> Connected: String session valide
    Connected --> Listening: attach events.NewMessage
    Listening --> Forwarding: on new message
    Forwarding --> Listening: done
    Listening --> Connecting: disconnect / reconnect
    Connecting --> Idle: max retries
```

---

## 8. Déploiement

| Service | Rôle | Plan |
|---------|------|------|
| **Fly.io** | FastAPI + Telethon (tout-en-un) | Free tier (3 VMs always-on) |
| **Neon** | PostgreSQL (config) | Free tier (0.5GB) |

---

## 9. Arbre des routes

```mermaid
graph TB
    ROOT["/"]
    ROOT --> LOGIN["/login"]
    ROOT --> DASH["/dashboard"]

    subgraph API
        APIPREFIX["/api"]
        APIPREFIX --> AUTH["/mtproto/send-code POST"]
        APIPREFIX --> VERIFY["/mtproto/verify POST"]
        APIPREFIX --> STATUS["/mtproto/status GET"]
        APIPREFIX --> GROUPS["/groups GET"]
        APIPREFIX --> TOGGLE["/groups/toggle POST"]
        APIPREFIX --> DEST["/groups/set-destination POST"]
        APIPREFIX --> RELAY_START["/relay/start POST"]
        APIPREFIX --> RELAY_STOP["/relay/stop POST"]
        APIPREFIX --> RELAY_STATUS["/relay/status GET"]
    end
```
