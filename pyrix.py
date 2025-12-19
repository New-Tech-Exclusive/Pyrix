#!/usr/bin/env python3
import curses
import sys
import os
import re
import time
import builtins
import keyword

NORMAL = "NORMAL"
INSERT = "INSERT"
COMMAND = "COMMAND"
CONFIG = "CONFIG"
AUTOCOMPLETE = "AUTOCOMPLETE"

class Editor:
    def __init__(self, stdscr, filename=None):
        self.stdscr = stdscr
        self.filename = filename
        self.cursor_x = 0
        self.cursor_y = 0
        self.scroll = 0
        self.lines = [""]
        self.mode = NORMAL
        self.command_text = ""
        self.undo_stack = []
        self.redo_stack = []
        self.show_line_numbers = True
        self.config_index = 0
        self.config_input = ""
        self.is_inputting = False
        self.notifications = []
        self.show_dashboard = filename is None and not (len(sys.argv) > 1)
        self.lsp = None
        self.ac_suggestions = []
        self.ac_index = 0
        self.is_python = filename and filename.endswith('.py')
        
        if self.is_python:
            self.lsp = PythonLSP()
        
        # Tokyonight Palette
        self.tokyonight = {
            "bg": "#1a1b26", "fg": "#c0caf5",
            "keyword": "#bb9af7", "string": "#9ece6a",
            "comment": "#565f89", "def": "#7aa2f7",
            "status_bg": "#3b4261", "status_active": "#7aa2f7",
            "status_error": "#f7768e", "status_info": "#e0af68"
        }

        self.config_options = [
            {"name": "Line Numbers", "type": "toggle", "attr": "show_line_numbers"},
            {"name": "Foreground", "type": "color", "pair": 5, "hex": self.tokyonight["fg"], "fg": True},
            {"name": "Background", "type": "color", "pair": 5, "hex": self.tokyonight["bg"], "bg": True},
            {"name": "Keyword Color", "type": "color", "pair": 1, "hex": self.tokyonight["keyword"]},
            {"name": "String Color", "type": "color", "pair": 2, "hex": self.tokyonight["string"]},
            {"name": "Comment Color", "type": "color", "pair": 3, "hex": self.tokyonight["comment"]},
            {"name": "Def/Class Color", "type": "color", "pair": 4, "hex": self.tokyonight["def"]},
        ]

        if curses.has_colors():
            curses.start_color()
            if curses.can_change_color():
                for i, opt in enumerate(self.config_options):
                    if opt["type"] == "color":
                        self.update_color_definition(opt)
                
                # Additional colors for status segments
                curses.init_color(20, *self.hex_to_rgb("#7aa2f7")) # Normal mode blue
                curses.init_color(21, *self.hex_to_rgb("#e0af68")) # Insert mode yellow
                curses.init_color(22, *self.hex_to_rgb("#f7768e")) # Command mode red
                curses.init_color(23, *self.hex_to_rgb("#3b4261")) # Status background
                
                curses.init_pair(20, 0, 20) # Segment ACTIVE BG
                curses.init_pair(21, 20, 23) # Segment ACTIVE text on status bg
                curses.init_pair(22, 23, 0) # Dark text on black
                curses.init_pair(23, 10, 23) # Default fg on status bg
            else:
                curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)
                curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)
                curses.init_pair(3, curses.COLOR_GREEN, curses.COLOR_BLACK)
                curses.init_pair(4, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
                curses.init_pair(5, curses.COLOR_WHITE, curses.COLOR_BLACK)
                curses.init_pair(20, curses.COLOR_BLACK, curses.COLOR_BLUE)
                curses.init_pair(23, curses.COLOR_WHITE, curses.COLOR_BLACK)

        if filename and os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                self.lines = f.read().splitlines()
                if not self.lines:
                    self.lines = [""]

    def run(self):
        curses.curs_set(1)
        self.stdscr.timeout(100)

        while True:
            self.draw()
            key = self.stdscr.getch()

            if key == -1:
                continue

            if self.mode == NORMAL:
                if self.show_dashboard:
                    res = self.handle_dashboard(key)
                    if res == "QUIT": break
                    continue
                if self.handle_normal(key) == "QUIT":
                    break
            elif self.mode == INSERT:
                # Proactively query LSP for ghost text if we have a word
                self.handle_insert(key)
                if self.is_python and self.mode == INSERT:
                    word = self.get_current_word()
                    if word and len(word) > 1:
                        code = "\n".join(self.lines)
                        self.ac_suggestions = self.lsp.get_completions(code, self.cursor_y + 1, self.cursor_x)
                    else:
                        self.ac_suggestions = []
            elif self.mode == COMMAND:
                if self.handle_command(key) == "QUIT":
                    break
            elif self.mode == CONFIG:
                self.handle_config(key)
            elif self.mode == AUTOCOMPLETE:
                self.handle_autocomplete(key)

    def save_state(self):
        # Limit undo stack size to 100
        if len(self.undo_stack) > 100:
            self.undo_stack.pop(0)
        self.undo_stack.append({
            'lines': list(self.lines),
            'cursor_x': self.cursor_x,
            'cursor_y': self.cursor_y
        })
        self.redo_stack.clear()

    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append({
            'lines': list(self.lines),
            'cursor_x': self.cursor_x,
            'cursor_y': self.cursor_y
        })
        state = self.undo_stack.pop()
        self.lines = state['lines']
        self.cursor_x = state['cursor_x']
        self.cursor_y = state['cursor_y']

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append({
            'lines': list(self.lines),
            'cursor_x': self.cursor_x,
            'cursor_y': self.cursor_y
        })
        state = self.redo_stack.pop()
        self.lines = state['lines']
        self.cursor_x = state['cursor_x']
        self.cursor_y = state['cursor_y']

    def handle_normal(self, key):
        self.show_dashboard = False
        if key == ord('i'):
            self.mode = INSERT
        elif key == ord(':'):
            self.mode = COMMAND
            self.command_text = ""
        elif key == ord('h'):
            self.move(-1, 0)
        elif key == ord('j'):
            self.move(0, 1)
        elif key == ord('k'):
            self.move(0, -1)
        elif key == ord('l'):
            self.move(1, 0)
        elif key == ord('x'):
            self.delete_char()
        elif key == ord('o'):
            self.newline()
            self.mode = INSERT
        elif key == 27:  # ESC
            pass  # Already in NORMAL

    def handle_insert(self, key):
        if key == 27:  # ESC
            self.mode = NORMAL
        elif key in (curses.KEY_BACKSPACE, 127):
            self.save_state()
            self.backspace()
        elif key == curses.KEY_RIGHT and self.ac_suggestions:
            # Complete first suggestion
            suggestion = self.ac_suggestions[0]
            word = self.get_current_word()
            self.save_state()
            line = self.lines[self.cursor_y]
            self.lines[self.cursor_y] = line[:self.cursor_x - len(word)] + suggestion + line[self.cursor_x:]
            self.cursor_x += (len(suggestion) - len(word))
            self.ac_suggestions = []
        elif key == 9:  # Tab
            if self.is_python:
                code = "\n".join(self.lines)
                suggestions = self.lsp.get_completions(code, self.cursor_y + 1, self.cursor_x)
                if suggestions:
                    self.ac_suggestions = suggestions
                    self.mode = AUTOCOMPLETE
                    self.ac_index = 0
                else:
                    self.save_state()
                    for _ in range(4): self.insert(' ')
            else:
                self.save_state()
                for _ in range(4): self.insert(' ')
        elif key == 10:  # Enter
            self.save_state()
            self.newline()
        elif 32 <= key <= 126:
            self.save_state()
            self.insert(chr(key))

    def handle_command(self, key):
        if key == 27:  # ESC
            self.mode = NORMAL
        elif key == 10:  # Enter
            cmd = self.command_text.strip()
            if cmd == "w":
                self.save()
                self.notify("File Saved")
                self.mode = NORMAL
            elif cmd == "q":
                return "QUIT"
            elif cmd == "wq":
                self.save()
                return "QUIT"
            elif cmd == "u":
                self.undo()
                self.mode = NORMAL
            elif cmd == "r":
                self.redo()
                self.mode = NORMAL
            elif cmd == "config":
                self.mode = CONFIG
                self.config_index = 0
            else:
                self.mode = NORMAL
        elif key in (curses.KEY_BACKSPACE, 127):
            self.command_text = self.command_text[:-1]
            if not self.command_text and key == (curses.KEY_BACKSPACE, 127):
                # This logic is a bit flawed but fine for now
                pass
        if 32 <= key <= 126:
            self.command_text += chr(key)

    def get_current_word(self):
        line = self.lines[self.cursor_y]
        start = self.cursor_x
        while start > 0 and (line[start-1].isalnum() or line[start-1] == '_'):
            start -= 1
        return line[start:self.cursor_x]

    def handle_autocomplete(self, key):
        if key == 27:  # ESC
            self.mode = INSERT
        elif key == ord('j') or key == curses.KEY_DOWN or key == 9:  # j, Down, Tab
            self.ac_index = (self.ac_index + 1) % len(self.ac_suggestions)
        elif key == ord('k') or key == curses.KEY_UP:
            self.ac_index = (self.ac_index - 1) % len(self.ac_suggestions)
        elif key == 10:  # Enter
            suggestion = self.ac_suggestions[self.ac_index]
            word = self.get_current_word()
            # Replace current word with suggestion
            self.save_state()
            line = self.lines[self.cursor_y]
            self.lines[self.cursor_y] = line[:self.cursor_x - len(word)] + suggestion + line[self.cursor_x:]
            self.cursor_x += (len(suggestion) - len(word))
            self.mode = INSERT
            self.ac_suggestions = []
        elif key == curses.KEY_RIGHT: # Accept current selection
            suggestion = self.ac_suggestions[self.ac_index]
            word = self.get_current_word()
            self.save_state()
            line = self.lines[self.cursor_y]
            self.lines[self.cursor_y] = line[:self.cursor_x - len(word)] + suggestion + line[self.cursor_x:]
            self.cursor_x += (len(suggestion) - len(word))
            self.mode = INSERT
            self.ac_suggestions = []
        else:
            self.mode = INSERT
            self.handle_insert(key)

    def hex_to_rgb(self, hex_str):
        hex_str = hex_str.lstrip('#')
        if len(hex_str) == 3:
            hex_str = ''.join([c*2 for c in hex_str])
        r = int(hex_str[0:2], 16) * 1000 // 255
        g = int(hex_str[2:4], 16) * 1000 // 255
        b = int(hex_str[4:6], 16) * 1000 // 255
        return r, g, b

    def update_color_definition(self, opt):
        if not curses.can_change_color(): return
        
        # We use color indices 10 and above for our custom colors
        idx_offset = self.config_options.index(opt) + 10
        r, g, b = self.hex_to_rgb(opt["hex"])
        curses.init_color(idx_offset, r, g, b)
        
        # Update pairs
        bg_opt = next(o for o in self.config_options if o.get("bg"))
        fg_opt = next(o for o in self.config_options if o.get("fg"))
        bg_idx = self.config_options.index(bg_opt) + 10
        fg_idx = self.config_options.index(fg_opt) + 10
        
        if opt.get("bg") or opt.get("fg"):
            # Update all pairs that use default background
            for o in self.config_options:
                if o["type"] == "color":
                    o_idx = self.config_options.index(o) + 10
                    curses.init_pair(o["pair"], o_idx, bg_idx)
            # Special case for pair 5 (default fg/bg)
            curses.init_pair(5, fg_idx, bg_idx)
        else:
            curses.init_pair(opt["pair"], idx_offset, bg_idx)

    def handle_config(self, key):
        if self.is_inputting:
            if key == 10:  # Enter
                opt = self.config_options[self.config_index]
                if self.config_input.startswith('#') and len(self.config_input) in (4, 7):
                    opt["hex"] = self.config_input
                    self.update_color_definition(opt)
                self.is_inputting = False
                self.config_input = ""
            elif key == 27:  # ESC
                self.is_inputting = False
                self.config_input = ""
            elif key in (curses.KEY_BACKSPACE, 127):
                self.config_input = self.config_input[:-1]
            elif 32 <= key <= 126:
                self.config_input += chr(key)
            return

        if key == 27 or key == ord('q'):  # ESC or q
            self.mode = NORMAL
        elif key == ord('j') or key == curses.KEY_DOWN:
            self.config_index = (self.config_index + 1) % len(self.config_options)
        elif key == ord('k') or key == curses.KEY_UP:
            self.config_index = (self.config_index - 1) % len(self.config_options)
        elif key == 10 or key == ord(' '):  # Enter or Space
            opt = self.config_options[self.config_index]
            if opt["type"] == "toggle":
                current = getattr(self, opt["attr"])
                setattr(self, opt["attr"], not current)
            elif opt["type"] == "color":
                self.is_inputting = True
                self.config_input = opt["hex"]

    def draw_config_menu(self):
        h, w = self.stdscr.getmaxyx()
        menu_h = len(self.config_options) + 6
        menu_w = 50
        start_y = (h - menu_h) // 2
        start_x = (w - menu_w) // 2

        # Draw box
        for i in range(menu_h):
            for j in range(menu_w):
                char = " "
                if i == 0 or i == menu_h - 1: char = "-"
                elif j == 0 or j == menu_w - 1: char = "|"
                self.stdscr.addstr(start_y + i, start_x + j, char)

        self.stdscr.addstr(start_y + 1, start_x + 2, " Configuration Menu ", curses.A_BOLD)
        self.stdscr.addstr(start_y + 2, start_x + 2, " (j/k: navigate, Enter: edit) ", curses.A_DIM)

        for i, opt in enumerate(self.config_options):
            is_selected = (i == self.config_index)
            style = curses.A_REVERSE if is_selected else curses.A_NORMAL
            
            label = f"{opt['name']}: "
            self.stdscr.addstr(start_y + 4 + i, start_x + 2, label)
            
            pos_x = start_x + 2 + len(label)
            
            if opt["type"] == "toggle":
                val = "[X]" if getattr(self, opt["attr"]) else "[ ]"
                self.stdscr.addstr(start_y + 4 + i, pos_x, val, style)
            elif opt["type"] == "color":
                hex_val = opt["hex"]
                if is_selected and self.is_inputting:
                    hex_val = self.config_input + "_"
                
                self.stdscr.addstr(start_y + 4 + i, pos_x, hex_val, style)
                
                # Preview square
                preview_idx = i + 10
                curses.init_pair(100 + i, curses.COLOR_WHITE, preview_idx)
                self.stdscr.addstr(start_y + 4 + i, pos_x + 10, "  ", curses.color_pair(100 + i))

        if self.is_inputting:
            self.stdscr.addstr(start_y + menu_h - 2, start_x + 2, " Typing hex... (e.g. #FF0000) ", curses.A_DIM)

        self.stdscr.refresh()

    def delete_char(self):
        self.save_state()
        line = self.lines[self.cursor_y]
        if self.cursor_x < len(line):
            self.lines[self.cursor_y] = line[:self.cursor_x] + line[self.cursor_x+1:]

        self.stdscr.refresh()

    def get_line_colors(self, line):
        colors = [0] * len(line)
        
        # Simple regex-based highlighting
        keywords = r'\b(if|else|elif|while|for|in|import|from|as|return|yield|try|except|finally|with|pass|break|continue|None|True|False|and|or|not|is|lambda)\b'
        def_class = r'\b(def|class)\b'
        strings = r'(\".*?\"|\'.*?\')'
        comments = r'#.*$'

        for match in re.finditer(keywords, line):
            for i in range(match.start(), match.end()):
                colors[i] = curses.color_pair(1)
        
        for match in re.finditer(def_class, line):
            for i in range(match.start(), match.end()):
                colors[i] = curses.color_pair(4) | curses.A_BOLD

        for match in re.finditer(strings, line):
            for i in range(match.start(), match.end()):
                colors[i] = curses.color_pair(2)

        for match in re.finditer(comments, line):
            for i in range(match.start(), match.end()):
                colors[i] = curses.color_pair(3)

        return colors

    def get_wrapped_lines(self):
        h, w = self.stdscr.getmaxyx()
        gutter_width = 5 if self.show_line_numbers else 0
        width = w - 1 - gutter_width
        wrapped = []
        for i, line in enumerate(self.lines):
            if not line:
                wrapped.append((i, 0, 0))
                continue
            for j in range(0, len(line), width):
                wrapped.append((i, j, min(j + width, len(line))))
        return wrapped

    def draw_dashboard(self):
        h, w = self.stdscr.getmaxyx()
        logo = [
            "  ██████╗ ██╗   ██╗██████╗ ██╗██╗  ██╗",
            "  ██╔══██╗╚██╗ ██╔╝██╔══██╗██║╚██╗██╔╝",
            "  ██████╔╝ ╚████╔╝ ██████╔╝██║ ╚███╔╝ ",
            "  ██╔═══╝   ╚██╔╝  ██╔══██╗██║ ██╔██╗ ",
            "  ██║        ██║   ██║  ██║██║██╔╝ ██╗",
            "  ╚═╝        ╚═╝   ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝",
            "",
            "        Modular • Fast • Tokyonight (Changeable)",
            "",
            "       [i] Notebook Mode    [:] Command ",
            "       [q] Quit             [u] Update  "
        ]
        start_y = (h - len(logo)) // 2
        for i, line in enumerate(logo):
            style = curses.color_pair(1) | curses.A_BOLD if i < 6 else curses.color_pair(5)
            self.stdscr.addstr(start_y + i, (w - len(line)) // 2, line, style)

    def handle_dashboard(self, key):
        if key == ord('i'):
            self.show_dashboard = False
            self.mode = INSERT
        elif key == ord(':'):
            self.show_dashboard = False
            self.mode = COMMAND
            self.command_text = ""
        elif key == ord('q'):
            return "QUIT"
        return None

    def notify(self, msg):
        self.notifications.append({"msg": msg, "time": time.time()})

    def draw_notifications(self):
        h, w = self.stdscr.getmaxyx()
        now = time.time()
        self.notifications = [n for n in self.notifications if now - n["time"] < 3]
        for i, n in enumerate(self.notifications):
            msg = f" {n['msg']} "
            self.stdscr.addstr(h - 4 - i, w - len(msg) - 2, msg, curses.color_pair(21) | curses.A_BOLD)

    def draw_statusline(self, h, w):
        # Background for statusline
        self.stdscr.addstr(h - 2, 0, " " * (w - 1), curses.color_pair(23))
        
        # Mode Segment
        mode_colors = {NORMAL: 20, INSERT: 21, COMMAND: 22, CONFIG: 1}
        mode_pair = mode_colors.get(self.mode, 20)
        mode_str = f" {self.mode} "
        self.stdscr.addstr(h - 2, 0, mode_str, curses.color_pair(mode_pair) | curses.A_BOLD)
        
        # Filename Segment
        filename = self.filename or "[No Name]"
        self.stdscr.addstr(h - 2, len(mode_str) + 1, f" {filename} ", curses.color_pair(23))
        
        # Position Segment
        pos_str = f" LOC: {self.cursor_y + 1}:{self.cursor_x + 1} "
        self.stdscr.addstr(h - 2, w - len(pos_str) - 1, pos_str, curses.color_pair(20) | curses.A_BOLD)

    def draw_hintbar(self, h, w):
        hints = " [i] Insert  [:] Command  [h/j/k/l] Move  [u] Undo  [r] Redo "
        self.stdscr.addstr(h - 1, 0, hints[:w-1], curses.A_DIM)

    def draw(self):
        self.stdscr.erase()
        h, w = self.stdscr.getmaxyx()
        self.stdscr.bkgd(' ', curses.color_pair(5))

        if self.show_dashboard:
            self.draw_dashboard()
            self.stdscr.refresh()
            return

        gutter_width = 5 if self.show_line_numbers else 0
        wrapped = self.get_wrapped_lines()
        
        max_scroll = max(0, len(wrapped) - (h - 2))
        self.scroll = min(self.scroll, max_scroll)
        visible_wrapped = wrapped[self.scroll:self.scroll + h - 2]
        
        cursor_screen_y = -1
        cursor_screen_x = -1

        for i, (line_idx, start, end) in enumerate(visible_wrapped):
            if self.show_line_numbers:
                if start == 0:
                    line_num_str = f"{line_idx + 1:4} "
                    self.stdscr.addstr(i, 0, line_num_str, curses.color_pair(3) | curses.A_DIM)
                else:
                    self.stdscr.addstr(i, 0, "     ")

            line = self.lines[line_idx]
            colors = self.get_line_colors(line)
            segment = line[start:end]
            seg_colors = colors[start:end]
            
            for j, (char, color) in enumerate(zip(segment, seg_colors)):
                self.stdscr.addch(i, j + gutter_width, char, color)
            
            if line_idx == self.cursor_y and start <= self.cursor_x <= end:
                if self.cursor_x < end or (self.cursor_x == end and end == len(line)):
                    cursor_screen_y = i
                    cursor_screen_x = self.cursor_x - start + gutter_width

        if self.mode == CONFIG:
            self.draw_config_menu()
            return

        self.draw_statusline(h, w)
        self.draw_notifications()

        # Ghost Text Logic
        if cursor_screen_y != -1 and self.mode in (INSERT, AUTOCOMPLETE) and self.ac_suggestions:
            suggestion = self.ac_suggestions[self.ac_index if self.mode == AUTOCOMPLETE else 0]
            word = self.get_current_word()
            if suggestion.startswith(word):
                ghost_text = suggestion[len(word):]
                if ghost_text and cursor_screen_x + len(ghost_text) < w:
                    self.stdscr.addstr(cursor_screen_y, cursor_screen_x, ghost_text, curses.A_DIM | curses.A_ITALIC)

        if self.mode == AUTOCOMPLETE:
            self.draw_autocomplete_popup(cursor_screen_y, cursor_screen_x)
            return

        if self.mode == COMMAND:
            self.stdscr.addstr(h - 1, 0, ":" + self.command_text[:w - 2], curses.A_BOLD)
            self.stdscr.move(h - 1, len(self.command_text) + 1)
        else:
            self.draw_hintbar(h, w)
            if cursor_screen_y != -1:
                self.stdscr.move(cursor_screen_y, cursor_screen_x)

        self.stdscr.refresh()

    def move(self, dx, dy):
        # Vertical movement in wrapped world is tricky.
        # For now, let's keep dy as logical line movement, 
        # but the user might expect screen line movement.
        # Nvim 'j' and 'k' move by logical lines unless prefixed with 'g'.
        # However, many users prefer 'j' to move to the next screen line.
        # Let's stick to logical lines for now as it's simpler and closer to default vim.
        
        self.cursor_y = max(0, min(self.cursor_y + dy, len(self.lines) - 1))
        self.cursor_x = max(0, min(self.cursor_x + dx, len(self.lines[self.cursor_y])))
        
        # Update scroll to keep cursor visible
        h, w = self.stdscr.getmaxyx()
        wrapped = self.get_wrapped_lines()
        
        # Find which wrapped line the cursor is on
        cursor_wrapped_idx = -1
        for i, (line_idx, start, end) in enumerate(wrapped):
            if line_idx == self.cursor_y and start <= self.cursor_x <= end:
                if self.cursor_x < end or (self.cursor_x == end and end == len(self.lines[line_idx])):
                    cursor_wrapped_idx = i
                    break
        
        if cursor_wrapped_idx != -1:
            if cursor_wrapped_idx < self.scroll:
                self.scroll = cursor_wrapped_idx
            elif cursor_wrapped_idx >= self.scroll + h - 2:
                self.scroll = cursor_wrapped_idx - (h - 3)

    def insert(self, ch):
        line = self.lines[self.cursor_y]
        self.lines[self.cursor_y] = line[:self.cursor_x] + ch + line[self.cursor_x:]
        self.cursor_x += 1

    def backspace(self):
        if self.cursor_x > 0:
            line = self.lines[self.cursor_y]
            self.lines[self.cursor_y] = line[:self.cursor_x - 1] + line[self.cursor_x:]
            self.cursor_x -= 1
        elif self.cursor_y > 0:
            prev = self.lines[self.cursor_y - 1]
            self.cursor_x = len(prev)
            self.lines[self.cursor_y - 1] += self.lines[self.cursor_y]
            del self.lines[self.cursor_y]
            self.cursor_y -= 1

    def newline(self):
        line = self.lines[self.cursor_y]
        self.lines[self.cursor_y] = line[:self.cursor_x]
        self.lines.insert(self.cursor_y + 1, line[self.cursor_x:])
        self.cursor_y += 1
        self.cursor_x = 0

    def save(self):
        if not self.filename:
            return
        with open(self.filename, "w", encoding="utf-8") as f:
            f.write("\n".join(self.lines))

    def draw_autocomplete_popup(self, cy, cx):
        h, w = self.stdscr.getmaxyx()
        if not self.ac_suggestions: return
        
        visible_count = min(len(self.ac_suggestions), 10)
        visible_items = self.ac_suggestions[:visible_count]
        
        pop_w = max(len(s) for s in visible_items) + 4
        pop_h = visible_count
        
        # Boundary checks
        if cx + pop_w >= w:
            px = max(0, w - pop_w - 1)
        else:
            px = cx
            
        if cy + pop_h + 1 >= h - 2:
            py = max(0, cy - pop_h)
        else:
            py = cy + 1
            
        for i, s in enumerate(visible_items):
            if py + i >= h - 2: break # Don't draw over statusline
            style = curses.color_pair(21) | curses.A_BOLD if i == self.ac_index else curses.color_pair(23)
            # Ensure px + pop_w doesn't overshoot
            label = f" {s} ".ljust(pop_w)
            if px + len(label) >= w:
                label = label[:w - px - 1]
            try:
                self.stdscr.addstr(py + i, px, label, style)
            except curses.error:
                pass

class PythonLSP:
    def __init__(self):
        # Try to find jedi in common venv location
        try:
            import jedi
        except ImportError:
            venv_path = "/media/bentley/2TB/repos/.venv"
            if os.path.exists(venv_path):
                lib_dir = os.path.join(venv_path, "lib")
                if os.path.exists(lib_dir):
                    p_dirs = [d for d in os.listdir(lib_dir) if d.startswith("python")]
                    if p_dirs:
                        site_pkgs = os.path.join(lib_dir, p_dirs[0], "site-packages")
                        if site_pkgs not in sys.path:
                            sys.path.append(site_pkgs)
        
        try:
            import jedi
            self.jedi = jedi
        except ImportError:
            self.jedi = None

    def get_completions(self, code, line, column):
        if not self.jedi:
            return []
        try:
            script = self.jedi.Script(code)
            completions = script.complete(line, column)
            return [c.name for c in completions]
        except:
            return []

def main(stdscr):
    filename = sys.argv[1] if len(sys.argv) > 1 else None
    editor = Editor(stdscr, filename)
    editor.run()

if __name__ == "__main__":
    curses.wrapper(main)
