# auth/login_window.py
# Login / Sign-Up window — shown before the dashboard.

import tkinter as tk
from auth.user_store import authenticate, create_user, update_last_login

# ── Palette (matches main app) ────────────────────────────────────────────────
BG       = "#0d0d1a"
PANEL    = "#1a1a2e"
CARD     = "#252545"
ACCENT   = "#f5a623"
ACCENT2  = "#4fc3f7"
TEXT     = "#e0e0e0"
TEXT_DIM = "#888888"
SUCCESS  = "#66bb6a"
ERROR    = "#ef5350"
BORDER   = "#3a3a5c"
DARK_BT  = "#12121f"


class LoginWindow(tk.Toplevel):
    """Modal login / sign-up window.
    Sets self.result_user to the authenticated user dict on success,
    or leaves it None if the user closes the window.
    """

    def __init__(self, master):
        super().__init__(master)
        self.result_user = None

        self.title("Solar PV Designer Lite — Sign In")
        self.geometry("500x640")
        self.resizable(False, False)
        self.configure(bg=BG)

        # Center on screen
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self._cx = (sw - 500) // 2
        self._cy = (sh - 640) // 2
        self.geometry(f"500x640+{self._cx}+{self._cy}")

        self.grab_set()   # modal — blocks other windows
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build()

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build(self):
        # ── Top brand bar ──
        hdr = tk.Frame(self, bg=ACCENT, height=60)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="☀  Solar PV Designer Lite",
                 font=("Segoe UI", 15, "bold"),
                 bg=ACCENT, fg="#1e1e2e").pack(side="left", padx=22, pady=14)
        tk.Label(hdr, text="Ghana",
                 font=("Segoe UI", 9), bg=ACCENT, fg="#4a3000").pack(side="right", padx=22)

        tk.Label(self, text="Off-Grid System Sizing Platform",
                 font=("Segoe UI", 9), bg=BG, fg=TEXT_DIM).pack(pady=(14, 4))

        # ── Main card ──
        card = tk.Frame(self, bg=CARD, padx=30, pady=22,
                        highlightbackground=BORDER, highlightthickness=1)
        card.pack(padx=36, pady=10, fill="both", expand=True)

        # Tab switcher
        tab_row = tk.Frame(card, bg=CARD)
        tab_row.pack(fill="x", pady=(0, 16))

        self._tab_login_btn = tk.Button(
            tab_row, text="Login",
            font=("Segoe UI", 10, "bold"),
            bg=ACCENT, fg="#1e1e2e", relief="flat",
            padx=22, pady=6, cursor="hand2",
            command=lambda: self._show_tab("login"))
        self._tab_login_btn.pack(side="left")

        self._tab_signup_btn = tk.Button(
            tab_row, text="Sign Up",
            font=("Segoe UI", 10, "bold"),
            bg=CARD, fg=TEXT_DIM, relief="flat",
            padx=22, pady=6, cursor="hand2",
            command=lambda: self._show_tab("signup"))
        self._tab_signup_btn.pack(side="left", padx=(6, 0))

        # Divider
        tk.Frame(card, bg=BORDER, height=1).pack(fill="x", pady=(0, 14))

        # Forms (only one visible at a time)
        self._login_frm  = tk.Frame(card, bg=CARD)
        self._signup_frm = tk.Frame(card, bg=CARD)
        self._build_login_form(self._login_frm)
        self._build_signup_form(self._signup_frm)

        self._show_tab("login")

        # Footer hint
        tk.Label(self, text="Default admin  →  username: admin   password: admin123",
                 font=("Segoe UI", 8), bg=BG, fg=TEXT_DIM).pack(pady=(4, 10))

    # ── Tab switcher ─────────────────────────────────────────────────────────
    def _show_tab(self, tab):
        if tab == "login":
            self._signup_frm.pack_forget()
            self._login_frm.pack(fill="x")
            self._tab_login_btn.config(bg=ACCENT, fg="#1e1e2e")
            self._tab_signup_btn.config(bg=CARD,   fg=TEXT_DIM)
            self.geometry(f"500x640+{self._cx}+{self._cy}")
            self._le_user.focus_set()
        else:
            self._login_frm.pack_forget()
            self._signup_frm.pack(fill="x")
            self._tab_login_btn.config(bg=CARD,   fg=TEXT_DIM)
            self._tab_signup_btn.config(bg=ACCENT, fg="#1e1e2e")
            self.geometry(f"500x800+{self._cx}+{self._cy}")
            self._se_name.focus_set()

    # ── Field helper ─────────────────────────────────────────────────────────
    def _field(self, parent, label, show=""):
        tk.Label(parent, text=label,
                 font=("Segoe UI", 8, "bold"), bg=CARD, fg=TEXT_DIM
                 ).pack(anchor="w", pady=(10, 2))
        var = tk.StringVar()
        entry = tk.Entry(parent, textvariable=var,
                         font=("Segoe UI", 11),
                         bg=DARK_BT, fg=TEXT,
                         insertbackground=ACCENT2,
                         relief="flat", show=show)
        entry.pack(fill="x", ipady=7)
        return var, entry

    # ── Login form ────────────────────────────────────────────────────────────
    def _build_login_form(self, parent):
        self._lv_user, self._le_user = self._field(parent, "USERNAME")
        self._lv_pass, le_pass       = self._field(parent, "PASSWORD", show="•")
        le_pass.bind("<Return>", lambda e: self._do_login())

        self._login_err = tk.StringVar()
        tk.Label(parent, textvariable=self._login_err,
                 font=("Segoe UI", 9), bg=CARD, fg=ERROR,
                 wraplength=380).pack(anchor="w", pady=(6, 0))

        tk.Button(parent, text="  Login  →  ",
                  font=("Segoe UI", 11, "bold"),
                  bg=ACCENT, fg="#1e1e2e", activebackground="#d4911a",
                  relief="flat", cursor="hand2", pady=9,
                  command=self._do_login).pack(fill="x", pady=(14, 0))

    # ── Signup form ───────────────────────────────────────────────────────────
    def _build_signup_form(self, parent):
        self._sv_name,  self._se_name  = self._field(parent, "FULL NAME")
        self._sv_user,  _              = self._field(parent, "USERNAME  (letters, numbers, _ -)")
        self._sv_email, _              = self._field(parent, "EMAIL  (optional)")
        self._sv_pass,  _              = self._field(parent, "PASSWORD  (min 6 characters)", show="•")
        self._sv_pass2, se_pass2       = self._field(parent, "CONFIRM PASSWORD", show="•")
        se_pass2.bind("<Return>", lambda e: self._do_signup())

        self._signup_msg = tk.StringVar()
        self._signup_msg_lbl = tk.Label(parent, textvariable=self._signup_msg,
                                        font=("Segoe UI", 9), bg=CARD, fg=ERROR,
                                        wraplength=380)
        self._signup_msg_lbl.pack(anchor="w", pady=(6, 0))

        tk.Button(parent, text="  Create Account  →  ",
                  font=("Segoe UI", 11, "bold"),
                  bg=SUCCESS, fg="#0d200d", activebackground="#4caf50",
                  relief="flat", cursor="hand2", pady=9,
                  command=self._do_signup).pack(fill="x", pady=(12, 0))

    # ── Actions ───────────────────────────────────────────────────────────────
    def _do_login(self):
        self._login_err.set("")
        uname = self._lv_user.get().strip()
        pwd   = self._lv_pass.get()
        if not uname or not pwd:
            self._login_err.set("Please enter both username and password.")
            return
        user = authenticate(uname, pwd)
        if user:
            update_last_login(user["username"])
            self.result_user = user
            self.grab_release()
            self.destroy()
        else:
            self._login_err.set("Invalid username or password.")

    def _do_signup(self):
        self._signup_msg.set("")
        self._signup_msg_lbl.config(fg=ERROR)
        full  = self._sv_name.get().strip()
        uname = self._sv_user.get().strip()
        email = self._sv_email.get().strip()
        pwd   = self._sv_pass.get()
        pwd2  = self._sv_pass2.get()

        if not uname or not pwd:
            self._signup_msg.set("Username and password are required.")
            return
        if pwd != pwd2:
            self._signup_msg.set("Passwords do not match.")
            return

        ok, msg = create_user(uname, pwd, full, email)
        if ok:
            user = authenticate(uname, pwd)
            update_last_login(user["username"])
            self.result_user = user
            self.grab_release()
            self.destroy()
        else:
            self._signup_msg.set(msg)

    def _on_close(self):
        self.result_user = None
        self.grab_release()
        self.destroy()
