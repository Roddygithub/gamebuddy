# Rapport final d’ingénierie GameBuddy

Date: 20 novembre 2026. Référence intégrée: commit `1d1a9ef`, PR [#15](https://github.com/Roddygithub/gamebuddy/pull/15).

## État initial et audit

Le dépôt était en version 0.7.0 sur `main` (`2a9cf0e`), sans divergence avec `origin/main` et
avec le workflow CI vert. Le checkout contenait aussi des modifications locales non commitées;
elles ont été conservées, inspectées et intégrées au travail. La baseline locale était de 189
tests réussis et un test de langue échoué parce que `LC_ALL`/`LC_MESSAGES` hérités masquaient
`LANG`.

Le différentiel a confirmé que GameBuddy avait déjà PySide6, l’orb et l’interface Buddy,
l’intégration Omarchy/Hyprland optionnelle, la capture ciblée Hyprland par `stableId`, la
mémorisation de fenêtre, les providers multiples dont Codex CLI, la STT/TTS, Piper, la mémoire,
les raccourcis, un Coach expérimental et `gamebuddy eval`. Ces capacités ont été auditées et
améliorées sans réécrire l’architecture ni réimplémenter les fonctions existantes.

Les constats Gamekin sont classés dans
[`GAMEKIN-DIFFERENTIAL.md`](GAMEKIN-DIFFERENTIAL.md). Les chemins de capture, OCR et contrats
visibles dans l’analyse ont été traités comme **VERIFIED au niveau du code inspecté**, pas
comme preuve de qualité réelle en jeu. Les gains de vitesse, la localisation du traitement,
les caches de connaissances et l’absence de fine-tuning restent **HYPOTHESIS** ou **UNKNOWN**
selon le cas. Aucun code, binaire, prompt ou donnée propriétaire Gamekin n’a été copié.

## Problèmes corrigés

- Liaison des captures et du cache à l’identité et à la génération de la fenêtre sélectionnée;
  rejet d’une cible remplacée ou disparue, y compris entre acquisition et confirmation.
- Sérialisation des acquisitions et vérification du contexte avant les sorties UI, IPC et voix.
- Correction du cooldown Coach, dont le sentinelle initial bloquait à tort le premier conseil
  durant les 60 premières secondes après un démarrage système.
- Déduplication visuelle et textuelle limitée au contexte de capture; un écran revenu après une
  confirmation instable est réévalué.
- Annulation TTS liée à la réponse, à la génération Coach et à la fenêtre; une voix périmée
  s’arrête sans interrompre ASK ni annuler une nouvelle voix de la fenêtre choisie.
- Fermeture IPC non bloquante, envois sérialisés par socket et événements Coach annulables.
- Plafond JPEG réellement borné, filtres et documentation des limites de timing corrigés.

Les tests couvrent ces corrections dans les suites capture, Coach, IPC et TTS. La CI a d’abord
révélé le défaut d’uptime court sous Python 3.11; il a été corrigé et tous les checks ont ensuite
passé sur les deux versions supportées.

## Tests, mesure et revue

- Tests locaux: **234 passed** sous Python 3.11; même résultat avec `QT_QPA_PLATFORM=offscreen`.
- Contrôles locaux: Ruff check, Ruff format check, `bash -n install.sh plugin-control.sh` et
  `git diff --check` passent.
- CI de PR #15, run [44737643636](https://github.com/Roddygithub/gamebuddy/actions/runs/44737643636):
  `test (3.11)`, `test (3.12)` et `manifest` sont **SUCCESS**.
- Revue indépendante: 17 rondes Terra au fil des corrections; la dernière revue ciblée (R17)
  confirme le correctif d’uptime sans finding P0–P2 matériel restant.
- Mesures de performance: [`PERFORMANCE-RESULTS.md`](PERFORMANCE-RESULTS.md) présente des
  tailles d’encodage sur images synthétiques. Selon le contenu, le plafond JPEG réduit les
  octets mais peut ajouter environ 21 à 125 ms et réduire la résolution. Aucune amélioration
  générale de latence n’est revendiquée.
- Évaluation Coach sur deux exemples synthétiques: **1/2**. Le cas ambigu a été correctement
  abstenu; le cas shop attendu `ADVISE` a reçu `ABSTAIN`. Latence provider, premier token,
  premier son audible et qualité sur captures réelles restent inconnus.

## Intégration et sécurité

La PR #15, « Harden capture and coach reliability », a été fusionnée par squash dans `main`
avec le commit `1d1a9ef`. Aucun paquet système, service persistant, abonnement payant ou collecte
persistante de captures n’a été introduit. Les permissions, la sélection de cible, les limites
de capture et les protections SSRF existantes restent documentées dans
[`SECURITY-REVIEW.md`](SECURITY-REVIEW.md). Cette revue de code n’est pas un audit externe de
dépendances ou de providers.

## État de préparation

- **ASK MODE — prêt pour usage et essais manuels avec un provider configuré.** La capture et
  l’identité de cible sont plus robustes, mais la compréhension visuelle et la latence n’ont
  pas été validées en vraie partie.
- **AUTONOMOUS COACH — expérimental et opt-in.** La chaîne filtre et annule mieux les
  observations périmées; l’évaluation synthétique 1/2 ne justifie pas un usage autonome fiable.
- **PLAYER-LEARNING — non disponible.** Aucun apprentissage du joueur ou fine-tuning n’a été
  implémenté ni démontré.

La prochaine validation utile exige une fenêtre de jeu contrôlée et des captures Underlords
annotées, avec cas d’ownership, ressources, options indisponibles, décisions expirées, conseils
incorrects et silence attendu. Elle n’a pas été lancée pendant cette mission.
