# Backlog d’ingénierie

Backlog borné issu du différentiel du 20 novembre 2026. Les items clos restent visibles
pour l’audit; les éléments qui dépendent d’une vraie partie ne sont pas simulés comme faits.

| ID | Priorité / état | Preuve et impact utilisateur | Critères d’acceptation et vérification | Implémentation / revue |
|---|---|---|---|---|
| P0-1 | **Clos** | Le cache image de l’app n’était pas lié à la cible et pouvait survivre à un changement de fenêtre; une frame d’un autre jeu pouvait partir au modèle. | Cache lié à l’adresse, `stableId`, `app_id`; effacement à la sélection/perte; identité vérifiée avant réutilisation; changement en cours de capture retourne `None`. Tests `test_capture_cache.py`. | `ui/app.py`, test de régression. Revue indépendante Terra requise avant intégration. |
| P0-2 | **Clos** | Après une capture Hyprland échouée, l’ancien cache pouvait rester utilisable; la scène envoyée pouvait ne plus correspondre au jeu. | Invalider le cache sur chaque échec; aucun fallback bureau; erreurs des backends conservées. Tests capture existants + cache. | `ui/app.py`, `capture/hyprland.py` non modifié. Revue indépendante Terra. |
| P1-1 | **Clos** | L’encodeur annonçait un plafond JPEG sans le garantir pour une frame très détaillée; CLI et app n’appliquaient pas toujours la même limite. | Toute sortie avec budget ≥1 Kio respecte le plafond; budget impossible explicite; CLI transmet le même réglage. Test haute entropie. | `capture/base.py`, `cli.py`. Mesure synthétique dans `PERFORMANCE-RESULTS.md`. |
| P1-2 | **Clos** | Une réponse lente pouvait laisser le Coach sans pause entre rattrapages et provoquer des appels rapprochés. | Si un tick dépasse les échéances, abandonner les intervalles manqués et attendre la prochaine cadence; test à horloge contrôlée. | `coach/pipeline.py`; revue Terra (même mission que capture). |
| P1-3 | **À valider en session** | Le dHash et la confirmation rapide ne prouvent pas qu’un état de Dota Underlords est bien lu ni que la décision est encore ouverte. | 20–30 captures réelles annotées, cas tenus à part pour validation; mesurer ownership, ressources, options, conseils fondés, silence utile, fenêtres expirées et latence. Aucun conseil critique erroné sur holdout avant d’élargir l’usage. | Évaluation avec le harness existant; nécessite une fenêtre gameplay contrôlée et l’accord au moment de la capture. Pas de responsable IA avant ce corpus. |
| P1-4 | **Expérience à décider plus tard** | L’OCR local pourrait ancrer nombres/noms, mais les polices et effets de jeu peuvent créer des valeurs erronées. Tesseract 5.5 est installé mais absent des dépendances. | Comparer, sur un corpus annoté, exactitude des valeurs et rappel des erreurs; le gate doit rejeter les conflits plutôt que préférer aveuglément OCR ou VLM. Gains latence/payload mesurés. | Rechercher options natives/Tesseract en lecture seule avant implémentation; revue de conception Terra si retenu. |
| P1-5 | **Expérience à décider plus tard** | La région utile et la fraîcheur d’un résultat web ne sont pas accompagnées d’un contrat source/version. | Mesurer OCR/lecture sur overview seul vs overview+crops; chaque fait de patch versionné cite source/date; cas de patch obsolète échoue explicitement. | Aucun framework RAG; extension du harness existant si corpus versionné disponible. |
| P2-1 | **Clos** | Le test de langue dépendait des variables `LC_ALL`/`LC_MESSAGES` présentes sur le poste et échouait même avec `LANG` forcé. | Test isole ses trois variables d’environnement; toutes les variantes `es_MX`, `pt_PT`, `zh_CN` passent. | `tests/test_languages_omarchy.py`; pas de changement de comportement produit. |
| P2-2 | **Clos** | README et architecture décrivaient encore une capture `grim -g` sur Hyprland, alors que le code prend la fenêtre directe. | Documentation mentionne `stableId`, absence de fallback écran, limites des autres backends et portée du cache. | `README.md`, `docs/ARCHITECTURE.md`. |

## Hors backlog pour l’instant

- Fine-tuning, serveur séparé, OCR requis, SDK multi-jeux, modèles locaux toujours actifs,
  apprentissage du joueur et auto-détection par catalogue: aucune mesure ne justifie leur coût.
- La collecte d’un jeu réel reste une validation utilisateur à planifier séparément, pas un
  test déclenché en arrière-plan.
