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

## Revue 2 — suivi TTS et lifecycle Coach

- Relecteur: instance Codex distincte, GPT-6.1 Terra, reasoning medium, lecture seule.
- Checkout inspecté: `d7e99bf`, diff réel et suite locale 203 tests exécutée par le relecteur.
- Les corrections de la revue 1 ont été vérifiées; deux objections supplémentaires restent
  à traiter: (1) le jeton TTS était encore créé dans le worker, donc une tâche déjà mise en
  file pouvait commencer après annulation; (2) un `start()` pendant que le thread stoppé est
  encore bloqué ne redémarrait pas le Coach.
- Réponse: le jeton TTS est assigné avant la mise en file, avec un test annulant une réponse
  en attente; chaque cycle Coach possède son propre Event d’arrêt et peut redémarrer pendant
  que l’ancien tick se termine. Suite après ces deux correctifs: **205 tests passés**.

## Revue 3 — isolation des cycles et état d’écoute

- Relecteur: GPT-6.1 Terra, reasoning high, lecture seule; checkout `4a344c4`, diff inspecté
  depuis `2a9cf0e`.
- Findings: un ancien cycle stoppé pouvait encore modifier `_last_hash` ou lancer une
  évaluation après une capture bloquée, en partageant cet état avec le nouveau cycle (**P1**);
  une annulation TTS dans la transition vers `speaking` pouvait remettre le listener en pause
  après l’annulation (**P2**). Le reviewer a aussi relevé un claim trop fort sur le rejet des
  flashes HUD.
- Réponse: les ticks sont maintenant sérialisés; le stop event propre au cycle est vérifié
  après capture et évaluation; le hash n’est mémorisé qu’après une évaluation non annulée. Les
  transitions de génération, état de lecture et pause du listener partagent le verrou speech.
  La documentation décrit le dHash comme filtre approximatif sans garantie sur les flashes.
- Tests ajoutés: ancien cycle arrêté pendant capture puis nouveau cycle vérifié sans appel
  raisonneur provenant de l’ancien; annulation pendant la transition speech. `uv run pytest -q`
  passe maintenant **206 tests**; Ruff, format, syntaxe shell et diff-check passent.
- Résultat: ces deux findings et le claim ont reçu une réponse; **nouvelle revue indépendante
  obligatoire avant PR** pour vérifier les corrections et l’absence de finding résiduel.

## Revue 4 — voix Coach, toggles et callback IPC

- Relecteur: GPT-6.1 Terra, reasoning high, lecture seule; checkout `3f73a40`, diff complet
  depuis le SHA de main.
- Findings: le callback voix Coach appelait `_speak` avec l’ancienne signature (**P1**);
  toggle bouton/IPC se fondait sur `thread.is_alive()` et n’annulait pas un arrêt en cours
  (**P2**); callback de livraison gardait son verrou pendant `sendall` IPC qui peut attendre
  le timeout de chaque subscriber (**P2**).
- Réponse dans le diff suivant: callback voix redirigé vers `_queue_speech`; état demandé du
  Coach mémorisé dans `_coach_enabled`; diffusion IPC passée en tâche thread-pool, hors du
  verrou de livraison. Trois tests vérifient ces chemins, dont un broadcast bloquant.
- Contrôles locaux après les corrections: `uv run pytest -q` **209 passed**; Ruff, format,
  `bash -n install.sh` et `git diff --check` passent. Le reviewer n’a pas exécuté les tests.
- Statut: en attente d’une nouvelle lecture indépendante de ces corrections avant PR.

## Revue 5 — cycle IPC, arrêt et état de statut

- Relecteur: GPT-6.1 Terra, reasoning high, lecture seule; checkout `93703a3`, diff depuis
  le SHA de main. Pas de test exécuté par le reviewer; il a inspecté statiquement les tests.
- Findings: conseil IPC mis en file pouvait être diffusé après désactivation (P2); fermeture
  de l’application pouvait attendre le verrou tenu par un `sendall` bloqué (P2); snapshot
  indiquait `coach=true` sur un thread qui finissait après stop.
- Réponse dans le diff courant: generation + état demandé sous `_coach_lock`, chaque worker
  IPC valide la generation avant envoi; `IPCServer.broadcast()` envoie sur un snapshot sans
  tenir le verrou global, et `stop()` retire les abonnés puis `shutdown`/ferme les sockets;
  `status_snapshot` expose l’état demandé.
- Tests ajoutés: annulation de broadcast mis en file après stop, broadcast d’abonné bloquant
  libéré à l’arrêt, snapshot false quand le thread unwind est toujours vivant.
- Vérification locale après corrections: 212 tests passent; Ruff, format, shell syntax et
  `git diff --check` passent. **Revue de suivi requise avant PR**, les nouveaux changements
  n’ont pas encore été inspectés indépendamment.

## Revue Gamekin (contexte, distincte d’une revue du code GameBuddy)

La revue indépendante GPT-6.1 du dossier Gamekin est intégrée dans
`~/Downloads/gamekin-analysis/ANALYSE.md` §12. Elle corrige notamment l’affirmation
« ReadProcessMemory absent », nuance modèles/fine-tuning et localisation, rectifie budgets
JPEG et limite la portée du self-test à sa fenêtre-fixture. Ces constats ne valident pas le
code GameBuddy et aucun artefact propriétaire n’est repris.
