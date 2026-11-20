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

## Revue 6 — annulation en cours et sérialisation des sockets

- Relecteur: GPT-6.1 Terra, reasoning high, statique en lecture seule; HEAD `58ab0ae`.
- Findings: un conseil déjà envoi vers un subscriber lent pouvait continuer après désactivation
  et atteindre les suivants (**P2**); envois simultanés sur un même socket n’étaient plus
  sérialisés après retrait du verrou global (**P2**). Le détachement/shutdown et l’état de
  statut R5 étaient jugés corrects sur les chemins inspectés.
- Réponse dans le diff actuel: predicate de validité (état + génération) vérifiée avant chaque
  socket et juste après acquisition du verrou dédié à ce socket; un send déjà démarré peut
  finir au subscriber courant mais les prochains sont supprimés après stop. `IPCServer` garde
  un verrou d’envoi par socket, tandis que le verrou de liste reste libre durant `sendall`.
- Tests ajoutés: stop entre le premier envoi bloqué et le second subscriber; deux broadcasts
  concurrents sur le même subscriber restent des lignes entières et sérialisées. Suite locale
  à HEAD 58ab0ae: **214 passed**; Ruff, format, shell syntax et diff-check passent. Revue de
  suivi requise avant PR.

## Revue 7 — voix Coach et protocole d’abonnement

- Relecteur: GPT-6.1 Terra, reasoning high, statique en lecture seule; HEAD `841152d`.
- Findings: un worker voix ou un signal UI Coach déjà mis en file pouvait survivre à l’arrêt
  (**P2**); l’accusé subscribe partageait la socket avec les broadcasts avant d’être envoyé
  (**P2**).
- Réponse: la voix Coach porte génération Coach et source, est annulée à la désactivation sans
  toucher une réponse ASK; le signal UI porte aussi la génération et l’UI le filtre. L’accusé
  IPC est écrit avant d’ajouter le subscriber, sous son verrou d’envoi; les broadcasts ne le
  voient donc qu’après l’ACK.
- Tests ajoutés: voix Coach en file puis stop, signal Qt ancien après stop, ACK et broadcast
  concurrents sur le subscriber. Vérification locale: **217 tests passent**; Ruff, format,
  shell syntax et diff-check passent. Revue de suivi requise avant PR.

## Revue 8 — course ASK/Coach et sélection de fenêtre

- Relecteur: GPT-6.1 Terra, reasoning high, statique en lecture seule; HEAD `83eb2dd`.
- Findings: arrêt Coach pouvait entrer entre la validation du jeton et la mise en file de la
  voix, interrompant une lecture ASK déjà active (**P2**); une erreur de capture de l’ancienne
  fenêtre pouvait émettre un `window_lost` sans identité et effacer une sélection plus récente
  via le signal Qt (**P2**).
- Réponse: `_queue_speech` vérifie l’identité Coach sous le même verrou que la création du job;
  `set_coach(False)` ne stoppe que la parole dont la source est Coach. `window_lost` porte
  `(id, capture_id, app_id)` et le slot refuse d’effacer une cible différente.
- Tests ajoutés pour la course ASK/Coach pendant désactivation et la notification de perte
  périmée avant/après capture. `uv run pytest -q`: **220 passed**; Ruff, format, shell syntax
  et diff-check passent. Revue indépendante de suivi nécessaire avant PR.

## Revue 9 — perte de fenêtre déjà disparue

- Relecteur: GPT-6.1 Terra, reasoning high, lecture seule; HEAD `71dee70`.
- Finding: les validations identité préalables retournaient `None` sans notifier l’UI quand
  `find_window` indiquait que la source a disparu; titre/choix restaient périmés (**P2**).
- Réponse: les deux chemins émettent maintenant un événement de perte identifiant si le
  lookup conclut à une source manquante ou remplacée; une exception de lookup (panne
  temporaire) invalide le cache mais ne supprime pas la sélection. Le slot vérifie encore
  l’identité courante au traitement du signal.
- Tests: source déjà absente avec et sans cache; erreur de lookup sans notification; sélection
  différente préservée. Suite après correction: **223 passed**; Ruff, format, shell syntax et
  diff-check passent. Nouvelle revue indépendante requise avant PR.

## Revue 10 — remplacement intermédiaire et captures simultanées

- Relecteur: GPT-6.1 Terra, reasoning high, lecture seule; HEAD `3c015ed`.
- Findings: backend pouvait signaler `window_replaced` après la prévalidation sans nettoyer la
  sélection (**P2**); signal tardif pouvait supprimer une sélection identique re-sélectionnée
  (**P2**); deux captures concurrentes pouvaient inverser l’ordre du cache (**P2**).
- Réponse: `window_replaced` produit le même événement ciblé que `window_lost`; un compteur de
  sélection est joint au signal et contrôlé par le slot; `_capture_lock` dédié sérialise les
  captures sans bloquer le changement de sélection via `_shot_lock`.
- Tests ajoutés: notification backend remplacé, resélection même identité avec signal obsolète,
  et deux captures fraîches bloquées pour vérifier l’ordre cache. Suite: **225 passed**; Ruff,
  format, shell syntax, diff-check passent. Revue de suivi requise avant PR.

## Revue 11 — génération de capture et fraîcheur Coach

- Relecteur: GPT-6.1 Terra, reasoning high, lecture seule; HEAD `c37abb4`.
- Findings: (1) Portal peut réutiliser le même objet `SCREEN`; une capture ancienne pouvait
  alors émettre un signal après re-sélection ou alimenter le cache de la nouvelle génération
  (**P2**); (2) Coach pouvait confirmer une observation avec une nouvelle fenêtre si les dHash
  étaient proches (**P2**).
- Réponse dans le diff courant: capture prend un snapshot de `_window_generation`, vérifie
  cette même génération à chaque réutilisation/cache/fin/notification; l’UI et Coach portent
  la génération du frame initial; la re-capture de confirmation doit garder le même contexte,
  et la livraison revérifie le contexte courant.
- Tests ajoutés: sélection du même objet pendant capture; changement de cible entre frame
  initiale et confirmation malgré des pixels identiques. Suite locale: **227 passed**; Ruff,
  format, shell syntax et diff-check passent. Revue de suivi requise avant PR.

## Revue 12 — contexte de sélection jusqu'aux livraisons asynchrones

- Relecteur: GPT-6.1 Terra, reasoning high, lecture seule; HEAD `4846efc`.
- Findings P2: une sélection pouvait changer entre la dernière vérification du pipeline et
  l'affichage, l'envoi IPC ou la lecture vocale; le filtre dHash partagé pouvait aussi ignorer
  une nouvelle fenêtre dont l'image ressemble à celle de l'ancienne.
- Réponse dans le diff en cours: la génération de capture suit le conseil dans le signal Qt,
  les prédicats IPC et la tâche TTS; chacun revérifie la cible au moment de l'effet. Le filtre
  dHash ne déduplique une image que dans le même contexte de capture.
- Tests ajoutés: génération changée avant l'affichage UI, l'IPC en attente et la synthèse
  vocale en attente; nouvelle sélection avec dHash identique évaluée par le raisonneur.
- Vérification locale: **230 tests passent**; `ruff check`, format, `bash -n install.sh` et
  `git diff --check` passent. Suivi indépendant requis avant PR.

## Revue 13 — déduplication inter-fenêtres et voix déjà active

- Relecteur: GPT-6.1 Terra, reasoning high, lecture seule; HEAD `4846efc` avec les corrections
  de la revue 12 non commitées.
- Findings P2: (1) le même conseil était filtré comme répétition même lorsqu'il provenait d'une
  nouvelle génération de capture; (2) une voix Coach déjà démarrée continuait après sélection
  d'une autre fenêtre.
- Réponse dans le diff en cours: la déduplication de conseil est maintenant limitée à la même
  génération de capture; `select_window` annule uniquement la voix Coach active et arrête son
  lecteur, sans interrompre une réponse ASK.
- Tests ajoutés: conseil identique accepté après changement de génération; sélection d'une
  nouvelle fenêtre pendant `player.play` annule la voix Coach.
- Vérification locale après correction: **231 tests passent**. Revue indépendante de suivi
  requise avant PR.

## Revue 14 — préserver une voix mise en file pour la nouvelle cible

- Relecteur: GPT-6.1 Terra, reasoning high, lecture seule; HEAD `4846efc` avec les corrections
  des revues 12 et 13 non commitées.
- Finding P2: entre la publication de la nouvelle génération et l'annulation de l'ancienne voix,
  un nouveau conseil pouvait être mis en file puis annulé à tort.
- Réponse dans le diff en cours: chaque job vocal mémorise sa génération de capture; le
  changement de cible annule les voix Coach obsolètes tout en préservant celle qui appartient
  à la génération nouvellement sélectionnée. La désactivation globale conserve l'annulation
  de toute voix Coach.
- Test ajouté: entrelacement déterministe où un job vocal de la nouvelle cible est mis en file
  après publication de génération et survit à l'annulation ciblée; l'ancien jeton est annulé.
- Vérification ciblée: 37 tests de Coach, capture et runtime passent. Revue indépendante de
  suivi requise avant PR.

## Revue 15 — conseil non retenté après confirmation instable

- Relecteur: GPT-6.1 Terra, reasoning high, lecture seule; HEAD `4846efc` avec les corrections
  des revues 12 à 14 non commitées.
- Finding P2: le hash d'un candidat était mémorisé avant la confirmation; une recapture
  temporairement différente ou absente abandonnait le conseil, puis le hash empêchait de
  réévaluer l'écran initial s'il revenait.
- Réponse dans le diff en cours: un candidat qui a reçu un résultat rejeté peut rester dédupliqué,
  mais celui qui a produit un conseil n'est mémorisé comme livré/considéré qu'après confirmation
  stable. La comparaison de confirmation porte directement sur le hash initial.
- Test ajouté: écran valide, confirmation transitoirement différente, puis retour à l'écran
  valide; le second tick doit relancer l'évaluation et livrer le conseil.
- Vérification locale: **233 tests passent**; Ruff check, format check, syntaxe shell et
  diff-check passent.

## Revue 16 — confirmation stable et suivi final

- Relecteur: GPT-6.1 Terra, reasoning high, lecture seule; checkout `4846efc` avec le diff
  des revues 12 à 15.
- Résultat: **aucun finding matériel P0–P2** identifié. Le reviewer a confirmé l’association
  des déduplications et voix à la cible, ainsi que la confirmation contre le hash initial.
- Contrôles du reviewer: inspection statique du diff, tests modifiés et chemins de capture,
  Coach, UI, IPC et TTS; `git diff --check`. Il n'a exécuté ni tests ni linters, ni lancé de
  jeu, ni accédé au réseau.

## Revue 17 — premier conseil sur un runner fraîchement démarré

- Détecté par CI après la revue 16: le job Python 3.11 a échoué sur les premiers conseils
  Coach; Python 3.12 et le manifeste passaient. L'inspection du log a montré un runner démarré
  depuis moins de 60 secondes.
- Cause: `_last_advice_at=0.0` était traité comme une vraie heure monotone; le garde cooldown
  ignorait le premier conseil pendant les premières 60 secondes après le démarrage du système.
- Réponse dans le diff en cours: l'horodatage est `None` avant toute livraison et le cooldown
  n'est testé qu'après un premier conseil; test simulant monotonic=5s. Suite locale sur Python
  3.11, avec et sans `QT_QPA_PLATFORM=offscreen`: **234 passed** dans chaque run.
- Relecteur: GPT-6.1 Terra, reasoning medium, lecture seule; il a confirmé la sentinelle,
  l'horodatage monotone et la reprise d'un candidat après cooldown. Aucun finding P0–P2.
- Vérifications complètes locales: **234 tests**; Ruff check/format, shell syntax et
  diff-check passent. La relance GitHub après push reste requise.

## Revue Gamekin (contexte, distincte d’une revue du code GameBuddy)

La revue indépendante GPT-6.1 du dossier Gamekin est intégrée dans
`~/Downloads/gamekin-analysis/ANALYSE.md` §12. Elle corrige notamment l’affirmation
« ReadProcessMemory absent », nuance modèles/fine-tuning et localisation, rectifie budgets
JPEG et limite la portée du self-test à sa fenêtre-fixture. Ces constats ne valident pas le
code GameBuddy et aucun artefact propriétaire n’est repris.
