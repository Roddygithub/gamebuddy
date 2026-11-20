# Évaluation de la perception

## Capacités du code

- ASK attache une image JPEG optionnelle à la question et donne le titre de jeu connu.
- Coach emploie un seul frame par observation, un dHash 16×16 pour ignorer les changements
  faibles, une sortie JSON structurée et une seconde image de confirmation avant diffusion.
- `coach/gate.py` valide des contraintes d’état et d’ownership déclarées par le modèle.
  Ce n’est pas une vérification indépendante de pixels.
- Le dépôt ne contient pas d’OCR de jeu ni de zones adaptatives. Tesseract 5.5 est installé
  sur la machine, mais n’est ni une dépendance du projet ni un validateur de valeur.
- La suite dispose de deux exemples, dessinés dans `evals/coach/example-*`; ils testent le
  format du harness et des décisions évidentes, pas la lecture d’une partie réelle.

## Résultat actuel

Le harness sépare `perception`, `grounding`, `latency` et `decision`; les enregistrements
peuvent être rejoués sans nouvel appel modèle. Les deux images de démonstration sont
explicitement `synthetic = true`. Aucune exactitude sur noms de héros, niveau d’étoiles,
or, coût ou plateau adverse ne peut en être déduite.

Un test OCR exploratoire sur une image HUD créée par PIL a conservé les nombres après JPEG
420 Kio. Il indique seulement que ce dessin généré reste lisible par Tesseract. Il ne mesure
ni un modèle vision, ni une police de jeu, ni la perception de Dota Underlords.

## Mesures à ajouter au corpus avant la prochaine décision

Pour chaque capture annotée, conserver séparément la vérité et le résultat du modèle:

- propriétaire et côté de plateau (joueur/adversaire/spectateur);
- entités visibles, niveaux/étoiles si lisibles;
- ressources typées (PV, bouclier, mana, or, coût) avec leur région source;
- options d’achat/action réellement disponibles;
- ambiguïtés et champs qui doivent rester inconnus;
- frame d’origine, horodatage, jeu et patch si connu;
- capture fraîche, changement de cible ou source perdue.

Rapporter exactitude et rappel sur chaque champ, conflits de ressources, erreurs critiques,
abstentions correctes, faux conseils, taille du JPEG et coût capture/encodage. Garder des cas
holdout non utilisés pour ajuster le prompt. N’appeler un OCR utile que s’il améliore le
rappel sans faire passer des valeurs erronées dans le gate.

## Décision

**Pas de nouvelle brique de perception dans cette phase.** Les options à tester sur ce
corpus sont screenshot entier, screenshot plafonné, puis overview+crops/OCR. Les règles de
sélection du corpus et la lecture des sources Gamekin sont dans
[`GAMEKIN-DIFFERENTIAL.md`](GAMEKIN-DIFFERENTIAL.md) et
[`PERFORMANCE-RESULTS.md`](PERFORMANCE-RESULTS.md).
