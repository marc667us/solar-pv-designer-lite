"""Restructure the BOQ "WIRING OF POINTS" section catalog into four
subsections per owner spec 2026-06-30:

  A. Lighting Points          (1.5mm2, wires: Live + Neutral + Control)
  B. Socket Outlet Points     (2.5mm2, wires: Live + Neutral + Earth)
  C. Air Conditioner Points   (4.0mm2, wires: Live + Neutral + Earth)
  D. Water Heater Points      (4.0mm2, wires: Live + Neutral + Earth)

Each subsection lists items in order Boxes -> Conduit Points -> Wires.
Colour codes embedded in item names (Brown = Live, Blue = Neutral,
Yellow/Green = Earth, Grey = Control).

Patches two catalogs:
  * basic catalog at ~line 22187 ("WIRING OF POINTS": [...] short form)
  * v3 catalog at ~line 23160 ("Supply and install ..." spec form)

Existing prices preserved.  Legacy "general" items (32mm conduit, 6.0mm2
wires, etc.) kept at the tail of each catalog so any existing BOQ row
keyed against the old names still resolves.

Re-runnable: each replace checks for the post-patch shape and skips.
ASCII only -- uses "mm2" not Unicode squared sign to match existing file
encoding (file has mojibake; sticking to ASCII avoids any drift).
"""
from __future__ import annotations
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent / "web_app.py"
data = WEB.read_bytes()
CRLF = b"\r\n"

def crlf(s: bytes) -> bytes:
    return s.replace(b"\r\n", b"\n").replace(b"\n", CRLF)

def replace_once(d: bytes, old: bytes, new: bytes, label: str) -> bytes:
    old_c, new_c = crlf(old), crlf(new)
    if new_c in d:
        print(f"  {label}: already patched, skipping")
        return d
    n = d.count(old_c)
    if n != 1:
        sys.exit(f"  {label}: expected exactly 1 match of OLD anchor, found {n}")
    print(f"  {label}: patched")
    return d.replace(old_c, new_c, 1)


# ---------- BASIC catalog (~ line 22187) ----------
BASIC_OLD = b'''    "WIRING OF POINTS": [
        # --- Pipes / conduits (priced per metre or per piece) ---
        ("20mm PVC rigid conduit pipe (3m length, priced per metre)", "M",    5),
        ("20mm flexible PVC tube (rolls, priced per metre)",  "M",    6),
        ("20mm diameter PVC conduit pipe",                    "Nos.",   14.63),
        ("25mm diameter PVC conduit pipe",                    "Nos.",   19.50),
        ("32mm diameter PVC conduit pipe",                    "Nos.",   28.00),
        # --- Boxes ---
        ("3x3 steel square box",                              "No.",    13),
        ("3x6 steel square box",                              "No.",    18),
        ("75mm x 75mm steel conduit boxes",                   "Nos.",   13),
        ("150mm x 75mm steel conduit boxes",                  "Nos.",   18),
        ("Circular boxes of various ways",                    "Nos.",    5),
        ("Junction boxes",                                    "Nos.",    8),
        # --- Wires / cables ---
        ("1.5mm2 PVC insulated copper cable (Brown)",         "Coils", 391),
        ("1.5mm2 PVC insulated copper cable (Blue)",          "Coils", 391),
        ("1.5mm2 PVC insulated copper cable (Grey)",          "Coils", 391),
        ("1.5mm2 PVC insulated copper cable (Yellow/Green)",  "Coils", 391),
        ("2.5mm2 PVC insulated copper cable (Brown)",         "Coils", 653),
        ("2.5mm2 PVC insulated copper cable (Blue)",          "Coils", 653),
        ("2.5mm2 PVC insulated copper cable (Yellow/Green)",  "Coils", 653),
        ("4.0mm2 PVC insulated copper cable (Brown)",         "Coils", 1037),
        ("4.0mm2 PVC insulated copper cable (Blue)",          "Coils", 1037),
        ("4.0mm2 PVC insulated copper cable (Yellow/Green)",  "Coils", 1037),
        ("6.0mm2 PVC insulated copper cable (Brown)",         "Coils", 1500),
        ("6.0mm2 PVC insulated copper cable (Blue)",          "Coils", 1500),
        ("6.0mm2 PVC insulated copper cable (Yellow/Green)",  "Coils", 1500),
    ],'''

BASIC_NEW = b'''    "WIRING OF POINTS": [
        # ===== A. LIGHTING POINTS (1.5mm2) =====
        # Boxes
        ("Lighting Point - 3x3 steel square box",                                   "Nos.",   13),
        # Conduit point
        ("Lighting Point - 20mm PVC conduit pipe",                                  "M",       5),
        # Wires (Live + Neutral + Control)
        ("Lighting Point - 1.5mm2 PVC copper cable, Live (Brown)",                  "Coils", 391),
        ("Lighting Point - 1.5mm2 PVC copper cable, Neutral (Blue)",                "Coils", 391),
        ("Lighting Point - 1.5mm2 PVC copper cable, Control (Grey)",                "Coils", 391),

        # ===== B. SOCKET OUTLET POINTS (2.5mm2) =====
        # Boxes
        ("Socket Outlet Point - 3x6 steel square box",                              "Nos.",   18),
        # Conduit point
        ("Socket Outlet Point - 20mm PVC conduit pipe",                             "M",       5),
        # Wires (Live + Neutral + Earth)
        ("Socket Outlet Point - 2.5mm2 PVC copper cable, Live (Brown)",             "Coils", 653),
        ("Socket Outlet Point - 2.5mm2 PVC copper cable, Neutral (Blue)",           "Coils", 653),
        ("Socket Outlet Point - 2.5mm2 PVC copper cable, Earth (Yellow/Green)",     "Coils", 653),

        # ===== C. AIR CONDITIONER POINTS (4.0mm2) =====
        # Boxes
        ("Air Conditioner Point - 3x6 steel square box",                            "Nos.",   18),
        # Conduit point
        ("Air Conditioner Point - 25mm PVC conduit pipe",                           "Nos.",   19.50),
        # Wires (Live + Neutral + Earth)
        ("Air Conditioner Point - 4.0mm2 PVC copper cable, Live (Brown)",           "Coils", 1037),
        ("Air Conditioner Point - 4.0mm2 PVC copper cable, Neutral (Blue)",         "Coils", 1037),
        ("Air Conditioner Point - 4.0mm2 PVC copper cable, Earth (Yellow/Green)",   "Coils", 1037),

        # ===== D. WATER HEATER POINTS (4.0mm2) =====
        # Boxes
        ("Water Heater Point - 3x6 steel square box",                               "Nos.",   18),
        # Conduit point
        ("Water Heater Point - 25mm PVC conduit pipe",                              "Nos.",   19.50),
        # Wires (Live + Neutral + Earth)
        ("Water Heater Point - 4.0mm2 PVC copper cable, Live (Brown)",              "Coils", 1037),
        ("Water Heater Point - 4.0mm2 PVC copper cable, Neutral (Blue)",            "Coils", 1037),
        ("Water Heater Point - 4.0mm2 PVC copper cable, Earth (Yellow/Green)",      "Coils", 1037),

        # ===== LEGACY / GENERAL ITEMS (preserved for back-compat with existing BOQ rows) =====
        ("20mm PVC rigid conduit pipe (3m length, priced per metre)", "M",    5),
        ("20mm flexible PVC tube (rolls, priced per metre)",  "M",    6),
        ("20mm diameter PVC conduit pipe",                    "Nos.",   14.63),
        ("25mm diameter PVC conduit pipe",                    "Nos.",   19.50),
        ("32mm diameter PVC conduit pipe",                    "Nos.",   28.00),
        ("3x3 steel square box",                              "No.",    13),
        ("3x6 steel square box",                              "No.",    18),
        ("75mm x 75mm steel conduit boxes",                   "Nos.",   13),
        ("150mm x 75mm steel conduit boxes",                  "Nos.",   18),
        ("Circular boxes of various ways",                    "Nos.",    5),
        ("Junction boxes",                                    "Nos.",    8),
        ("1.5mm2 PVC insulated copper cable (Brown)",         "Coils", 391),
        ("1.5mm2 PVC insulated copper cable (Blue)",          "Coils", 391),
        ("1.5mm2 PVC insulated copper cable (Grey)",          "Coils", 391),
        ("1.5mm2 PVC insulated copper cable (Yellow/Green)",  "Coils", 391),
        ("2.5mm2 PVC insulated copper cable (Brown)",         "Coils", 653),
        ("2.5mm2 PVC insulated copper cable (Blue)",          "Coils", 653),
        ("2.5mm2 PVC insulated copper cable (Yellow/Green)",  "Coils", 653),
        ("4.0mm2 PVC insulated copper cable (Brown)",         "Coils", 1037),
        ("4.0mm2 PVC insulated copper cable (Blue)",          "Coils", 1037),
        ("4.0mm2 PVC insulated copper cable (Yellow/Green)",  "Coils", 1037),
        ("6.0mm2 PVC insulated copper cable (Brown)",         "Coils", 1500),
        ("6.0mm2 PVC insulated copper cable (Blue)",          "Coils", 1500),
        ("6.0mm2 PVC insulated copper cable (Yellow/Green)",  "Coils", 1500),
    ],'''

data = replace_once(data, BASIC_OLD, BASIC_NEW, "basic catalog WIRING OF POINTS")


# ---------- V3 catalog (~ line 23160) -- spec-formatted ----------
V3_OLD = b'''    "WIRING OF POINTS": [
        # --- Pipes / conduits (priced per metre or per piece) ---
        ("Supply and install 20mm PVC rigid conduit pipe (3m length, priced per metre)",                           "M",    5),
        ("Supply and install 20mm flexible PVC tube (rolls, priced per metre)",                                     "M",    6),
        ("Supply and install 20mm diameter PVC conduit pipe",                                                       "Nos.",   14.63),
        ("Supply and install 25mm diameter PVC conduit pipe",                                                       "Nos.",   19.50),
        ("Supply and install 32mm diameter PVC conduit pipe",                                                       "Nos.",   28.00),
        # --- Boxes ---
        ("Supply and install 3x3 steel square box",                                                                 "No.",    13),
        ("Supply and install 3x6 steel square box",                                                                 "No.",    18),
        ("Supply and install 75mm x 75mm steel conduit boxes",                                                      "Nos.",   13),
        ("Supply and install 150mm x 75mm steel conduit boxes",                                                     "Nos.",   18),
        ("Supply and install circular boxes of various ways",                                                       "Nos.",    5),
        ("Supply and install junction boxes",                                                                       "Nos.",    8),
        # --- Wires / cables ---
        ("Wire the following point in conduit / trunking using 1.5mm2 PVC insulated copper cable (Brown)",         "Coils", 391),
        ("Wire the following point in conduit / trunking using 1.5mm2 PVC insulated copper cable (Blue)",          "Coils", 391),
        ("Wire the following point in conduit / trunking using 1.5mm2 PVC insulated copper cable (Grey)",          "Coils", 391),
        ("Wire the following point in conduit / trunking using 1.5mm2 PVC insulated copper cable (Yellow/Green)",  "Coils", 391),
        ("Wire the following point in conduit / trunking using 2.5mm2 PVC insulated copper cable (Brown)",         "Coils", 653),
        ("Wire the following point in conduit / trunking using 2.5mm2 PVC insulated copper cable (Blue)",          "Coils", 653),
        ("Wire the following point in conduit / trunking using 2.5mm2 PVC insulated copper cable (Yellow/Green)",  "Coils", 653),
        ("Wire the following point in conduit / trunking using 4.0mm2 PVC insulated copper cable (Brown)",         "Coils", 1037),
        ("Wire the following point in conduit / trunking using 4.0mm2 PVC insulated copper cable (Blue)",          "Coils", 1037),
        ("Wire the following point in conduit / trunking using 4.0mm2 PVC insulated copper cable (Yellow/Green)",  "Coils", 1037),
        ("Wire the following point in conduit / trunking using 6.0mm2 PVC insulated copper cable (Brown)",         "Coils", 1500),
        ("Wire the following point in conduit / trunking using 6.0mm2 PVC insulated copper cable (Blue)",          "Coils", 1500),
        ("Wire the following point in conduit / trunking using 6.0mm2 PVC insulated copper cable (Yellow/Green)",  "Coils", 1500),
    ],'''

V3_NEW = b'''    "WIRING OF POINTS": [
        # ===== A. LIGHTING POINTS (1.5mm2) =====
        # Boxes
        ("Supply and install Lighting Point - 3x3 steel square box",                                                "Nos.",   13),
        # Conduit point
        ("Supply and install Lighting Point - 20mm PVC conduit pipe",                                               "M",       5),
        # Wires (Live + Neutral + Control)
        ("Wire Lighting Point in conduit using 1.5mm2 PVC insulated copper cable, Live (Brown)",                    "Coils", 391),
        ("Wire Lighting Point in conduit using 1.5mm2 PVC insulated copper cable, Neutral (Blue)",                  "Coils", 391),
        ("Wire Lighting Point in conduit using 1.5mm2 PVC insulated copper cable, Control (Grey)",                  "Coils", 391),

        # ===== B. SOCKET OUTLET POINTS (2.5mm2) =====
        # Boxes
        ("Supply and install Socket Outlet Point - 3x6 steel square box",                                           "Nos.",   18),
        # Conduit point
        ("Supply and install Socket Outlet Point - 20mm PVC conduit pipe",                                          "M",       5),
        # Wires (Live + Neutral + Earth)
        ("Wire Socket Outlet Point in conduit using 2.5mm2 PVC insulated copper cable, Live (Brown)",               "Coils", 653),
        ("Wire Socket Outlet Point in conduit using 2.5mm2 PVC insulated copper cable, Neutral (Blue)",             "Coils", 653),
        ("Wire Socket Outlet Point in conduit using 2.5mm2 PVC insulated copper cable, Earth (Yellow/Green)",       "Coils", 653),

        # ===== C. AIR CONDITIONER POINTS (4.0mm2) =====
        # Boxes
        ("Supply and install Air Conditioner Point - 3x6 steel square box",                                         "Nos.",   18),
        # Conduit point
        ("Supply and install Air Conditioner Point - 25mm PVC conduit pipe",                                        "Nos.",   19.50),
        # Wires (Live + Neutral + Earth)
        ("Wire Air Conditioner Point in conduit using 4.0mm2 PVC insulated copper cable, Live (Brown)",             "Coils", 1037),
        ("Wire Air Conditioner Point in conduit using 4.0mm2 PVC insulated copper cable, Neutral (Blue)",           "Coils", 1037),
        ("Wire Air Conditioner Point in conduit using 4.0mm2 PVC insulated copper cable, Earth (Yellow/Green)",     "Coils", 1037),

        # ===== D. WATER HEATER POINTS (4.0mm2) =====
        # Boxes
        ("Supply and install Water Heater Point - 3x6 steel square box",                                            "Nos.",   18),
        # Conduit point
        ("Supply and install Water Heater Point - 25mm PVC conduit pipe",                                           "Nos.",   19.50),
        # Wires (Live + Neutral + Earth)
        ("Wire Water Heater Point in conduit using 4.0mm2 PVC insulated copper cable, Live (Brown)",                "Coils", 1037),
        ("Wire Water Heater Point in conduit using 4.0mm2 PVC insulated copper cable, Neutral (Blue)",              "Coils", 1037),
        ("Wire Water Heater Point in conduit using 4.0mm2 PVC insulated copper cable, Earth (Yellow/Green)",        "Coils", 1037),

        # ===== LEGACY / GENERAL ITEMS (preserved for back-compat with existing BOQ rows) =====
        ("Supply and install 20mm PVC rigid conduit pipe (3m length, priced per metre)",                           "M",    5),
        ("Supply and install 20mm flexible PVC tube (rolls, priced per metre)",                                     "M",    6),
        ("Supply and install 20mm diameter PVC conduit pipe",                                                       "Nos.",   14.63),
        ("Supply and install 25mm diameter PVC conduit pipe",                                                       "Nos.",   19.50),
        ("Supply and install 32mm diameter PVC conduit pipe",                                                       "Nos.",   28.00),
        ("Supply and install 3x3 steel square box",                                                                 "No.",    13),
        ("Supply and install 3x6 steel square box",                                                                 "No.",    18),
        ("Supply and install 75mm x 75mm steel conduit boxes",                                                      "Nos.",   13),
        ("Supply and install 150mm x 75mm steel conduit boxes",                                                     "Nos.",   18),
        ("Supply and install circular boxes of various ways",                                                       "Nos.",    5),
        ("Supply and install junction boxes",                                                                       "Nos.",    8),
        ("Wire the following point in conduit / trunking using 1.5mm2 PVC insulated copper cable (Brown)",         "Coils", 391),
        ("Wire the following point in conduit / trunking using 1.5mm2 PVC insulated copper cable (Blue)",          "Coils", 391),
        ("Wire the following point in conduit / trunking using 1.5mm2 PVC insulated copper cable (Grey)",          "Coils", 391),
        ("Wire the following point in conduit / trunking using 1.5mm2 PVC insulated copper cable (Yellow/Green)",  "Coils", 391),
        ("Wire the following point in conduit / trunking using 2.5mm2 PVC insulated copper cable (Brown)",         "Coils", 653),
        ("Wire the following point in conduit / trunking using 2.5mm2 PVC insulated copper cable (Blue)",          "Coils", 653),
        ("Wire the following point in conduit / trunking using 2.5mm2 PVC insulated copper cable (Yellow/Green)",  "Coils", 653),
        ("Wire the following point in conduit / trunking using 4.0mm2 PVC insulated copper cable (Brown)",         "Coils", 1037),
        ("Wire the following point in conduit / trunking using 4.0mm2 PVC insulated copper cable (Blue)",          "Coils", 1037),
        ("Wire the following point in conduit / trunking using 4.0mm2 PVC insulated copper cable (Yellow/Green)",  "Coils", 1037),
        ("Wire the following point in conduit / trunking using 6.0mm2 PVC insulated copper cable (Brown)",         "Coils", 1500),
        ("Wire the following point in conduit / trunking using 6.0mm2 PVC insulated copper cable (Blue)",          "Coils", 1500),
        ("Wire the following point in conduit / trunking using 6.0mm2 PVC insulated copper cable (Yellow/Green)",  "Coils", 1500),
    ],'''

data = replace_once(data, V3_OLD, V3_NEW, "v3 catalog WIRING OF POINTS")

WEB.write_bytes(data)
print("done.")
