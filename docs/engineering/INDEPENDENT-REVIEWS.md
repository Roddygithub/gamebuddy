# Revues indépendantes

## Revue 1 — corrections de capture, Coach, TTS et performance

- Auteur des changements: coordinateur GPT-6 Luna.
- Relecteur: instance Codex distincte, GPT-6.1 Terra, reasoning medium, en lecture seule.
- Portée: diff complet depuis `2a9cf0e`, limites de capture/privacy, cache concurrent,
  plafond JPEG, cadence Coach, tests et claims de performance. Le relecteur a inspecté le
  code réel; il n’a exécuté ni la suite ni les benchmarks.
- Checkout revu: `b21ee69`, état propre. Résultat de lecture seule, sans réseau ni session
  de jeu.
- Findings: trois défauts P1 (horloges cooldown incohérentes, identité Hyprland non revérifiée
  avant capture fraîche/cache expiré, course de démarrage TTS), trois défauts P2 (hash candidat
  pendant cooldown, hash de confirmation changée, annulation durant confirmation) et une
  affirmation erronée sur la mesure du premier son.
- Réponse: les sept points sont corrigés dans le diff courant. Les tests dédiés vérifient le
  cooldown après expiration, la reprise du candidat, le remplacement de fenêtre sans cache et
  cache expiré, le changement de frame de confirmation, l’arrêt pendant une capture bloquée,
  et l’annulation entre la vérification de génération et le lecteur. La documentation décrit
  `synthesis_s` comme délai de synthèse du premier segment, pas comme premier son audible.
- Vérification locale après corrections: `uv run pytest -q` — **203 passed**; Ruff check et
  format passent; `bash -n install.sh` et `git diff --check` passent.
- Résultat: findings corrigés, **revue de suivi indépendante requise avant PR**. Le suivi doit
  inspecter les modifications réelles et la sortie de tests, pas cette synthèse seule.

## Revue Gamekin (contexte, distincte d’une revue du code GameBuddy)

La revue indépendante GPT-6.1 du dossier Gamekin est intégrée dans
`~/Downloads/gamekin-analysis/ANALYSE.md` §12. Elle corrige notamment l’affirmation
« ReadProcessMemory absent », nuance modèles/fine-tuning et localisation, rectifie budgets
JPEG et limite la portée du self-test à sa fenêtre-fixture. Ces constats ne valident pas le
code GameBuddy et aucun artefact propriétaire n’est repris.
