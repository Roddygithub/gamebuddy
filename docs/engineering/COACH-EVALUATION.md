# Évaluation du mode Coach

## Ce que le code garantit

`coach/pipeline.py` observe selon un intervalle, ignore les frames vides ou trop semblables,
respecte un cooldown, demande une observation JSON et laisse `coach/gate.py` refuser tout
ce qui n’est pas un conseil structuré assez confiant. Le gate exige entre autres décision
ADVISE, propriété suffisamment certaine, fenêtre lente ouverte, preuve, absence d’inconnue
critique et lien avec une option visible. Un deuxième frame frais est comparé avant de
diffuser le conseil. La cadence ne doit pas rattraper les ticks manqués en rafale.

Le gate ne sait pas vérifier que le VLM a bien lu ses propres champs. Le score confiance
est déclaré par le même modèle et n’est pas une preuve indépendante.

## Corpus et tests

Le harness `gamebuddy eval` (déjà livré en amont) grade perception, grounding, latence et
décision sur des cas TOML annotés; `--replay` rejoue les réponses stockées sous le schéma
rapporté. Tests du pipeline actuels: persistance d’un shop, disparition d’un flash,
absence de vision, frame vide, répétition et timing. Ils utilisent des fournisseurs/fenêtres
simulés. Le dataset livré n’a que deux exemples synthétiques.

Après changements de cette mission, `uv run pytest -q` passe 197 tests; cela valide le code
et les régressions déterministes, pas la valeur du conseil en partie.

## Critères de maturité

Avant de présenter le Coach comme fiable en jeu, ajouter un jeu de captures réelles et
indépendamment annotées, un holdout distinct et des scores pour:

- lecture correcte par catégorie de champ et propriétaire;
- faux conseils critiques, options réellement visibles et fenêtre encore ouverte;
- abstention correcte, faux silence et interruption inutile;
- répétition, délai jusqu’au premier conseil et nombre d’appels reasoner;
- cas HP/bouclier, plateau adverse, option indisponible et décision expirée.

Un coach toujours muet ne passe pas: mesurer séparément rappel des occasions. Ne pas
annoncer apprentissage joueur à partir de replays. N’activer aucune collecte et ne lancer
aucune partie live dans cette phase.

## Verdict

**Expérimental, opt-in.** Le pipeline peut filtrer et refuser des sorties, mais la vérité
de la perception et l’utilité du conseil ne sont pas établies. Les validations live
dépendent d’une courte fenêtre gameplay convenue par la personne.
