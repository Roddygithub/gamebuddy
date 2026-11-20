# Routage des modèles et coût

## Mission de développement

- Coordinateur: GPT-6 Luna (ce fil T3 Code). L’utilisateur demande l’usage de Luna pour
  l’orchestration et interdit GPT-6.2 Astra.
- Le catalogue T3 annonce que les options héritées du coordinateur sont `reasoningEffort=high`
  et `serviceTier=default`; elles ne peuvent pas être modifiées par le dépôt. La mission
  demande Luna Low, mais cette exécution héritée est High. J’ai limité l’escalade de raisonnement
  et utilisé des outils déterministes pour les tests/mesures.
- Revue indépendante: GPT-6.1 Terra, reasoning high pour les rounds R1–R16, medium pour R17,
  instance `codex`; chaque résultat a été contrôlé dans le retour de délégation. R17 n’a relevé
  aucun défaut matériel.
- Aucun Sol/Astra n’a été utilisé. Sol ne sera demandé que pour une question architecture
  réellement complexe ou une décision sécurité critique que Terra ne peut trancher.

## Routage de l’application vérifié

La configuration utilisateur non secrète indique `provider=codex`, `model=gpt-6-luna`,
`effort=medium`; le Coach n’a pas d’override dédié. La config du produit et la mission
agent sont deux contextes distincts. Aucun jeton/API key n’est lu dans ce rapport.

GameBuddy conserve ses providers Anthropic, OpenAI-compatible, Ollama et Codex existants.
Le mode Coach vérifie `supports_vision()` et refuse le modèle texte seul avant capture. Ne
pas interpréter cette interface comme un classement qualité/latence entre modèles.

## Appels et achats

Aucun appel multimodal distant n’a été utilisé pour le baseline, aucune API payante n’a été
ajoutée et aucun abonnement/achat n’a été déclenché. Les tests utilisent les fournisseurs
mockés existants. Le benchmark est local et déterministe. Une future évaluation par provider
devra l’annoncer dans le rapport, noter provider/modèle et distinguer images synthétiques de
captures réelles.
