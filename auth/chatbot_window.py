# auth/chatbot_window.py
# PV Solar AI Chatbot — full in-app chat powered by Anthropic Claude API.

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import threading
import json
import os
import sys
import urllib.request
import urllib.error

# ── Palette ───────────────────────────────────────────────────────────────────
BG       = "#0d0d1a"
PANEL    = "#1a1a2e"
CARD     = "#12121f"
CARD2    = "#1e1e35"
ACCENT   = "#f5a623"
ACCENT2  = "#4fc3f7"
TEXT     = "#e0e0e0"
TEXT_DIM = "#888888"
SUCCESS  = "#66bb6a"
ERROR    = "#ef5350"
BORDER   = "#2a2a4a"
WARN     = "#ffd54f"

API_URL    = "https://api.anthropic.com/v1/messages"
API_VER    = "2023-06-01"
MODEL      = "claude-opus-4-7"
MAX_TOKENS = 1024

SYSTEM_PROMPT = """You are an expert solar PV system design assistant specialising in off-grid and hybrid systems for Ghana and West Africa.

You have deep knowledge of:
- Solar PV modules: PERC, TOPCon, HJT, bifacial — LONGi, JA Solar, Jinko, Canadian Solar, REC, Trina
- Battery storage: LiFePO4 (Pylontech, BYD, CATL, Growatt), lead-acid (Trojan, Rolls)
- Inverters: Victron (MultiPlus, Quattro), Growatt (SPF/MIN/MAX), Goodwe, SMA, Deye, Sofar, Huawei
- System sizing: load estimation, PV array sizing, battery autonomy, inverter selection, cable sizing
- Ghana electrical standards: BS 7671:2018 (18th Edition), 415/230V 50Hz, ECG distribution
- Ghana market pricing (GHS, April 2026), import duty, VAT, installation costs
- PURC tariff structures, ECG tariff ~GHS 2.00/kWh residential, net metering regulations
- Economic analysis: payback, NPV (25-year DCF), ROI for Ghana off-grid projects
- Off-grid and mini-grid installation for tropical climates: IP ratings, heat derating, BS 7430 earthing
- IEC standards: IEC 61730, IEC 61215, IEC 62109, IEC 62485; BS EN 61386, BS EN 60947-2

Ghana design assumptions:
- Peak sun hours: 5 hrs/day | System efficiency: 0.75 | LiFePO4 DoD: 80%
- Battery autonomy: 1 day standard | 48V DC bus for systems ≥3 kWh
- ECG tariff (2026): ~GHS 2.00/kWh residential

Provide practical, actionable advice. Show calculations step-by-step. Quote realistic GHS prices. Reference standards where applicable."""


def _root():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _config_path():
    return os.path.join(_root(), "data", "app_config.json")


def _load_api_key():
    try:
        with open(_config_path(), "r", encoding="utf-8") as f:
            return json.load(f).get("anthropic_api_key", "")
    except Exception:
        return ""


def _save_api_key(key: str):
    path = _config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cfg = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        pass
    cfg["anthropic_api_key"] = key
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


class ChatbotWindow(tk.Toplevel):

    def __init__(self, master, current_user: dict = None):
        super().__init__(master)
        self._user     = current_user or {}
        self._messages = []
        self._busy     = False

        self.title("PV Solar AI Chatbot")
        w, h = 860, 660
        self.geometry(f"{w}x{h}")
        self.minsize(640, 500)
        self.configure(bg=BG)
        self.resizable(True, True)

        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        self._build()

    # ── Build ─────────────────────────────────────────────────────────────────
    def _build(self):
        self._build_header()
        self._build_chat_area()
        self._build_input_bar()
        self._build_toolbar()

    def _build_header(self):
        hdr = tk.Frame(self, bg=ACCENT, height=52)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        tk.Label(hdr, text="🤖  PV Solar AI Chatbot",
                 font=("Segoe UI", 13, "bold"),
                 bg=ACCENT, fg="#1e1e2e").pack(side="left", padx=18, pady=12)

        tk.Label(hdr, text="Ghana Off-Grid Solar Expert · Powered by Claude",
                 font=("Segoe UI", 9), bg=ACCENT, fg="#4a3000"
                 ).pack(side="left")

        tk.Button(
            hdr, text="🔑  API Key",
            font=("Segoe UI", 9),
            bg="#1e1e2e", fg=ACCENT2,
            activebackground="#12121f",
            relief="flat", cursor="hand2", padx=10, pady=5,
            command=self._set_api_key,
        ).pack(side="right", padx=12, pady=8)

    def _build_chat_area(self):
        frame = tk.Frame(self, bg=BG)
        frame.pack(fill="both", expand=True, padx=12, pady=(8, 0))

        vscroll = ttk.Scrollbar(frame, orient="vertical")
        vscroll.pack(side="right", fill="y")

        self._chat = tk.Text(
            frame,
            bg=CARD, fg=TEXT,
            font=("Segoe UI", 10),
            wrap="word",
            state="disabled",
            relief="flat",
            padx=14, pady=10,
            yscrollcommand=vscroll.set,
            cursor="arrow",
            spacing3=6,
        )
        self._chat.pack(side="left", fill="both", expand=True)
        vscroll.config(command=self._chat.yview)

        # Tags
        self._chat.tag_configure("user_lbl",  foreground=ACCENT,  font=("Segoe UI", 9, "bold"))
        self._chat.tag_configure("user_msg",  foreground=TEXT,     font=("Segoe UI", 10), lmargin1=10, lmargin2=10)
        self._chat.tag_configure("ai_lbl",    foreground=ACCENT2,  font=("Segoe UI", 9, "bold"))
        self._chat.tag_configure("ai_msg",    foreground="#d0e8ff", font=("Segoe UI", 10), lmargin1=10, lmargin2=10)
        self._chat.tag_configure("err_lbl",   foreground=ERROR,    font=("Segoe UI", 9, "bold"))
        self._chat.tag_configure("err_msg",   foreground=ERROR,    font=("Segoe UI", 10, "italic"), lmargin1=10, lmargin2=10)
        self._chat.tag_configure("sys_msg",   foreground=TEXT_DIM, font=("Segoe UI", 9, "italic"), lmargin1=10, lmargin2=10)
        self._chat.tag_configure("thinking",  foreground=WARN,     font=("Segoe UI", 9, "italic"), lmargin1=10, lmargin2=10)
        self._chat.tag_configure("divider",   foreground=BORDER)

        self._insert("Welcome! Ask me anything about solar PV system design for Ghana.\n"
                     "Examples:\n"
                     "  • Size a 10 kWh/day off-grid system for a home in Accra\n"
                     "  • Compare Growatt SPF 5000 vs Victron MultiPlus-II 5000\n"
                     "  • What cable size for 50A at 48V over 10 metres?\n"
                     "  • Calculate payback for 3 kWp at GHS 2.00/kWh ECG tariff", "sys_msg")
        self._divider()

    def _build_input_bar(self):
        bar = tk.Frame(self, bg=PANEL, padx=12, pady=10)
        bar.pack(fill="x")

        self._input_var = tk.StringVar()
        entry = tk.Entry(
            bar,
            textvariable=self._input_var,
            font=("Segoe UI", 11),
            bg=CARD2, fg=TEXT,
            insertbackground=ACCENT2,
            relief="flat",
        )
        entry.pack(side="left", fill="both", expand=True, ipady=8, padx=(0, 8))
        entry.bind("<Return>", lambda e: self._send())
        entry.focus_set()

        self._send_btn = tk.Button(
            bar,
            text="  Send  ▶",
            font=("Segoe UI", 10, "bold"),
            bg=ACCENT, fg="#1e1e2e",
            activebackground="#d4911a",
            relief="flat", cursor="hand2",
            padx=14, pady=8,
            command=self._send,
        )
        self._send_btn.pack(side="right")

    def _build_toolbar(self):
        tb = tk.Frame(self, bg=BG, padx=12, pady=6)
        tb.pack(fill="x")

        tk.Button(tb, text="🗑  Clear Chat",
                  font=("Segoe UI", 8),
                  bg=PANEL, fg=TEXT_DIM,
                  activebackground=BORDER,
                  relief="flat", cursor="hand2", padx=10, pady=4,
                  command=self._clear_chat).pack(side="left")

        tk.Button(tb, text="💡  Example Questions",
                  font=("Segoe UI", 8),
                  bg=PANEL, fg=ACCENT2,
                  activebackground=BORDER,
                  relief="flat", cursor="hand2", padx=10, pady=4,
                  command=self._show_examples).pack(side="left", padx=(6, 0))

        self._status_var = tk.StringVar(value="Ready")
        tk.Label(tb, textvariable=self._status_var,
                 font=("Segoe UI", 8), bg=BG, fg=TEXT_DIM).pack(side="right")

    # ── Send / API ────────────────────────────────────────────────────────────
    def _send(self):
        if self._busy:
            return
        text = self._input_var.get().strip()
        if not text:
            return

        api_key = _load_api_key()
        if not api_key:
            api_key = self._prompt_api_key()
            if not api_key:
                return

        self._input_var.set("")
        self._busy = True
        self._send_btn.config(state="disabled")
        self._status_var.set("Thinking...")

        self._messages.append({"role": "user", "content": text})

        name = self._user.get("full_name") or self._user.get("username") or "You"
        self._insert(f"\n👤  {name}", "user_lbl")
        self._insert(f"\n{text}\n", "user_msg")
        self._divider()
        self._insert("\n🤖  Solar AI\n", "ai_lbl")
        self._insert("Thinking...\n", "thinking")
        self._thinking_end = self._chat.index("end")

        threading.Thread(target=self._api_thread, args=(api_key,), daemon=True).start()

    def _api_thread(self, api_key):
        result = self._call_api(api_key)
        try:
            self.after(0, lambda: self._handle_response(result))
        except Exception:
            pass

    def _call_api(self, api_key):
        payload = {
            "model":      MODEL,
            "max_tokens": MAX_TOKENS,
            "system":     SYSTEM_PROMPT,
            "messages":   self._messages,
        }
        req = urllib.request.Request(
            API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-api-key":         api_key,
                "anthropic-version": API_VER,
                "content-type":      "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                body = json.loads(resp.read())
            return body["content"][0]["text"]
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            try:
                msg = json.loads(raw).get("error", {}).get("message", raw)
            except Exception:
                msg = raw[:300]
            return f"__ERR__HTTP {e.code} — {msg}"
        except urllib.error.URLError as e:
            return f"__ERR__Network error — {e.reason}"
        except Exception as e:
            return f"__ERR__{e}"

    def _handle_response(self, result):
        self._busy = False
        self._send_btn.config(state="normal")
        self._status_var.set("Ready")

        # Remove "Thinking..." line
        try:
            self._chat.config(state="normal")
            self._chat.delete("end-3l linestart", "end-1c")
            self._chat.config(state="disabled")
        except Exception:
            pass

        if result.startswith("__ERR__"):
            self._insert(result[7:] + "\n", "err_msg")
            self._divider()
        else:
            self._messages.append({"role": "assistant", "content": result})
            self._insert(result + "\n", "ai_msg")
            self._divider()

    # ── Text helpers ──────────────────────────────────────────────────────────
    def _insert(self, text, tag="sys_msg"):
        self._chat.config(state="normal")
        self._chat.insert("end", text, tag)
        self._chat.config(state="disabled")
        self._chat.see("end")

    def _divider(self):
        self._insert("\n" + "─" * 68 + "\n", "divider")

    # ── Actions ───────────────────────────────────────────────────────────────
    def _prompt_api_key(self):
        """Show inline API key prompt. Returns key or empty string."""
        key = simpledialog.askstring(
            "Anthropic API Key Required",
            "Enter your Anthropic API key to use the chatbot.\n\n"
            "Get one at: console.anthropic.com → API Keys\n"
            "(Separate from Claude Pro — requires API billing account)",
            parent=self, show="•",
        )
        if key and key.strip():
            _save_api_key(key.strip())
            return key.strip()
        return ""

    def _set_api_key(self):
        current = _load_api_key()
        masked  = (f"{current[:8]}...{current[-4:]}"
                   if len(current) > 12 else ("set" if current else "not set"))
        key = simpledialog.askstring(
            "Anthropic API Key",
            f"Current key: {masked}\n\nPaste new key (leave blank to cancel):",
            parent=self, show="•",
        )
        if key and key.strip():
            _save_api_key(key.strip())
            messagebox.showinfo("Saved", "API key saved.", parent=self)

    def _clear_chat(self):
        if self._busy:
            return
        if messagebox.askyesno("Clear Chat", "Clear conversation history?", parent=self):
            self._messages = []
            self._chat.config(state="normal")
            self._chat.delete("1.0", "end")
            self._chat.config(state="disabled")
            self._insert("Chat cleared. Start a new conversation.\n", "sys_msg")
            self._divider()

    def _show_examples(self):
        questions = [
            "Size an off-grid system for a 3-bedroom home in Accra using 10 kWh/day",
            "What battery capacity for 2 days autonomy at 8 kWh/day?",
            "Compare Growatt SPF 5000 vs Victron MultiPlus-II 5000 for off-grid use",
            "How many 400Wp panels for a 2.4 kWp array?",
            "Cable size for a 50A DC circuit at 48V over 10 metres?",
            "Calculate payback: 3 kWp system at GHS 2.00/kWh ECG tariff",
            "Earthing requirements for solar PV under BS 7430",
            "Difference between MPPT and PWM charge controllers",
            "Best LiFePO4 battery for a 5 kW off-grid system in Ghana",
            "What protection devices are required on a 48V solar system?",
        ]
        dlg = tk.Toplevel(self)
        dlg.title("Example Questions")
        dlg.geometry("540x360")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.grab_set()

        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        dlg.geometry(f"540x360+{(sw-540)//2}+{(sh-360)//2}")

        tk.Label(dlg, text="Click a question to use it",
                 font=("Segoe UI", 10, "bold"),
                 bg=BG, fg=ACCENT2).pack(pady=(14, 6))

        for q in questions:
            tk.Button(
                dlg, text=q,
                font=("Segoe UI", 9),
                bg=CARD2, fg=TEXT,
                activebackground=PANEL,
                relief="flat", cursor="hand2",
                anchor="w", padx=12, pady=5,
                wraplength=510, justify="left",
                command=lambda t=q, d=dlg: (
                    self._input_var.set(t),
                    d.destroy(),
                ),
            ).pack(fill="x", padx=14, pady=2)

        tk.Button(dlg, text="Close",
                  font=("Segoe UI", 9),
                  bg=PANEL, fg=TEXT_DIM,
                  relief="flat", cursor="hand2", pady=6,
                  command=dlg.destroy).pack(pady=(6, 12), padx=14, fill="x")
