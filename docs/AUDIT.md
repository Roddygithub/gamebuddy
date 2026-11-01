# Audit technique — 1er novembre 2026

Revue locale du code Python, de la configuration, de la persistance SQLite,
 de l’IPC, du cycle de vie audio, de l’interface Qt et du mécanisme de mise à jour.
Lecture des scripts d’installation et des workflows CI. Les corrections restent
 dans le dépôt ; aucune installation système ni mise à jour de l’application
utilisée au quotidien n’a été exécutée.

## Problèmes corrigés

| Zone | Problème constaté | Correction |
| --- | --- | --- |
| Mise à jour | Un répertoire source existant sans dossier `.git` était supprimé récursivement. Les worktrees Git utilisent un fichier `.git` et étaient donc concernés. | Reconnaissance des worktrees ; refus de remplacer un répertoire non Git contenant des données. |
| Mise à jour | Le checkout d’un nom ambigu pouvait sélectionner une branche homonyme ; le repli vers les tags ne vérifiait pas le statut HTTP. | Sélection explicite de `refs/tags/…` en HEAD détachée ; vérification de la réponse HTTP. |
| Configuration | La sauvegarde tronquait directement le fichier ; les permissions privées étaient appliquées après l’écriture des clés API. | Écriture dans un fichier temporaire créé en mode 0600, synchronisation et remplacement atomique. L’ancien fichier reste intact si l’écriture échoue. |
| IPC | Les valeurs JSON autres que des objets et les octets invalides interrompaient le traitement du client. Les requêtes pouvaient grandir sans limite. | Réponse d’erreur, connexion conservée pour les requêtes invalides et plafond de 1 Mio par message. |
| IPC | Arrêter une instance refusée pouvait supprimer le socket de l’instance active. Un abonné bloqué pouvait immobiliser les diffusions sans délai limite. | Suppression du socket uniquement après un bind réussi ; maintien du délai limite des abonnés. |
| Audio | Un échec de démarrage laissait un flux micro ouvert et empêchait les tentatives suivantes. | Fermeture du flux et remise à zéro après échec, pour le push-to-talk et l’écoute mains libres. |
| Réglages | Le remplacement du listener abandonnait un micro actif ; le recorder conservait ses anciens réglages. | Arrêt des anciens flux, recréation à la prochaine utilisation et rétablissement de l’écoute mains libres si elle était active. |
| Interface vocale | Le début de l’affichage de réponse utilisait un timer depuis un thread sans boucle Qt. | Signal Qt transmis au thread de l’interface. |
| Historique | Un échange avec plusieurs appels d’outils partiellement enregistrés pouvait être rejoué avec des résultats manquants. | Relecture des seuls échanges complets ; suppression des résultats orphelins et des échanges interrompus. |
| Tests Qt | La plateforme hors écran était définie trop tard pour certaines fixtures de portée module. | Configuration au chargement de `conftest.py`. |

## Validation

Environnement virtuel isolé dans `/tmp/gamebuddy-audit-venv`, Python 3.14,
dépendances installées depuis `.[dev]`.

- `python -m pytest -q` : **78 tests réussis**.
- `ruff check src tests` : réussi.
- `ruff format --check src tests` : réussi.
- `bash -n install.sh` : réussi.
- `git diff --check` : réussi.

Les tests ajoutés couvrent la conservation du fichier de configuration après
une écriture échouée, ses permissions pendant l’écriture, la préservation des
sources de mise à jour, les worktrees, les requêtes IPC invalides, le socket de
l’instance active, la récupération après échec du micro, les réglages audio,
le thread de l’interface vocale et les échanges d’outils incomplets.

## Limites

Les appels réels aux fournisseurs IA, la capture en session de jeu, le matériel
audio, les gestionnaires de paquets et le parcours réel de mise à jour n’ont pas
été exécutés. L’interface a été testée hors écran. La matrice CI Python 3.11/3.12
n’a pas été reproduite localement. Cet audit ne constitue pas un audit exhaustif
des vulnérabilités des dépendances.
