# Baseline de performance

## Instantané

- Commit `2a9cf0e81c1bde17152da92a9cef5e9c50235d50`, branche `main`, version déclarée
  `0.7.0`; `origin/main` au même SHA le 20 novembre 2026.
- GitHub CI du commit: run `43194306514`, conclusion `success`; aucun PR ouvert.
- OS Omarchy 4.5.0, noyau `7.2.15-1-omarchy`; Python du venv `3.13.16` (Python système
  `3.14.8`), uv `0.12.24`.
- Machine: Intel Core i7-6700K, 4 cœurs/8 threads, RAM 15 Gio; GTX 1060 6 Gio + Intel
  HD 530. Outils détectés: Hyprland `0.56.2-4`, grim `1.5.0-2`, Tesseract `5.5.3`.
- La session utilisateur expose Hyprland/Wayland via `systemctl --user show-environment`;
  le processus de développement n’a pas directement ces variables. Aucun jeu GameBuddy
  n’était actif pendant l’inspection.
- Configuration locale non secrète: provider `codex`, modèle `gpt-6-luna`, effort `medium`;
  aucun override de modèle Coach. Pas de clé, jeton ou identifiant privé copié dans ce rapport.

## Tests de départ

`uv run pytest -q` avant les corrections de cette mission: **189 passed, 1 failed**. L’échec
était `test_omarchy_aliases_and_unset_file`: le runner héritait de `LC_ALL`/`LC_MESSAGES`,
qui ont priorité sur `LANG`; le test ne neutralisait que `LANG`. La correction isole le test,
elle ne change pas la sélection de langue de l’application.

Après corrections: voir `PERFORMANCE-RESULTS.md` pour le résultat complet. Les exemples de
`evals/coach` présents sont dessinés/synthétiques; aucun appel à un modèle distant ni aucune
capture de jeu n’a servi de baseline de qualité dans cette phase.

## Portée et limites

Cette baseline est issue du code et de tests locaux, pas d’une session de jeu. Aucun chiffre
de latence Codex/LLM, de premier token, de premier son, de stabilité de frame réelle ou de FPS
n’est établi. Le benchmark JPEG est un micro-benchmark sans hôte au repos; sa variabilité est
à considérer. L’ordinateur reste utilisable pendant les tests unitaires et l’analyse statique.
