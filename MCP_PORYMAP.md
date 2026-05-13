# porymap-mcp — Vision et plan stratégique

> Document de référence pour le projet `porymap-mcp`. À utiliser comme source de vérité dans les sessions Claude Code et les futures discussions stratégiques. À mettre à jour au fur et à mesure de l'avancement.

## 1. Contexte et origine

Ce projet est né en parallèle d'un projet personnel de création d'un ROM hack Pokémon Emerald (base : `pokeemerald-expansion` de rh-hideout, fork qui ajoute Gen 1-9, Mégas et QoL modernes). L'auteur (Hugo Martins) construit son propre jeu dans l'esprit d'**Emerald Imperium** ou **Radical Red**, avec sa propre région et son scénario.

Lors du setup, la question s'est posée : "comment faire piloter par Claude l'outil de référence pour l'édition de maps (Porymap), de la même manière qu'on lui fait piloter le code ?"

Aucune solution n'existait. D'où ce projet.

## 2. Le problème à résoudre

**Porymap** est l'éditeur de maps de référence pour les projets de décompilation Pokémon Gen 3 (`pokeemerald`, `pokefirered`, `pokeruby`, et leurs forks comme `pokeemerald-expansion`). C'est un outil graphique en C++/Qt, qui édite directement les fichiers du projet (pas la ROM).

**Limites pour un workflow assisté par IA :**
- Pas de mode CLI ou headless (issue ouverte depuis 2021, non implémentée : `huderlem/porymap#364`)
- Pas d'API externe pour qu'un programme tiers envoie des commandes
- L'API JavaScript interne ne fonctionne que pendant que Porymap est ouvert et déclenchée manuellement
- Aucun MCP n'existe pour Porymap (vérifié en mai 2026)

**Conséquence** : un agent IA comme Claude Code peut modifier les fichiers de map à la main (en parsant les `.bin` lui-même), mais sans visualisation, sans connaissance des prefabs (Pokémon Center, Pokémart, etc.), et sans retour visuel.

## 3. La vision : MCP Porymap niveau 3

L'ambition est de construire un **serveur MCP** (Model Context Protocol) qui expose à un agent IA un ensemble de tools pour manipuler des projets pokeemerald, avec **retour visuel** à l'agent.

À terme, l'expérience cible est :
1. L'utilisateur dit à Claude "crée une petite ville côtière de 20x15 avec un port, 3 maisons et un marché"
2. Claude appelle les tools du MCP pour générer la map
3. Le MCP retourne à Claude un rendu image de la map créée
4. Claude juge le résultat, propose des ajustements, itère
5. L'utilisateur valide visuellement (dans Porymap ouvert en parallèle, ou via les images retournées)

## 4. Les 3 niveaux d'ambition

Le projet sera construit en paliers. Chaque palier est utilisable individuellement.

### Niveau 1 — MCP "Filesystem"
- Le MCP expose des tools haut-niveau pour manipuler les fichiers de map d'un projet pokeemerald
- Pas besoin que Porymap soit ouvert
- Claude écrit, le MCP modifie les fichiers, l'utilisateur ouvre Porymap après pour visualiser
- **Effort estimé** : 2-3 jours

### Niveau 2 — MCP "Porymap en temps réel"
- Niveau 1 + mécanisme pour que Porymap (ouvert en parallèle) réagisse en temps réel
- L'utilisateur voit la map se construire sous ses yeux pendant que Claude génère
- Probablement implémenté via le file-watching natif de Porymap, ou un script Porymap JavaScript dédié
- **Effort estimé** : 2-3 jours supplémentaires

### Niveau 3 — MCP "Vision intégrée"
- Niveau 2 + le MCP rend la map en image PNG et la renvoie à Claude dans la réponse du tool call
- Claude peut littéralement voir ce qu'il a fait et critiquer son propre travail
- Nécessite un renderer Python qui compose une image à partir des tilesets + layout
- **Effort estimé** : 3-5 jours supplémentaires

**Le niveau 3 est l'objectif final.** Mais les niveaux 1 et 2 sont des paliers fonctionnels, pas des prototypes jetables.

## 5. Architecture technique envisagée

### Stack
- **Langage** : Python 3.11+ (cohérent avec l'écosystème ML et les libs MCP)
- **Framework MCP** : FastMCP (l'API recommandée pour les serveurs MCP en Python)
- **Tests** : pytest
- **Packaging** : pyproject.toml, publication PyPI à terme
- **Dépendances clés** : Pillow (pour le renderer image), peut-être pyqt6 pour analyser certains formats Porymap

### Structure du repo

```
porymap-mcp/
├── src/
│   └── porymap_mcp/
│       ├── __init__.py
│       ├── server.py              # Point d'entrée MCP
│       ├── tools/                 # Les tools exposés à Claude
│       │   ├── maps.py            # create_map, paint_tile, ...
│       │   ├── events.py          # add_warp, add_npc, ...
│       │   ├── tilesets.py        # list_metatiles, get_prefab, ...
│       │   └── rendering.py       # render_map (niveau 3)
│       └── parsers/               # Lecture/écriture des fichiers projet
│           ├── mapbin.py          # Format .bin des layouts
│           ├── mapjson.py         # map.json
│           └── tileset.py         # tilesets et metatiles
├── tests/
├── docs/
├── examples/
├── pyproject.toml
├── README.md
├── ROADMAP.md
└── CLAUDE.md
```

### API exposée à Claude (esquisse, à raffiner après le POC manuel)

**Tools de découverte :**
- `list_maps(project_path)` — liste les maps d'un projet
- `get_map_info(project_path, map_name)` — métadonnées d'une map
- `list_metatiles(project_path, tileset_name)` — liste des metatiles d'un tileset
- `list_prefabs(project_path)` — liste des prefabs disponibles (Pokémon Center, etc.)

**Tools de création/modification :**
- `create_map(project_path, name, width, height, primary_tileset, secondary_tileset)` — crée une nouvelle map vide
- `paint_metatile(project_path, map_name, x, y, metatile_id, collision, elevation)` — peint un metatile
- `paint_prefab(project_path, map_name, prefab_name, x, y)` — pose un prefab complet
- `paint_rectangle(project_path, map_name, x1, y1, x2, y2, metatile_id)` — remplit une zone
- `set_border(project_path, map_name, metatile_ids)` — définit la bordure

**Tools d'events :**
- `add_warp(project_path, map_name, x, y, dest_map, dest_warp_id)` — ajoute un warp
- `add_object_event(project_path, map_name, x, y, gfx_id, movement, script)` — ajoute un NPC
- `add_sign(project_path, map_name, x, y, script)` — ajoute un panneau

**Tools de structure projet :**
- `register_map(project_path, map_name, map_group)` — ajoute la map aux index (map_groups.json, layouts.json, etc.)

**Tools de rendu (niveau 3) :**
- `render_map(project_path, map_name)` — retourne l'image PNG de la map

## 6. Roadmap détaillée

### Phase 0 — POC manuel express (préliminaire, dans `pokeemerald-expansion`)
- Créer manuellement une mini-map dans Porymap (10x10, 1 PC, 1 warp, 1 NPC)
- **Objectif** : comprendre Porymap suffisamment pour bien spec le MCP
- **Livrable** : un fichier `.claude/POC_LEARNINGS.md` listant ce qui frustre/ce qui gagne du temps
- **Durée** : 1 demi-journée à 1 journée

### Phase 1 — Spec détaillée du MCP (session chat dédiée)
- Affiner l'API des tools sur la base du POC
- Choisir les abstractions (tile par tile ? prefab par prefab ? ville entière ?)
- Choisir le format de specs (JSON ? YAML ?)
- Définir les critères de "fait" pour chaque palier
- **Livrable** : ROADMAP.md, CLAUDE.md, premier prompt Claude Code
- **Durée** : 2h de chat

### Phase 2 — Implémentation Palier 1 (MCP Filesystem)
- Setup du repo `porymap-mcp` sur GitHub (public dès le départ)
- MCP server en Python avec FastMCP
- Implémentation des tools de découverte et de modification (sans rendering, sans temps réel)
- Tests unitaires
- Documentation README + exemples d'usage
- **Livrable** : MCP utilisable dans Claude Code, capable de créer une vraie map
- **Durée** : 2-3 jours

### Phase 3 — Implémentation Palier 2 (temps réel Porymap)
- Mécanisme de hot-reload : forcer Porymap à recharger après modif
- Probablement un script Porymap JavaScript qui réagit aux changements de fichiers
- Tests d'intégration avec Porymap ouvert
- **Livrable** : on voit la map se construire sous nos yeux dans Porymap
- **Durée** : 2-3 jours

### Phase 4 — Implémentation Palier 3 (renderer + vision)
- Renderer Python : lire les tilesets, composer les metatiles, produire un PNG
- Intégration dans les tool calls (retour image en base64)
- Tests visuels (comparer le rendu maison vs export Porymap)
- **Livrable** : Claude voit ce qu'il génère
- **Durée** : 3-5 jours

### Phase 5 — Publication
- Documentation complète
- Publication sur PyPI : `pip install porymap-mcp`
- Annonce sur la communauté ROM hack (Discord pret, PokéCommunity en mode contribution, etc.)
- Annonce sur la communauté MCP (Discord Anthropic, Twitter/X, LinkedIn)
- **Durée** : 2-3 jours

## 7. Pourquoi ce projet a de la valeur au-delà du jeu

- **Originalité technique** : premier MCP pour un outil de game dev rétro
- **Cas d'usage concret** : pas un Nème wrapper d'API REST
- **Public cible** : la communauté ROM hack Pokémon (estimée à 10-50K personnes actives), la communauté MCP en expansion
- **Apprentissage profond** : MCP, FastMCP, formats binaires Gen 3, écosystème pokeemerald
- **Portfolio** : projet open source publiable, mentionnable en entretien, démontrant agentic dev + game dev + maîtrise MCP

## 8. Contraintes et risques

### Contraintes techniques
- Format binaire `.bin` documenté (cf. `pret/pokeemerald/include/global.fieldmap.h`)
- Format `map.json` documenté (Porymap, doc en ligne)
- Tilesets : PNG + binaire de metatiles, documenté
- Pas de SDK officiel Porymap, donc on doit reverse-engineer ce qu'il fait

### Risques projet
- **Sous-estimation du temps** : 2 semaines effectives peuvent devenir 1-2 mois sur agenda réel
- **Risque de scope creep** : envie de tout faire trop bien dès le début → bloquer un palier
- **Risque communauté** : politique anti-IA générative de PokéCommunity, mais ne concerne pas le code et les outils, seulement le contenu visiblement IA. À surveiller.
- **Risque dépendance Porymap** : si Porymap évolue significativement (nouveau format de fichier), il faudra suivre

### Mitigation
- Faire des paliers livrables individuellement (toujours quelque chose d'utilisable)
- Séparer strictement de `pokeemerald-expansion` (deux repos, deux histoires git)
- Versionner sur PyPI dès qu'un palier est stable
- Documenter au fur et à mesure, pas en bloc à la fin

## 9. Relation avec le projet de jeu

Le projet `porymap-mcp` est **strictement indépendant** du projet de jeu `my-pokemon-rom-hack` (repo privé sur le GitHub d'Hugo).

- `porymap-mcp` : outil open source, publiable, réutilisable pour tout projet pokeemerald
- `my-pokemon-rom-hack` : jeu personnel privé, utilisateur du MCP

Le MCP peut être développé même si le jeu est abandonné, et vice versa.

## 10. Organisation du workflow Claude

Trois niveaux d'interaction Claude :

1. **Chat Claude.ai** (web) — cadrage stratégique, décisions majeures, sessions de spec
2. **Claude Code dans `my-pokemon-rom-hack/`** — développement du jeu (création de maps, scripts, équipes, etc.)
3. **Claude Code dans `porymap-mcp/`** — développement du MCP (code Python, tests, doc)

Chaque projet a son propre `CLAUDE.md` adapté à son contexte.

## 11. Glossaire rapide

- **MCP** (Model Context Protocol) — protocole d'Anthropic permettant à un LLM d'utiliser des tools externes via un serveur intermédiaire
- **FastMCP** — framework Python pour construire des serveurs MCP
- **pokeemerald-expansion** — fork du repo officiel `pret/pokeemerald` maintenu par `rh-hideout`, qui ajoute Gen 1-9, Mégas, QoL modernes
- **Porymap** — éditeur de maps cross-platform pour les projets pokeemerald, pokefirered, pokeruby
- **Metatile** — bloc de 16x16 pixels composé de 4 tiles 8x8, unité de base des maps
- **Prefab** — groupe pré-défini de metatiles formant un objet (Pokémon Center, Pokémart, maison, etc.)
- **Layout** — l'ensemble metatiles + collision + élévation d'une map, stocké en `.bin`
- **Tileset** — bibliothèque de metatiles utilisable par une map (chaque map utilise un primaire + un secondaire)

## 12. Notes vivantes

À mettre à jour au fur et à mesure :

- **POC Test 0 (terminé)** : modification d'équipe de dresseur réussie. Pipeline `.party` → build → ROM validé.
- **POC Phase 0** : à lancer.
- **Décision prise (12 mai 2026)** : viser le niveau 3, par paliers progressifs, en deux repos séparés.

---

*Dernière mise à jour : 12 mai 2026*
*Auteur : Hugo Martins*
*Source de vérité — toute évolution doit passer par ce document.*
