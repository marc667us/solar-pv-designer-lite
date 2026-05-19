# auth/dashboard_window.py
# Role-based dashboard (user & admin) shown after login.

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from auth.user_store import (get_all_users, delete_user, change_role,
                              update_password, authenticate, _hash)

# ── Palette ───────────────────────────────────────────────────────────────────
BG       = "#1e1e2e"
PANEL    = "#2a2a3e"
CARD     = "#12121f"
ACCENT   = "#f5a623"
ACCENT2  = "#4fc3f7"
TEXT     = "#e0e0e0"
TEXT_DIM = "#888888"
SUCCESS  = "#66bb6a"
ERROR    = "#ef5350"
BORDER   = "#3a3a5c"
WARN     = "#ffd54f"

FONT_T   = ("Segoe UI", 15, "bold")
FONT_H   = ("Segoe UI", 11, "bold")
FONT_LBL = ("Segoe UI", 10)
FONT_SM  = ("Segoe UI", 8, "bold")
FONT_DIM = ("Segoe UI", 8)


class DashboardWindow(tk.Toplevel):
    """Main dashboard — user or admin view, determined by user['role']."""

    def __init__(self, master, user: dict, on_launch_designer=None, on_logout=None):
        super().__init__(master)
        self.user               = user
        self._on_launch_cb      = on_launch_designer
        self._on_logout_cb      = on_logout
        self.do_logout          = False   # flag read by caller after window closes

        is_admin = (user.get("role") == "admin")
        w, h = (1100, 740) if is_admin else (860, 600)

        self.title(f"Solar PV Designer Lite — Dashboard  ({user['username']})")
        self.geometry(f"{w}x{h}")
        self.minsize(w, h)
        self.configure(bg=BG)
        self.resizable(True, True)

        # Center on screen
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build()

    # ── Top-level build ───────────────────────────────────────────────────────
    def _build(self):
        self._build_header()

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=16, pady=12)

        if self.user.get("role") == "admin":
            self._build_admin_body(body)
        else:
            self._build_user_body(body)

        self._build_footer()

    # ── Header ────────────────────────────────────────────────────────────────
    def _build_header(self):
        hdr = tk.Frame(self, bg=ACCENT, height=56)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        tk.Label(hdr, text="☀  Solar PV Designer Lite",
                 font=("Segoe UI", 14, "bold"),
                 bg=ACCENT, fg="#1e1e2e").pack(side="left", padx=20, pady=10)

        # Role badge
        role = self.user.get("role", "user")
        badge_bg = "#b71c1c" if role == "admin" else "#1565c0"
        badge_fg = "#ffffff"
        tk.Label(hdr, text=f"  {role.upper()}  ",
                 font=("Segoe UI", 8, "bold"),
                 bg=badge_bg, fg=badge_fg,
                 padx=6, pady=2).pack(side="right", padx=6, pady=14)

        name = self.user.get("full_name", self.user["username"])
        tk.Label(hdr, text=f"👤  {name}",
                 font=("Segoe UI", 10),
                 bg=ACCENT, fg="#4a3000").pack(side="right", padx=4, pady=14)

    # ── Footer ────────────────────────────────────────────────────────────────
    def _build_footer(self):
        ftr = tk.Frame(self, bg=PANEL, height=32)
        ftr.pack(fill="x", side="bottom")
        ftr.pack_propagate(False)
        tk.Label(ftr, text="Solar PV Designer Lite  |  Ghana",
                 font=FONT_DIM, bg=PANEL, fg=TEXT_DIM).pack(side="left", padx=16)
        tk.Label(ftr, text="BS 7671:2018  |  415/230V 50Hz",
                 font=FONT_DIM, bg=PANEL, fg=TEXT_DIM).pack(side="right", padx=16)

    # ══════════════════════════════════════════════════════════════════════════
    # USER DASHBOARD
    # ══════════════════════════════════════════════════════════════════════════
    def _build_user_body(self, parent):
        # ── Welcome banner ──
        self._welcome_banner(parent)
        # ── Stats row ──
        self._stats_row(parent)
        # ── Actions ──
        self._action_buttons(parent)
        # ── Activity ──
        self._activity_section(parent)

    def _welcome_banner(self, parent):
        banner = tk.Frame(parent, bg=PANEL, padx=20, pady=16,
                          highlightbackground=BORDER, highlightthickness=1)
        banner.pack(fill="x", pady=(0, 12))

        left = tk.Frame(banner, bg=PANEL)
        left.pack(side="left")

        name = self.user.get("full_name", self.user["username"])
        tk.Label(left, text=f"Welcome back,",
                 font=("Segoe UI", 10), bg=PANEL, fg=TEXT_DIM).pack(anchor="w")
        tk.Label(left, text=name,
                 font=("Segoe UI", 22, "bold"), bg=PANEL, fg=ACCENT).pack(anchor="w")
        tk.Label(left,
                 text=f"@{self.user['username']}  ·  {self.user.get('email', '—')}",
                 font=FONT_DIM, bg=PANEL, fg=TEXT_DIM).pack(anchor="w", pady=(2, 0))

        # Solar icon right
        tk.Label(banner, text="☀",
                 font=("Segoe UI", 48), bg=PANEL, fg=ACCENT).pack(side="right", padx=20)

    def _stats_row(self, parent):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(0, 12))

        stats = [
            ("Designs Run",   str(self.user.get("designs_run", 0)),      ACCENT2,  "total PV designs generated"),
            ("Member Since",  self.user.get("created_at",  "—"),          WARN,     "account creation date"),
            ("Last Login",    self.user.get("last_login",  "First login"), SUCCESS,  "most recent login timestamp"),
            ("Account Type",  self.user.get("role", "user").title(),      TEXT,     "your access level"),
        ]
        for i, (label, value, color, hint) in enumerate(stats):
            card = tk.Frame(row, bg=PANEL, padx=14, pady=12,
                            highlightbackground=BORDER, highlightthickness=1)
            card.pack(side="left", expand=True, fill="both", padx=(0 if i == 0 else 8, 0))
            tk.Label(card, text=label, font=FONT_SM,
                     bg=PANEL, fg=TEXT_DIM).pack(anchor="w")
            tk.Label(card, text=value, font=("Segoe UI", 16, "bold"),
                     bg=PANEL, fg=color).pack(anchor="w")
            tk.Label(card, text=hint, font=FONT_DIM,
                     bg=PANEL, fg=TEXT_DIM).pack(anchor="w")

    def _action_buttons(self, parent):
        section_lbl(parent, "Quick Actions")

        btn_row = tk.Frame(parent, bg=BG)
        btn_row.pack(fill="x", pady=(0, 6))

        # Primary: Launch Designer
        launch_btn = tk.Button(
            btn_row,
            text="🚀   Launch Solar PV Designer",
            font=("Segoe UI", 13, "bold"),
            bg=ACCENT, fg="#1e1e2e",
            activebackground="#d4911a", activeforeground="#1e1e2e",
            relief="flat", cursor="hand2", padx=20, pady=14,
            command=self._launch_designer,
        )
        launch_btn.pack(side="left", expand=True, fill="both", padx=(0, 8))

        right_col = tk.Frame(btn_row, bg=BG)
        right_col.pack(side="left", fill="both")

        tk.Button(
            right_col,
            text="🔑  Change Password",
            font=FONT_LBL,
            bg=PANEL, fg=ACCENT2,
            activebackground=BORDER,
            relief="flat", cursor="hand2", padx=14, pady=10,
            command=self._change_password,
        ).pack(fill="x", pady=(0, 6))

        tk.Button(
            right_col,
            text="🚪  Logout",
            font=FONT_LBL,
            bg=PANEL, fg=ERROR,
            activebackground=BORDER,
            relief="flat", cursor="hand2", padx=14, pady=10,
            command=self._logout,
        ).pack(fill="x")

        # Chatbot button — full width below the two-column row
        tk.Button(
            parent,
            text="🤖   PV Solar AI Chatbot",
            font=("Segoe UI", 11, "bold"),
            bg="#1a2a3a", fg=ACCENT2,
            activebackground="#0d1a2a", activeforeground=ACCENT2,
            relief="flat", cursor="hand2", padx=20, pady=12,
            command=self._open_chatbot,
        ).pack(fill="x", pady=(6, 12))

    def _activity_section(self, parent):
        section_lbl(parent, "Activity Overview")

        act = tk.Frame(parent, bg=PANEL, padx=16, pady=14,
                       highlightbackground=BORDER, highlightthickness=1)
        act.pack(fill="x")

        designs = self.user.get("designs_run", 0)
        last    = self.user.get("last_login", "—")
        since   = self.user.get("created_at",  "—")

        rows = [
            ("Solar PV designs generated", str(designs)),
            ("Account created",            since),
            ("Last active",               last or "This is your first login"),
            ("Email",                     self.user.get("email") or "Not provided"),
        ]
        for label, val in rows:
            r = tk.Frame(act, bg=PANEL)
            r.pack(fill="x", pady=2)
            tk.Label(r, text=label, font=FONT_LBL,
                     bg=PANEL, fg=TEXT_DIM, width=28, anchor="w").pack(side="left")
            tk.Label(r, text=val, font=("Segoe UI", 10, "bold"),
                     bg=PANEL, fg=TEXT).pack(side="left")

    # ══════════════════════════════════════════════════════════════════════════
    # ADMIN DASHBOARD
    # ══════════════════════════════════════════════════════════════════════════
    def _build_admin_body(self, parent):
        # Left: welcome + stats + quick actions (same as user)
        # Right: user management table

        cols = tk.Frame(parent, bg=BG)
        cols.pack(fill="both", expand=True)
        cols.columnconfigure(0, weight=1)
        cols.columnconfigure(1, weight=2)
        cols.rowconfigure(0, weight=1)

        left = tk.Frame(cols, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        right = tk.Frame(cols, bg=BG)
        right.grid(row=0, column=1, sticky="nsew")

        # Left column
        self._welcome_banner(left)
        self._stats_row_admin(left)
        self._action_buttons(left)

        # Right column — user management
        self._user_management_panel(right)

    def _stats_row_admin(self, parent):
        """Admin summary chips."""
        all_users = get_all_users()
        total      = len(all_users)
        admins     = sum(1 for u in all_users if u["role"] == "admin")
        users_only = total - admins
        total_runs = sum(u.get("designs_run", 0) for u in all_users)

        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(0, 12))
        stats = [
            ("Total Users",    str(total),      ACCENT2),
            ("Designers",      str(users_only), SUCCESS),
            ("Admins",         str(admins),     ERROR),
            ("Total Designs",  str(total_runs), ACCENT),
        ]
        for i, (label, value, color) in enumerate(stats):
            card = tk.Frame(row, bg=PANEL, padx=10, pady=10,
                            highlightbackground=BORDER, highlightthickness=1)
            card.pack(side="left", expand=True, fill="both",
                      padx=(0 if i == 0 else 6, 0))
            tk.Label(card, text=label, font=FONT_SM,
                     bg=PANEL, fg=TEXT_DIM).pack(anchor="w")
            tk.Label(card, text=value, font=("Segoe UI", 18, "bold"),
                     bg=PANEL, fg=color).pack(anchor="w")

    def _user_management_panel(self, parent):
        section_lbl(parent, "User Management")

        # Toolbar
        toolbar = tk.Frame(parent, bg=BG)
        toolbar.pack(fill="x", pady=(0, 6))

        tk.Button(toolbar, text="⟳  Refresh",
                  font=FONT_DIM, bg=PANEL, fg=ACCENT2,
                  activebackground=BORDER, relief="flat",
                  cursor="hand2", padx=10, pady=4,
                  command=self._refresh_table).pack(side="left")

        tk.Button(toolbar, text="🗑  Delete Selected",
                  font=FONT_DIM, bg=PANEL, fg=ERROR,
                  activebackground=BORDER, relief="flat",
                  cursor="hand2", padx=10, pady=4,
                  command=self._delete_selected).pack(side="left", padx=(6, 0))

        tk.Button(toolbar, text="🔑  Reset Password",
                  font=FONT_DIM, bg=PANEL, fg=WARN,
                  activebackground=BORDER, relief="flat",
                  cursor="hand2", padx=10, pady=4,
                  command=self._reset_password).pack(side="left", padx=(6, 0))

        tk.Button(toolbar, text="⬆  Promote to Admin",
                  font=FONT_DIM, bg=PANEL, fg=ACCENT,
                  activebackground=BORDER, relief="flat",
                  cursor="hand2", padx=10, pady=4,
                  command=lambda: self._set_role("admin")).pack(side="left", padx=(6, 0))

        tk.Button(toolbar, text="⬇  Demote to User",
                  font=FONT_DIM, bg=PANEL, fg=TEXT_DIM,
                  activebackground=BORDER, relief="flat",
                  cursor="hand2", padx=10, pady=4,
                  command=lambda: self._set_role("user")).pack(side="left", padx=(6, 0))

        # Treeview
        tree_frame = tk.Frame(parent, bg=BG)
        tree_frame.pack(fill="both", expand=True)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("User.Treeview",
                         background=CARD, foreground=TEXT,
                         fieldbackground=CARD,
                         rowheight=26, font=("Segoe UI", 9))
        style.configure("User.Treeview.Heading",
                         background=PANEL, foreground=ACCENT2,
                         font=("Segoe UI", 9, "bold"),
                         relief="flat")
        style.map("User.Treeview",
                  background=[("selected", "#2e3a6e")],
                  foreground=[("selected", TEXT)])

        cols = ("Username", "Full Name", "Role", "Email", "Designs", "Created", "Last Login")
        self._tree = ttk.Treeview(tree_frame, columns=cols,
                                   show="headings", style="User.Treeview",
                                   selectmode="browse")

        col_widths = [110, 140, 70, 170, 70, 100, 135]
        for c, w in zip(cols, col_widths):
            self._tree.heading(c, text=c, anchor="w")
            self._tree.column(c,  width=w, anchor="w", minwidth=60)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical",
                             command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._populate_table()

    def _populate_table(self):
        for row in self._tree.get_children():
            self._tree.delete(row)
        for u in get_all_users():
            tag = "admin_row" if u["role"] == "admin" else ""
            self._tree.insert("", "end", values=(
                u["username"],
                u.get("full_name", "—"),
                u.get("role", "user"),
                u.get("email", "—") or "—",
                u.get("designs_run", 0),
                u.get("created_at", "—"),
                u.get("last_login", "—") or "Never",
            ), tags=(tag,))
        self._tree.tag_configure("admin_row", foreground=WARN)

    def _refresh_table(self):
        self._populate_table()

    def _selected_username(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("No Selection", "Please select a user first.")
            return None
        return self._tree.item(sel[0], "values")[0]

    def _delete_selected(self):
        uname = self._selected_username()
        if not uname:
            return
        if uname == self.user["username"]:
            messagebox.showerror("Error", "You cannot delete your own account.")
            return
        if messagebox.askyesno("Confirm Delete",
                                f"Delete user '{uname}'?\nThis cannot be undone."):
            ok, msg = delete_user(uname)
            if ok:
                self._populate_table()
                messagebox.showinfo("Deleted", msg)
            else:
                messagebox.showerror("Error", msg)

    def _reset_password(self):
        uname = self._selected_username()
        if not uname:
            return
        new_pw = simpledialog.askstring(
            "Reset Password",
            f"Enter new password for '{uname}' (min 6 chars):",
            parent=self, show="•")
        if not new_pw:
            return
        ok, msg = update_password(uname, new_pw)
        if ok:
            messagebox.showinfo("Done", f"Password for '{uname}' has been reset.")
        else:
            messagebox.showerror("Error", msg)

    def _set_role(self, new_role):
        uname = self._selected_username()
        if not uname:
            return
        if uname == self.user["username"] and new_role != "admin":
            messagebox.showerror("Error", "You cannot demote your own account.")
            return
        change_role(uname, new_role)
        self._populate_table()
        messagebox.showinfo("Done", f"'{uname}' is now '{new_role}'.")

    # ── Common actions ────────────────────────────────────────────────────────
    def _launch_designer(self):
        if self._on_launch_cb:
            self._on_launch_cb()

    def _open_chatbot(self):
        from auth.chatbot_window import ChatbotWindow
        ChatbotWindow(self, current_user=self.user)

    def _change_password(self):
        dlg = _ChangePasswordDialog(self, self.user["username"])
        self.wait_window(dlg)

    def _logout(self):
        self.do_logout = True
        self.destroy()

    def _on_close(self):
        self.do_logout = False
        self.destroy()


# ── Change-password dialog ────────────────────────────────────────────────────
class _ChangePasswordDialog(tk.Toplevel):
    def __init__(self, master, username):
        super().__init__(master)
        self._username = username
        self.title("Change Password")
        self.geometry("380x320")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.grab_set()

        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"380x320+{(sw-380)//2}+{(sh-320)//2}")

        tk.Label(self, text="Change Password",
                 font=("Segoe UI", 13, "bold"),
                 bg=BG, fg=ACCENT).pack(pady=(18, 6))
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", padx=20)

        card = tk.Frame(self, bg=PANEL, padx=24, pady=18)
        card.pack(padx=20, pady=14, fill="both")

        def field(label, show=""):
            tk.Label(card, text=label, font=FONT_SM,
                     bg=PANEL, fg=TEXT_DIM).pack(anchor="w", pady=(8, 2))
            var = tk.StringVar()
            tk.Entry(card, textvariable=var, font=("Segoe UI", 11),
                     bg=CARD, fg=TEXT, insertbackground=ACCENT2,
                     relief="flat", show=show).pack(fill="x", ipady=6)
            return var

        self._old  = field("CURRENT PASSWORD", "•")
        self._new  = field("NEW PASSWORD (min 6 chars)", "•")
        self._new2 = field("CONFIRM NEW PASSWORD", "•")

        self._err = tk.StringVar()
        tk.Label(card, textvariable=self._err,
                 font=("Segoe UI", 8), bg=PANEL, fg=ERROR).pack(anchor="w", pady=(4, 0))

        tk.Button(self, text="Update Password",
                  font=FONT_LBL,
                  bg=SUCCESS, fg="#0d200d",
                  relief="flat", cursor="hand2", pady=8,
                  command=self._submit).pack(fill="x", padx=20, pady=(0, 10))

    def _submit(self):
        self._err.set("")
        old  = self._old.get()
        new  = self._new.get()
        new2 = self._new2.get()

        if not authenticate(self._username, old):
            self._err.set("Current password is incorrect.")
            return
        if new != new2:
            self._err.set("New passwords do not match.")
            return
        ok, msg = update_password(self._username, new)
        if ok:
            messagebox.showinfo("Done", "Password updated successfully.")
            self.destroy()
        else:
            self._err.set(msg)


# ── Shared helper ─────────────────────────────────────────────────────────────
def section_lbl(parent, title):
    tk.Label(parent, text=title.upper(),
             font=FONT_SM, bg=BG, fg=ACCENT2).pack(anchor="w", pady=(10, 4))
    tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", pady=(0, 8))
