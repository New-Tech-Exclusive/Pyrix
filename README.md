# 🌌 Pyrix

**Pyrix** is a terminal-based text and code editor built with Python and `curses`.

---

## ✨ Features

- LazyVim-like UI
- Pure python, so its easy to edit
- it has native python autocomplete for files ending in '.py'
- it has a config menu to toggle line numbers and edit colors
- it has a startup dashboard with quick-start keybinding hints
- Neovim/Vim style keybindings

---

## 🚀 Getting Started

### Prerequisites

- Python 3.7+
- `curses` (built-in on most Linux/Dev environments)
- `jedi` (optional, for advanced Python autocomplete)

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/New-Tech-Exclusive/pyrix.git
   cd pyrix
   ```

2. **(Recommended) Install Jedi for autocomplete**:
   ```bash
   # In your virtual environment
   pip install jedi
   ```

3. **Make Pyrix executable**:
   ```bash
   chmod +x pyrix.py
   ```

4. **Make Pyrix available system-wide (optional, but recommended)**:
   ```bash
   mkdir -p ~/.local/bin
   cp pyrix.py ~/.local/bin/pyrix
   echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
   source ~/.bashrc
   ```

---

## ⌨️ Usage

Run Pyrix with or without a filename:

```bash
# Start with a new file
python3 pyrix.py

# Open an existing file
python3 pyrix.py main.py
```

### Keybindings

| Key | Action |
| --- | --- |
| `i` | Enter **INSERT** mode |
| `ESC` | Return to **NORMAL** mode |
| `:` | Enter **COMMAND** mode |
| `j`/`k`/`h`/`l` | Move cursor (Normal mode) |
| `u` | Undo last change |
| `r` | Redo change |
| `Tab` | Open autocomplete menu (Python Files) |
| `Right Arrow` | Accept ghost text suggestion |
| `:w` | Save file |
| `:q` | Quit Pyrix |
| `:config` | Open configuration menu |

---

## 🎨 Configuration

Access the configuration menu by typing `:config` in **NORMAL** mode. 

- Use `j`/`k` to navigate.
- Use `Space` or `Enter` to toggle options or edit colors.
- When editing colors, type a hex code (e.g., `#FF5500`) and press `Enter`.

---

## 📄 License

Distributed under the GPL-2.0 License.

---

*Made with ❤️ by Bentley*
