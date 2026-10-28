# VesperPy - lightweight open-source Discord management bot for Minecraft servers

[![Discord](https://img.shields.io/discord/947609711845462116?label=Discord&color=5865F2)](https://discord.gg/rgxqrmSbJN)
[![Minecraft](https://img.shields.io/badge/Minecraft-1.21.11-blue.svg)](https://wiki.vespera.fun)

---

## 📖 Overview

**VesperPy** - an advanced open-source Discord bot originally built for the Vespera Minecraft server that combines:

• Whitelist tickets - system for whitelisting players (for private servers)

• AI chatbot - a live "NPC" that explains the rules and helps players

• Ticket System - configurable player support for all issue types

• Radio - opportunity for players to share local news with other players

• AI Analytics - generating statistical reports on players based on info from whitelist applications

• API Plugin - integration with VesperBridge that is required for correct functionality

---

## 🛠 Installation

### Step 1: Clone / Download
```bash
git clone https://github.com/MiFo4kaa/VesperPY.git && cd VesperPY
```

### Step 2: Configure Settings
Move unwanted bot modules to "disabled" directory
Create `config.yaml` using `config.yaml.example`


### Step 3: Run 
```bash
python main.py
```

---

## 📁 Project Structure

```
VesperPY/
├── assets/               # Images/json for styling
├── cache/                # cache for tickets and radio
├── cogs/                 # Discord.py bot modules:
│   ├── AiChating.py      # AI chatbot
│   ├── Tickets.py        # Ticket handling with categories
│   ├── Radio.py          # Radio
│   ├── BloomCheck.py     # Bloom (or any other premium sub on your server) role checker
│   ├── Uwatch.py         # Remove from whitelist users that left from discord server
│   ├── PlayerInfo.py     # AI player analytics
│   └── Whitelist.py      # Whitelist system
├── disabled/             # disabled Discord.py modules
├── prompts/              # Prompts for AI (system and analysis)
├── tickets_config.yaml   # Ticket category configuration
├── radio_config.yaml     # Faction radio configuration
├── config.yaml           # MAIN configuration file
└── main.py               # Bot entry point to start execution
```

---

## 📝 License

MIT License.
