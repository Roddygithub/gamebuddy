# GameBuddy

<p align="center"><strong>Compagnon de jeu IA, piloté à la voix, pour Linux</strong><br>
Reste dans ton jeu, parle à Buddy. Un compagnon IA vocal pour Wayland, Hyprland et Omarchy.</p>

<p align="center"><a href="README.md">🇬🇧 English version</a></p>

<p align="center"><img src="docs/assets/orb-fr.png" alt="Widget GameBuddy" width="420"></p>

GameBuddy, c'est **Buddy** : un assistant IA qui vit dans un petit widget à côté de ton jeu.
Tu maintiens une touche et tu parles ; Buddy voit la fenêtre de jeu que tu as choisie,
cherche sur le web, répond dans ta langue, garde tes builds et checklists épinglés à
l'écran, et se souvient des détails utiles d'une session à l'autre. Il **conseille
seulement** : il n'injecte jamais d'entrées, ne lit pas la mémoire du jeu et ne joue pas à ta place.

Tout tourne en local, sauf les appels IA que tu configures (ta propre clé, ou un modèle
local via Ollama).

## Ce qu'on voit en jeu

Par défaut, Buddy n'est qu'un **orbe** : son visage animé et ses derniers mots, rien d'autre. Il
cligne des yeux au repos, pulse quand il écoute, fait tourner des points quand il réfléchit et bouge
la bouche quand il parle. Les clics hors de l'orbe vont au jeu. Un clic sur le visage (ou une
checklist qu'il épingle) ouvre le panneau complet : contenu épinglé, conversation, saisie texte.
`mode = "panel"` dans `[ui]` démarre directement avec le panneau.

<p align="center"><img src="docs/assets/widget-fr.png" width="360" alt="Panneau GameBuddy avec une checklist épinglée"></p>

## Fonctionnalités

- **Voix d'abord** — maintiens `Alt+V` (configurable) pour parler, ou active l'écoute mains libres. Le clavier marche aussi.
- **Il voit ton jeu** — Buddy capture la fenêtre choisie (Hyprland, sway, wlroots générique, X11) et masque son propre widget dans l'image.
- **Recherche et connaissances** — recherche web + lecture de pages pour patch notes, méta, builds ; connaissances du modèle pour la stratégie.
- **Conversation continue** — le fil survit aux redémarrages ; la mémoire longue durée est une base SQLite locale.
- **Contenu épinglé** — builds, checklists, tableaux, liens ou vidéos restent visibles jusqu'à remplacement.
- **Réponses parlées** — TTS OpenAI, piper ou espeak-ng ; transcription OpenAI, [voxtype](https://github.com/peteonrails/voxtype) (l'outil de dictée d'Omarchy, builds GPU), faster-whisper (hors ligne) ou whisper.cpp.
- **Mode coach (optionnel, expérimental)** — observation périodique avec une porte de validation prudente : silence tant qu'une fenêtre de décision lente n'est pas clairement visible. Voir [docs/COACH-MODE.md](docs/COACH-MODE.md).
- **Multilingue** — interface en français, anglais, allemand, espagnol, italien, portugais (BR/PT) ; Buddy répond dans la langue que tu parles.
- **Fournisseurs** — un abonnement ChatGPT Plus/Pro (via le Codex CLI, sans clé API), Anthropic Claude, OpenAI, Ollama, ou tout endpoint compatible OpenAI.
- **Scriptable** — IPC par socket Unix et CLI (`gamebuddy ptt start`, `gamebuddy ask "…"`, `gamebuddy toggle`) : c'est ainsi que les raccourcis Hyprland et le widget de barre Omarchy le pilotent.

## Avec un abonnement ChatGPT Plus / Pro (sans clé API)

GameBuddy fonctionne avec un abonnement ChatGPT via le **Codex CLI officiel d'OpenAI**, qui se
connecte avec ton compte ChatGPT et décompte l'usage sur les limites de l'abonnement :

```bash
npm install -g @openai/codex     # ou le paquet de ta distribution
codex login                      # « Se connecter avec ChatGPT » dans le navigateur, une seule fois
```

Choisis ensuite le fournisseur `codex` dans l'assistant de démarrage, ou mets
`provider = "codex"` dans `config.toml`. Chaque question devient une exécution `codex exec`
(prompt + capture, bac à sable lecture seule, aucune session écrite) ; épinglage, mémoire et
recherche web passent par une enveloppe « actions » que GameBuddy exécute. Contreparties :
quelques secondes de latence en plus, pas de streaming, et pas d'API vocale — la voix bascule
sur des moteurs locaux (voxtype si l'outil de dictée d'Omarchy est installé, sinon faster-whisper, pour la
transcription ; piper ou espeak-ng pour la
synthèse), installés par défaut par `./install.sh`. `gamebuddy doctor` indique si Codex est
installé et connecté.

## Démarrage rapide (Arch Linux / Omarchy)

```bash
git clone https://github.com/Roddygithub/gamebuddy.git
cd gamebuddy
./install.sh
```

L'installeur ajoute les outils système via pacman (`grim`, `python`, `portaudio`, `espeak-ng`…),
crée un virtualenv isolé dans `~/.local/share/gamebuddy/venv`, lie la commande `gamebuddy` dans
`~/.local/bin`, ajoute les règles et raccourcis Hyprland dans `~/.config/hypr/`, et installe
une entrée de bureau plus un service `systemd --user` (non activé par défaut).

Ensuite :

```bash
codex login                           # ChatGPT Plus/Pro — ou export ANTHROPIC_API_KEY / OPENAI_API_KEY
gamebuddy                               # le premier lancement ouvre l'assistant de configuration
```

Widget de barre Omarchy (une icône qui affiche/masque Buddy) :

```bash
omarchy plugin add https://github.com/Roddygithub/gamebuddy.git --enable
omarchy bar put gamebuddy --after omarchy.clock
```

### Installation manuelle (toute distribution)

```bash
pipx install 'git+https://github.com/Roddygithub/gamebuddy.git'    # ou : uv tool install …
gamebuddy hyprland-config >> ~/.config/hypr/hyprland.conf          # utilisateurs Hyprland
gamebuddy doctor                                                    # vérifie outils, micro, clés
gamebuddy
```

Paquets système : `grim` (captures Wayland), `portaudio` (micro), en option `espeak-ng` ou
`piper` pour la voix hors ligne, `wmctrl` + ImageMagick sous X11.

## Configuration

`~/.config/gamebuddy/config.toml` (créé par `gamebuddy config init`, modifiable dans les Réglages ou
avec `gamebuddy config edit`). Les clés principales :

```toml
[general]
language = "auto"          # fr, en, de, es, it, pt-BR, pt-PT
assistant_name = "Buddy"
personality = "coach"      # coach | friendly | concise

[hotkeys]
push_to_talk = "ALT, V"    # syntaxe des binds Hyprland
toggle_widget = "ALT, B"

[llm]
provider = "codex"         # codex (ChatGPT Plus) | anthropic | openai | ollama | openai_compatible
model = ""                 # défaut Codex ; ex. "claude-opus-5-5" pour anthropic
effort = "low"             # anthropic / codex : réponses rapides et peu coûteuses en jeu

[speech]
stt = "voxtype"            # openai | voxtype | faster_whisper | whispercpp | none
tts = "espeak"             # openai | piper | espeak | none

[coach]
enabled = false
model = ""                 # modèle économique par défaut (claude-haiku-5-5 / gpt-4o-mini)
```

`voxtype` réutilise la pile de dictée d'Omarchy (*Install > AI > Dictation*, ou `yay -S voxtype`) :
mêmes modèles Whisper que faster-whisper, mais avec ses builds GPU Vulkan/ROCm et le modèle déjà
téléchargé. Laisser `stt_model` vide pour utiliser la config de voxtype.

Configuration 100 % locale : `provider = "ollama"`, `model = "qwen3-vl"` (vision + appels d'outils : recherche web et épinglage continuent de marcher ; un modèle sans outils répond simplement sans),
`stt = "faster_whisper"` (`pip install 'gamebuddy[local]'`), `tts = "piper"`. La recherche web est faite par GameBuddy lui-même (DuckDuckGo + lecture de page), donc elle marche avec n'importe quel fournisseur.

## Bureaux et distributions

| Session | Vision du jeu | Règles d'overlay / push-to-talk |
|---|---|---|
| Hyprland | fenêtre choisie (`hyprctl` + `grim`) | `gamebuddy hyprland-config` (écrit par l'installeur) |
| sway | fenêtre choisie (`swaymsg` + `grim`) | `gamebuddy sway-config` (écrit par l'installeur) |
| autres wlroots (river, niri, labwc…) | écran entier (`grim`) | lier `gamebuddy ptt start/stop` et `gamebuddy toggle` dans le compositeur |
| GNOME / KDE Wayland | écran entier (`spectacle`, `gnome-screenshot` ou le portail xdg) | raccourcis personnalisés vers les mêmes commandes ; `hotkeys.mode = "toggle"` si le bureau ne gère pas le relâchement |
| X11 | fenêtre choisie (`wmctrl` + ImageMagick) | écouteur global intégré (`pip install 'gamebuddy[x11]'`, `hotkeys.x11_listener = true`) |

`install.sh` installe les paquets système via pacman, apt, dnf ou zypper ; le reste passe par pip.
Omarchy n'apporte rien d'obligatoire : ses couleurs de thème et sa pile de dictée voxtype sont reprises si présentes.

## Mises à jour

```bash
gamebuddy update            # récupère la dernière release et réinstalle (redémarre le widget)
gamebuddy update --check    # juste vérifier
```

L'installeur active un timer utilisateur quotidien (`gamebuddy-update.timer`). Avec
`auto_update = "notify"` (défaut), le widget affiche une bulle et une entrée dans le menu de la
barre quand une nouvelle version existe ; `auto_update = "auto"` dans `[general]` (ou Réglages →
Updates) laisse le timer l'installer tout seul, `"off"` ne vérifie jamais. Les releases sont de
simples tags git publiés par GitHub Actions : pas de binaire, toujours le code source lisible.

## Hyprland

`gamebuddy hyprland-config` imprime règles et raccourcis adaptés à ta version de Hyprland
(`windowrulev2` historique, syntaxe `match:` ≥ 0.53, Lua ≥ 0.55). Le widget est une
fenêtre flottante épinglée : visible sur tous les espaces de travail et au-dessus des jeux
en fenêtré / plein écran sans bordure. Le plein écran exclusif n'est pas garanti, comme
dans l'original.

## CLI

| Commande | Effet |
|---|---|
| `gamebuddy` | lance le widget (instance unique) |
| `gamebuddy ptt start\|stop\|toggle` | push-to-talk |
| `gamebuddy ask "quel objet ?"` | pose une question depuis un script |
| `gamebuddy toggle` / `show` / `hide` | visibilité du widget |
| `gamebuddy listen on\|off` | écoute mains libres |
| `gamebuddy coach on\|off` | mode coach |
| `gamebuddy select-window [id]` | choisit la fenêtre du jeu (`gamebuddy windows` liste les ids) |
| `gamebuddy doctor` | vérifie outils, micro, clés, version Hyprland |
| `gamebuddy memory list\|forget` | consulte ou efface la mémoire longue durée |

## Vie privée

- Les captures ne sont prises que quand tu poses une question (ou en mode coach) et ne partent que vers le fournisseur que tu as choisi. Seuls le texte de la conversation et tes notes sont écrits sur disque (`~/.local/share/gamebuddy/gamebuddy.db`).
- Les clés API restent dans `config.toml` (mode 600) ou dans ton environnement.
- Pas de télémétrie, pas de compte, pas de serveur à nous.

## Licence

MIT — voir [LICENSE](LICENSE). Projet communautaire indépendant, sans affiliation avec un éditeur de jeux ou un fournisseur d'IA.

### Taille adaptative de Buddy

Par défaut, `compact_orb = "auto"` dans `[ui]` affiche une petite tête de 64 × 64
sur les écrans dont la surface utile ne dépasse pas 1280 pixels de large ou
800 pixels de haut. Ces dimensions sont en pixels logiques : la mise à l’échelle
HiDPI du bureau est donc prise en compte. Sur les écrans plus grands, l’orbe
avec texte mesure 260 × 96. Le panneau reste limité à la surface utile et la
présentation se réadapte lors d’un changement d’écran ou de résolution.

`compact_orb = true` force la petite tête ; `false` garde l’orbe avec texte.
L’icône de Buddy dans le systray est fournie comme icône symbolique monochrome :
les bureaux compatibles, dont Omarchy, l’adaptent à la couleur de leur barre.
