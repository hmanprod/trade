---
goal: Remplacer la destination globale unique par des destinations par groupe source, choisies depuis n'importe quel compte connecté
version: 1.0
date_created: 2026-08-06
owner: backend-frontend
status: 'Planned'
tags: feature, data-model, migration, relay, UX, destination
---

# Introduction

Le relais actuel ne gère qu'**une seule destination** (`RelayConfig.destination_group_id`) partagée par toutes les sources actives. La page « Groupes & Canaux Sources » mélange donc les rôles (un seul badge "DESTINATION", un champ global), d'où la confusion. L'objectif est de passer à un modèle **destination par groupe source** : chaque groupe source peut avoir sa propre destination, différente de celle d'une autre source, ou partager une même destination avec d'autres sources. La destination peut être un groupe du **même compte** ou d'un **autre compte connecté** (tant que la session d'émission y est membre).

## Problèmes utilisateur adressés
- **PRB-001** — Pouvoir définir une **destination différente par groupe source**.
- **PRB-002** — Permettre à **plusieurs sources de partager la même destination**.
- **PRB-003** — N'afficher que **3 groupes** → il faut tous les afficher.
- **PRB-004** — La destination peut être un groupe du **même compte** ou d'un **autre compte connecté**.
- **PRB-005** — Ne pas raisonner à l'écran en « compte source » vs « compte destination » : garder une seule liste de comptes connectés, piocher dedans pour les sources ET pour la destination.
- **PRB-006** — Pouvoir définir une destination en un seul geste : choisir un compte → choisir un groupe de destination.

## 1. Requirements & Constraints

- **REQ-001** : Chaque `SourceGroup` porte sa propre destination `(destination_group_id, destination_session_id)`, nullable.
- **REQ-002** : **Pas de destination par défaut globale.** Une source sans destination explicite n'est pas reléguée (elle est marquée « À définir » dans l'UI).
- **REQ-003** : Deux sources peuvent référencer le même `destination_group_id` (partage permis).
- **REQ-004** : Récupérer et afficher **tous** les dialogues (groupes/canaux) de chaque compte (pagination complète).
- **REQ-005** : La destination peut venir de n'importe quelle session connectée, du moment que la session d'émission de la source est **membre** du groupe destination.
- **REQ-006** : Migration auto de la base (motif déjà présent dans `app/main.py`).
- **SEC-001** : Aucun secret en clair ; ne pas altérer les `string_session`.
- **CON-001** : Contrainte Telethon : `forward_messages` est exécuté par le **client source** (`app/telegram/relay.py`). Une destination sur un autre compte fonctionne seulement si la session d'émission y est membre (cas d'un compte relais dédié membre de tout).
- **CON-002** : Conserver le modèle HTMX actuel (réponses HTML partielles et swaps).
- **CON-003** : Conserver les guards `get_admin_user` sur chaque route.

## 2. Implementation Steps

### Implementation Phase 1 — Modèle & migration

- GOAL-001: Ajouter la destination par source-group au modèle et à la migration auto.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Ajouter à `SourceGroup` dans `app/db/models.py` : `destination_group_id: Mapped[int|None] = mapped_column(BigInteger, nullable=True)` et `destination_session_id: Mapped[int|None] = mapped_column(Integer, ForeignKey("mtproto_session.id"), nullable=True)`. | |  |
| TASK-002 | Ajouter les deux colonnes au tableau de migrations dans `app/main.py` (motif `information_schema.columns`), avec les types `BIGINT` / `INTEGER REFERENCES mtproto_session(id)`. | |  |
| TASK-003 | `RelayConfig.destination_group_id` devient inutilisé : on ignore ce champ à la lecture (on ne le supprime pas de la table, la colonne reste en base mais n'est plus jamais utilisée). | |  |

### Implementation Phase 2 — Forwarder multi-destination

- GOAL-002: Servir la destination de chaque source (explicite uniquement, pas de fallback).

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-004 | Modifier `app/telegram/relay.py` : `start_relay(source_ids, dest_map, keywords)` où `dest_map: dict[session_id, dict[source_group_id, dest_id]]`. | |  |
| TASK-005 | Dans le `handler`, `dest_id = dest_map.get(_sid, {}).get(msg.chat_id)` ; si `dest_id` est None, **ne pas forwarder** (source sans destination). | |  |
| TASK-006 | Journaliser `(session_id, chat_id, dest_id)` à chaque forward (INFO) pour le débogage multi-destination. | |  |

### Implementation Phase 3 — Afficher TOUS les dialogues (PRB-003)

- GOAL-003: Charger la liste complète des groupes/canaux par compte.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-007 | Dans `app/routes/groups.py`, remplacer `client.get_dialogs()` par une itération complète : `async for d in client.iter_dialogs()` (aucun `limit`), ou `client.get_dialogs(limit=None)`. | |  |
| TASK-008 | Conserver le filtre `d.is_group or d.is_channel` ; exclure les dialogues privés/users puisque seuls les groupes comptent. | |  |
| TASK-009 | Vérifier en test que le compte a bien obtenu **tous** ses dialogues (pas de plafond à l'affichage — cf TEST-006). |

### Implementation Phase 4 — API de routes destinations

- GOAL-004: Nouvelles routes pour définir / effacer une destination par source.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-010 | Refondre `POST /api/groups/set-destination` en `POST /api/groups/{session_id}/destination` avec `source_group_id`, `dest_session_id`, `dest_group_id`, `dest_title`, `source_title`. Si `dest_group_id == 0` → effacer la destination source (retour au défaut). | |  |
| TASK-011 | Garantir qu'une route `clear-destination` (+ simple) efface une destination source. | |  |
| TASK-012 | `GET /api/groups` renvoie tous les dialogues + la destination courante par source. | |  |
| TASK-012b | Nouvelle route pour alimenter le double-picker destination : `GET /api/groups/destination-options` renvoyant `{comptes: [{session_id, label, groupes: [{id, titre}]}]}` (tous comptes connectés). | |  |
| TASK-012c | Route d'action groupée : `POST /api/groups/batch-destination` acceptant `source_group_ids[]`, `dest_session_id`, `dest_group_id` ; applique la même destination à toutes les sources listées. | |  |

### Implementation Phase 5 — Upsert SourceGroup

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-013 | Dans `toggle_source`, ne pas réinitialiser `destination_group_id/session_id` (préserver). | |  |
| TASK-014 | À la création d'une `SourceGroup` : `destination_group_id = None`, `destination_session_id = None` (défaut). | |  |

### Implementation Phase 6 — UI / UX « Groupes & Canaux Sources »

- GOAL-006: Diriger la pioche via une seule liste de comptes : sélection multiples sources, puis destination par groupe (ou groupée).

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-015 | Nouveau sélecteur d'ajout de sources : un `<select>` de **compte** (sessions connectées) filtrant la liste de groupes, avec **cases à cocher multiples** sur les groupes. Bouton « /ajouter les groupes sélectionnés en sources actives ». | |  |
| TASK-016 | La bonne liste des groupes « à scraper » s'affiche quand le compte est choisi (reste du comportement actuel `#groups-list`), mais avec cases à cocher multiples + bouton d'action groupée. | |  |
| TASK-017 | En-têtes de tableau clairs : « Groupe / Canal » · « Scraper (actif) » · « Destination ». Supprimer la case/ligne « Action de destination » ambiguë hors du contexte. | |  |
| TASK-018 | Pour CHAQUE groupe de la liste, un sélecteur compact « Définir destination » (reprenant PRB-006) : un dropdown **compte** qui filtre un second dropdown **groupe** ; valider écrit la destination et affiche le libellé `→ <titre> (@<compte>)` côté ligne. | |  |
| TASK-019 | Actions groupées en en-tête : « Appliquer aux sélectionnés » et « Appliquer à tous » ouvrant le même double-picker compte→groupe (réutilise TASK-018). | |  |
| TASK-020 | Retour à **aucune destination** via un petit bouton ✕ sur une assignation (la source redevient « À définir »). | |  |
| TASK-021 | Badges sur la ligne source : « À définir » si pas de destination, sinon le libellé de destination (et « Partagé » si deux sources pointent vers le même groupe — REQ-003). | |

### Implementation Phase 7 — Statut & commandes

- GOAL-007: Aligner le statut du relais avec le multi-destination.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-022 | `app/routes/relay.py` : construire `dest_map` uniquement depuis les `SourceGroup` **avec** une destination explicite ; les sources sans destination sont exclues du relais (ou listées comme à définir). | |  |
| TASK-023 | `app/routes/status.py` : afficher le nombre de sources actives sans destination (« à définir ») + nombre de destinations distinctes actives. | |  |

## 3. Alternatives

- **ALT-001** : Table d'association dédiée `SourceDestination`. Non retenue : stocker directement deux colonnes sur `SourceGroup` est plus simple et suffit.
- **ALT-002** : Destination « par compte » (mêmes dest pour toutes les sources d'un compte) plutôt que par groupe. Non retenu : PRB-001/002 demandent explicitement la granularité par groupe.
- **ALT-003** : Garder une « destination par défaut globale » (ancien `RelayConfig.destination_group_id`). Retiré : l'utilisateur veut rester simple et focus — chaque source porte sa destination, pas de fallback global.

## 4. Dependencies

- **DEP-001**: Telethon `iter_dialogs`/`get_dialogs` pour récupérer tous les dialogues (PRB-003).
- **DEP-002**: SQLAlchemy async + migrations incrémentales existantes dans `app/main.py`.
- **DEP-003**: Contrainte Telegram : session d'émission membre de la destination (CON-001). Aucun nouveau paquet.
## 5. Files

- **app/db/models.py** — colonnes `destination_group_id`, `destination_session_id`.
- **app/main.py** — migrations auto (2 colonnes).
- **app/telegram/relay.py** — map par-destination, résolution.
- **app/routes/groups.py** — fetch-all + nouvelles routes set/clear batch.
- **app/routes/relay.py** — construire `dest_map` au démarrage.
- **app/static/app.css et app/templates/dashboard.html (ou partial HTMX)** — revue UX : sélecteur compte→groupes (sources), double-picker compte→groupe (destination), actions groupées, badges « À définir »/destination/« Partagé ».
- **app/routes/status.py** — résumé destinations.

## 6. Testing

- **TEST-001** : source **sans** destination → n'est pas forwardée (et badge « À définir »).
- **TEST-002** : deux sources avec des destinations différentes → chaque source est transférée vers sa destination.
- **TEST-003** : deux sources partageant la même destination → aucune erreur, messages bien regroupés.
- **TEST-004** : filtrage par mots-clés toujours appliqué même avec destination explicite.
- **TEST-005** : migration exécutée 2× → pas d'erreur.
- **TEST-006** : `GET /api/groups` renvoie tous les dialogues, sans plafond (PRB-003).
- **TEST-007** : effacer la destination d'une source → badge « À définir », pas de forward.
- **TEST-008** : « Appliquer aux sélectionnés » / « Appliquer à tous » écrit la destination sur plusieurs sources en une requête batch.
- **TEST-009** : le double-picker destination (`destination-options`) ne propose que les groupes des comptes connectés, et vaut pour le compte sélectionné.

## 7. Risks & Assumptions

- **RISK-001** : si une session source n'est pas membre de la destination choisie sur un autre compte, `forward_messages` échouera. → Mitigation : valider côté UI que la session source est bien membre, et logger l'erreur proprement.
- **ASSUMPTION-001** : la destination est obligatoirement stockée sur chaque `SourceGroup` qui doit être reléguée ; pas de fallback global. `RelayConfig.destination_group_id` reste en base mais n'est plus lu.

## 8. Related Specifications / Further Reading

- `plan/architecture-workflow-stack.md` (réf AGENTS.md)
- Telethon `Client.forward_messages` (contrainte CON-001).
- `app/main.py` — motif de migrations incrémentales.