# Fiabilité de capture

État vérifié au 20 novembre 2026, sur le code `main` 0.7.0 plus les changements locaux
de cette mission. Une capture live du jeu n’a pas été exécutée.

## Chemin réel

1. La personne choisit une fenêtre; `WindowInfo.id` est l’identifiant du backend et
   `capture_id` porte l’identifiant de capture stable disponible sous Hyprland.
2. Le choix est mémorisé dans `~/.local/share/gamebuddy/window.json` par application et
   titre; au redémarrage, GameBuddy ne choisit pas au hasard parmi plusieurs fenêtres.
3. Hyprland re-liste les clients avant capture, retrouve l’adresse puis demande à grim
   l’identifiant `stableId` de cette fenêtre. Sans cible ou sans `stableId`, la capture
   échoue. Aucun repli sur le bureau n’est utilisé.
4. Sway et X11 capturent la fenêtre/région ciblée. Les backends wlroots générique et
   portail capturent l’écran entier; l’identité fine de fenêtre n’y est pas disponible.
   Le masquage de Buddy s’applique là où la capture est une région ciblée.
5. Le PNG devient un JPEG; par défaut la largeur maximale est 2560 px, qualité 90 et
   plafond 430 080 octets (420 Kio) par frame. Le CLI réutilise maintenant le même budget.
6. L’app réutilise une frame pendant au plus 250 ms seulement si `(id, capture_id,
   app_id)` correspond encore et que le backend retrouve cette même source. Une erreur,
   perte ou sélection différente invalide le cache. L’image est gardée en mémoire; ce
   mécanisme ne l’écrit pas sur disque. Un verrou d’acquisition distinct sérialise les
   captures et empêche une frame lente d’écraser un résultat plus récent.
7. Coach contourne ce cache pour sa seconde capture de confirmation. ASK capture à la
   demande et joint le résultat au provider sélectionné.

## Régressions couvertes

- `tests/test_hyprland_capture.py`: cible `stableId`, absence de fallback, fenêtre perdue.
- `tests/test_capture_cache.py`: adresse Hyprland réutilisée avec un autre `stableId`
  échoue fermé sans cache, avec cache expiré ou sur le cache valide; changement de
  sélection pendant l’acquisition ne renvoie pas la frame; une notification de perte
  retardée ne détruit pas la nouvelle sélection; une source absente est signalée après un
  lookup concluant, mais une erreur transitoire de lookup n’efface pas le titre; deux captures
  fraîches concurrentes n’inversent pas l’âge du cache.
- `tests/test_observer_capture.py`: préserve l’image ultra-large sans plafond et vérifie
  qu’une image haute entropie respecte le budget; refuse un budget trop petit pour un JPEG.
- `tests/test_coach_stability.py`: une frame changée pendant la confirmation ne produit
  aucun conseil.

## Limites restantes

- Aucun test n’a capturé une partie, une fenêtre masquée, un jeu plein écran, un changement
  d’espace de travail ou un écran noir avec le compositeur réel. L’accès de cette commande
  shell à Hyprland n’est pas direct même si la session utilisateur expose ses variables.
- Les backends non-Hyprland n’ont pas tous l’équivalent d’un `stableId`; leur comportement
  au remplacement rapide d’une fenêtre reste à vérifier par backend.
- Le `dhash` global ne détecte pas une image complètement figée mais non uniforme.
  `is_blank()` ne valide que la faible variation globale et ne prouve pas que la fenêtre
  sélectionnée contient le jeu voulu.
- Une réponse du modèle peut terminer après que l’écran a changé. Le second frame vérifie
  la stabilité après le délai de génération, mais le pipeline ne compare pas encore la
  fraîcheur ni l’identité au moment exact de la restitution audio/UI.
- `max_bytes` borne chaque JPEG, pas l’ensemble images+texte ni les octets de transport du
  provider. La valeur 420 Kio favorise les détails; son effet sur la lecture par VLM doit
  être évalué sur des captures autorisées et annotées.

## Validation live à faire plus tard

Avec une courte session convenue: sélectionner une fenêtre de test, comparer capture
`gamebuddy capture` à la fenêtre attendue, basculer d’espace, fermer/remplacer le jeu et
vérifier l’échec sans bureau. Ne sauvegarder aucune frame sauf si la personne active
explicitement `coach.save_frames`; garder ces fichiers privés et bornés.
