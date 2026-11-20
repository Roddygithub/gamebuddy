# Résultats de performance

Mesures locales du 20 novembre 2026. Hôte Omarchy décrit dans `PERFORMANCE-BASELINE.md`.
Elles évaluent uniquement l’encodage Pillow et la taille des octets sur des images générées
localement. Elles ne sont ni un benchmark de modèle ni une validation de gameplay.

## Encodeur JPEG

Les séries texturées/bruitées ci-dessous sont des médianes de six exécutions. Baseline:
JPEG Pillow qualité 90, 2560×1440, sans plafond. La variante de mesure utilise `to_jpeg()`
qualité 90, même taille initiale, plafond 420 000 octets (≈410 Kio); le défaut produit est
430 080 octets (420 Kio), donc la mesure est légèrement plus stricte.

| Image de test | Sans plafond | Plafond 420 Kio | Lecture |
|---|---:|---:|---|
| Scène HUD synthétique, fond sombre et cartes lisibles | 67,2 Kio / 57,2 ms / 2560×1440 | 67,2 Kio / 55,8 ms / 2560×1440 | Budget non déclenché. Tesseract lit `ROUND 17`, `GOLD 52`, `HEALTH 84 /100` dans les deux rendus. Mesure antérieure à 4 répétitions. |
| Même HUD synthétique avec texture haute fréquence ajoutée au fond | 842 Kio / 107,0 ms / 2560×1440 | 300,6 Kio / 127,7 ms / 2560×1440 | Octets réduits de 64%; surcoût local ≈21 ms. Tesseract lit les mêmes nombres, mais cela ne mesure pas un VLM. |
| Scène haute fréquence uniforme (stress-test bruité, non représentatif d’un jeu) | 2966 Kio / 138,0 ms / 2560×1440 | 377,9 Kio / 263,2 ms / 1423×800 | Réduction de taille ≈87%; surcoût ≈125 ms et résolution réduite. Le cas montre la limite, pas le comportement typique. |

Pour la variante 200 Kio sur la scène HUD texturée: 168,9 Kio, 2091×1176, 214,7 ms; Tesseract
relit les mêmes nombres. Sur le bruit synthétique, 200 Kio produit 183,5 Kio, 1098×617 et
242,4 ms. Le budget 420 Kio est donc retenu par défaut pour favoriser
les détails à l’écran; il n’est pas présenté comme une amélioration de latence sur chaque image.

**Limites du benchmark.** Les séries avec texture et bruit sont six appels successifs sur un
hôte non isolé; la série HUD simple était quatre appels. Le timing varie avec la charge.
L’image et ses textes ont été générés par PIL; la mesure OCR est
Tesseract mono-thread sur un champ de texte clair. Aucune police de jeu, animation, compression
du provider, représentation de tokens ou capture réelle n’a été comparée. La baisse du volume
JPEG n’implique pas une baisse identique du coût ou de la durée du modèle.

## Coach et voix

Les changements locaux instrumentent capture, évaluation, confirmation et taille de frame par
tour; la TTS par phrase mesure le délai de synthèse jusqu’au premier segment. Aucune partie
réelle ni lecture audio en session n’a été lancée. La latence du provider, le premier token,
le premier son perçu et la durée complète de réponse restent **inconnus**.

Le 20 novembre 2026, `gamebuddy eval evals/coach --repeat 1 --language fr` a appelé le modèle
Coach configuré (`codex / gpt-6-luna`) sur deux exemples synthétiques: **1/2 pass**. L’abstention
attendue sur le cas ambigu a passé; le shop attendu `ADVISE` a reçu `ABSTAIN` et échoué le
critère de décision. Perception: 1/1; grounding: 1/2; latence du harness: 2/2. Rapport brut
local `/tmp/gamebuddy-eval-synthetic-2026-11-20.json`, non versionné. Ce corpus trop petit et
synthétique ne représente pas le jeu réel ni une mesure comparative avant/après.
