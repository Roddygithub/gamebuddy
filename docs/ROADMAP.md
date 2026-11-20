# Roadmap — précision, latence et Coach

Objectif : réduire l’attente sans perdre le contexte visuel utile. La cible « moins de
2 secondes entre le changement d’écran et un conseil » reste une ambition, pas un résultat
mesuré. Le délai modèle, la perception en partie et le premier son ne sont pas encore mesurés
ensemble.

Cette feuille de route garde uniquement des travaux justifiés. Les décisions prises à partir
de l’analyse Gamekin sont détaillées dans [`engineering/GAMEKIN-DIFFERENTIAL.md`](engineering/GAMEKIN-DIFFERENTIAL.md).

## Déjà présent dans le checkout 0.7.0 et changements vérifiés

| Capacité | Preuve / limite |
|---|---|
| Capture Hyprland par `stableId`, sélection mémorisée et pas de fallback bureau | `capture/hyprland.py`, `capture/base.py`; tests existants. Session gameplay réelle encore à valider. |
| Coach opt-in, gate structurel, cooldown et confirmation par frame frais | `coach/pipeline.py`, `coach/gate.py`; le gate ne prouve pas la vérité du VLM. |
| Harness d’évaluation et relecture des sorties | `gamebuddy eval`; exemples livrés synthétiques, aucune généralisation en partie. |
| Cadence Coach qui saute les échéances manquées sans rafale | Test à horloge contrôlée. |
| Limite JPEG par image (420 Kio par défaut), changement de qualité puis dimensions | Test d’image bruitée; le surcoût varie selon la frame. Voir résultats micro-benchmark. |
| Cache de capture bref, attaché à l’identité, invalidé sur sélection/perte | Test pour adresse Hyprland réutilisée et sélection pendant acquisition. |
| Synthèse par phrase et annulation quand une nouvelle demande ou PTT arrive | Tests de découpage et d’interruption; lecture sur périphérique réel non testée. |
| Rejet d’une frame presque uniforme et avertissement si modèle Coach texte seul | Tests unitaires; ce n’est pas un self-test de capture de jeu. |

## Travaux à faire dans l’ordre

### 1. Valider la capture réelle et sa fraîcheur — priorité P0/P1

Pendant une courte session convenue, vérifier fenêtre ciblée, plein écran, changement
d’espace, disparition/remplacement, échec sans capture bureau et l’image réellement montrée
au modèle. Mesurer l’âge au départ et décider si ASK/Coach doivent refuser une réponse trop
vieille. Ne pas enregistrer les frames par défaut.

### 2. Constituer un corpus de perception/Coach — priorité P1

Annoter 20–30 captures de jeu, garder des cas holdout, puis rapporter ownership, champs
ressources typés, options visibles, états ambigus, conseils erronés, silence et délai. Les
exemples synthétiques existants restent des tests de code. L’utilisateur doit choisir la
fenêtre de validation live; aucun jeu n’est lancé automatiquement.

### 3. Comparer OCR et régions à l’image entière — priorité P1 conditionnelle

Tesseract est déjà présent sur la machine mais absent du produit. L’ajouter seulement si le
corpus montre que les valeurs HUD sont mieux lues sans faire passer les erreurs OCR dans le
gate. Comparer texte, rappel des erreurs, latence et taille. Pas de framework universel de
vision ni de nouvelle dépendance avant cette preuve.

### 4. Mesurer le chemin complet — priorité P1

Séparer STT, capture, préparation JPEG, premier texte utile, réponse complète, synthèse du
premier segment et premier son entendu. Ne pas utiliser la durée totale de `codex exec` comme
proxy d’inférence. Ne pas ajouter de serveur persistant ou d’appel de préchauffage sans
mesure montrant que l’initialisation domine réellement.

### 5. Versionner une connaissance seulement si un cas l’exige — priorité P2

Tester un fait de jeu qui a changé entre deux patches. Si l’outil web existant répond bien,
ne pas construire de packs/cache/RAG. Si une lacune réelle demeure, attacher source, date,
jeu et patch et tester l’invalidation avant d’élargir.

## Différés sans preuve

Fine-tuning, détection de jeu par catalogue, modèles locaux always-on, SDK multi-jeux,
apprentissage de joueur, service de streaming et architecture serveur. Aucun achat ni
abonnement API ne sera ajouté.

Les mesures synthétiques déjà disponibles sont dans
[`engineering/PERFORMANCE-RESULTS.md`](engineering/PERFORMANCE-RESULTS.md); elles ne
représentent pas une validation en jeu.
