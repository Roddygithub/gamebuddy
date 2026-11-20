# Revue sécurité et vie privée

Lecture statique au 20 novembre 2026 de `capture/`, `config.py`, `paths.py`, `memory.py`,
`tools/web.py`, `tools/registry.py`, `llm/codex_provider.py`, `ui/app.py` et des constats
antérieurs de `docs/AUDIT.md`. Ce document n’est pas un audit externe de dépendances ni
une validation d’un provider distant.

## Protections constatées

- Hyprland capture un `stableId` de fenêtre et échoue fermé au lieu de capturer le bureau;
  le cache retient seulement des JPEG en mémoire pendant une durée bornée, avec vérification
  de l’identité de source.
- Les frames de Coach ne sont persistées que si `coach.save_frames` est activé; la rétention
  locale est bornée et le répertoire de données est privé selon l’audit existant.
- L’historique texte et les mémoires sont dans SQLite local. Les screenshots ne sont pas
  enregistrés dans les messages.
- `docs/AUDIT.md` rapporte config privée/écriture atomique, restrictions IPC, mise à jour
  contrôlée et protections de lifecycle audio.
- `tools/web.py` n’accepte que HTTP(S), rejette credentials/ports atypiques, résout puis épingle
  une adresse IP publique, revalide les redirections, borne taille/durée et refuse les contenus
  non textuels. La recherche externe provient du package `ddgs` existant.
- Le provider Codex désactive l’accès aux outils intégrés et ne lui transmet que la capture
  choisie; vérifier les détails contre `llm/codex_provider.py` avant tout changement de ce
  chemin sensible.
- Aucun installateur, service systemd, paquet système ou collecte persistante n’a été ajouté
  par cette mission.

## Points de vigilance

- Les captures et enregistrements micro envoyés au provider choisi sortent de l’appareil; le
  consentement du fournisseur, la rétention et la région dépendent de ses conditions. Le dépôt
  ne garantit pas un traitement local.
- Les résultats web sont du contenu non fiable. Le prompt doit les traiter comme sources,
  pas comme instructions. La sécurité du réseau contre SSRF ne neutralise pas l’injection de
  prompt issue d’une page publique.
- L’UI et le Coach sont simultanés; une image en mémoire n’est pas chiffrée au niveau app.
  Le processus courant et l’espace mémoire utilisateur restent dans la frontière locale.
- Le cache cible est plus sûr, mais les backends autres que Hyprland n’exposent pas tous un
  identifiant stable équivalent. L’absence de preuve d’exfiltration n’est pas une preuve
  universelle de non-rétention chez les fournisseurs.
- Le support d’URL par `fetch_page` doit rester borné à la chaîne de redirections contrôlée;
  ne pas remplacer cette implémentation par une bibliothèque qui réactive proxies,
  résolution automatique ou redirects non vérifiés sans revue.

## Diff et validation de cette mission

Les modifications récentes corrigent une course de cache de capture; elles ne réduisent pas
les protections existantes et ne stockent aucune frame de test. Les tests en mémoire couvrent
le changement d’identité et la perte de sélection. La revue indépendante Terra du diff entier
est requise avant publication; son résultat et tout correctif seront consignés dans
`INDEPENDENT-REVIEWS.md`.

**Aucune découverte justifiant de nouvelles permissions ou un paquet supplémentaire.** Les
limites restent les providers configurés par l’utilisateur, le contenu web non fiable et les
backends qui n’ont pas de test live sur ce poste.
