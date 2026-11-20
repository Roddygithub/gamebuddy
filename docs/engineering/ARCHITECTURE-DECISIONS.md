# Décisions d’architecture

## ADR-01 — Garder le pipeline de capture et PySide6

**Décision.** Réutiliser `CaptureBackend`, `WindowInfo`, `to_jpeg()` et la composition
existante dans `ui/app.py`. Pas de second serveur ou framework de perception.

**Motif.** GameBuddy sait déjà capturer la fenêtre sélectionnée directement sous Hyprland
(`stableId` + `grim -T`), persister le choix et utiliser des backends Linux non-Hyprland.
Une réécriture ne corrigerait pas les courses de cache et risquerait de régresser les
plateformes supportées.

**Conséquence.** Corriger la source commune de la capture réutilisée, garder les tests
backend actuels et documenter les garanties différentes selon le backend.

## ADR-02 — Réutilisation seulement pour la même cible, et échec fermé

**Décision.** Le cache 250 ms reste en mémoire, associé à `(id, capture_id, app_id)`. Toute
sélection/perte invalide le cache. Avant le hit, relire l’identité active. Si une adresse
Hyprland désigne désormais un autre `stableId`, retourner `None` et demander une sélection
fraîche; ne pas capturer silencieusement le nouveau propriétaire de l’adresse.

**Motif.** Cache non qualifié = risque d’envoyer un autre jeu ou une autre app au provider.
La fraîcheur vérifiée et l’identité sont indépendantes de la compréhension du screenshot.

**Limites.** Le cache n’est pas un objet frame universel horodaté; la fraîcheur d’un résultat
du modèle avant diffusion n’est pas encore vérifiée. Les backends sans identifiant stable
fort nécessitent leur propre session de validation.

## ADR-03 — Limiter le JPEG à 420 Kio par image

**Décision.** Budget par défaut de 430 080 octets (420 Kio); si nécessaire, une baisse de qualité
de 20 points, puis ajustement de taille jusqu’à respecter le plafond. `0` désactive la
limite. Les budgets <1 Kio sont refusés comme incompatibles avec un JPEG valide.

**Motif.** La revue Gamekin rapporte 144/420 Kio selon le chemin, mais ce sont des budgets
par encodeur, pas une requête totale. Un micro-benchmark local sur HUD synthétique a montré
que 420 Kio conservait 2560×1440 et le texte OCR lisible, alors que 200 Kio rognait la
résolution. Ce n’est pas une preuve de lisibilité en jeu.

**Conséquence.** Mesurer temps local et octets séparément; ne pas présenter la réduction de
payload comme une baisse universelle de latence.

## ADR-04 — Garder le Coach expérimental et opt-in

**Décision.** Ne pas promouvoir le Coach autonome. Conserver le filtre déterministe, le gate
structurel, le cooldown et la confirmation d’un second frame; exiger un modèle vision.

**Motif.** Le gate valide les champs que le modèle a renvoyés, pas la vérité indépendante de
ces champs. L’évaluation du dépôt comprend deux cas synthétiques, pas un holdout gameplay.

**Conséquence.** Aucun apprentissage du joueur et aucune collecte de captures activés. Les
erreurs HP/bouclier, ownership, plateau adverse et action expirée restent des risques à
évaluer sur des annotations réelles avant des conseils live.

## ADR-05 — Reporter OCR et crops jusqu’à une comparaison annotée

**Décision.** Ne pas ajouter Tesseract comme dépendance ou sous-système requis.

**Motif.** L’outil est installé sur cette machine, mais aucune mesure sur des captures de jeu
ne quantifie sa précision, ses faux nombres ou son coût. La revue Gamekin confirme une
architecture OCR observée, pas son effet sur la qualité finale.

**Critère de réouverture.** Corpus de captures avec texte fin et ambigu; comparer exactitude,
rappel des erreurs, taille totale et latence entre screenshot entier, OCR et crops; conflits
OCR/VLM doivent rester visibles à l’évaluateur.
