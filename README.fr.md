# GameBuddy

<p align="center"><strong>Compagnon de jeu IA, piloté à la voix, pour Linux</strong><br>
Reste dans ton jeu, parle à Buddy. Un widget façon GameKin pour Wayland, Hyprland et Omarchy.</p>

<p align="center"><a href="README.md">🇬🇧 English version</a></p>

<p align="center"><img src="docs/assets/widget-fr.png" alt="Widget GameBuddy" width="420"></p>

GameBuddy, c'est **Buddy** : un assistant IA qui vit dans un petit widget à côté de ton jeu.
Tu maintiens une touche et tu parles ; Buddy voit la fenêtre de jeu que tu as choisie,
cherche sur le web, répond dans ta langue, garde tes builds et checklists épinglés à
l'écran, et se souvient des détails utiles d'une session à l'autre. Il **conseille
seulement** : il n'injecte jamais d'entrées, ne lit pas la mémoire du jeu et ne joue pas à ta place.

Tout tourne en local, sauf les appels IA que tu configures (ta propre clé, ou un modèle
local via Ollama).

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

Configuration 100 % locale : `provider = "ollama"`, `model = "llama3.2-vision"`,
`stt = "faster_whisper"` (`pip install 'gamebuddy[local]'`), `tts = "piper"`.

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

MIT — voir [LICENSE](LICENSE). GameKin est une marque de son propriétaire ; GameBuddy est un projet indépendant, sans affiliation.
