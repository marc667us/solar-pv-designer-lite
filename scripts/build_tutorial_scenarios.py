"""Generate the Tutorial & Demo Engine's scenario definitions.

Every SolarPro page registers its tutorial as a JSON definition keyed by the
Flask endpoint name; the engine (static/tutorial/tutorial-engine.js) loads
/static/tutorial/scenarios/<endpoint>.json and plays it. Pages never hard-code a
tutorial (spec: pvsolar1/"video tutorial.txt").

Adding a tutorial for a new page = add one entry to SCENARIOS below and re-run:

    python scripts/build_tutorial_scenarios.py

Every step degrades safely: if `target` is not on the page the engine shows
`fallback` and moves on. Clicks are simulated (cursor + ripple) and only
dispatched against the real DOM when a step sets dispatch=True -- never for
destructive controls, and never at all in read-only "watch" mode.

in : SCENARIOS (below)
out: static/tutorial/scenarios/<endpoint>.json  +  index.json (coverage manifest)
"""
from __future__ import annotations

import json
import os

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "static", "tutorial", "scenarios")


def step(title, desc, voice, *, target="", action="highlightOnly",
         type_text="", dispatch=False, duration=700, fallback=""):
    """One scenario step. out: dict matching the engine's step contract."""
    s = {
        "title": title,
        "description": desc,
        "voiceScript": voice,
        "captionText": voice,
        "targetSelector": target,
        "action": action,
        "duration": duration,
        "delayBefore": 120,
        "fallbackMessage": fallback or f"{title}: not visible on this page yet.",
    }
    if type_text:
        s["typeText"] = type_text
    if dispatch:
        s["dispatch"] = True
    return s


# endpoint -> (title, module, description, [steps])
SCENARIOS: dict[str, tuple] = {
    "dashboard": (
        "Dashboard", "Dashboard",
        "Your projects, quick actions and platform status in one place.",
        [
            step("Your projects", "Every design you create is listed here with its status.",
                 "This is your dashboard. Every solar design you create appears here.",
                 target=".solar-card"),
            step("Create a design", "Start a new residential, commercial or industrial PV design.",
                 "To begin a new design, use Create Standard Project in the top navigation.",
                 target='a[href="/project/new"], a[href*="new"]', action="moveCursor"),
            step("Generation Station", "Utility-scale plants use the 14-step Generation Station wizard.",
                 "For utility-scale plants, open Generation Station Design.",
                 target='a[href="/large-scale-solar"]', action="moveCursor"),
            step("Marketplace", "Priced equipment feeds your BOQ and procurement lists.",
                 "The Marketplace supplies live equipment prices to your bills of quantities.",
                 target='a[href*="/marketplace"]', action="moveCursor"),
        ],
    ),
    "marketplace_public": (
        "Marketplace", "Marketplace",
        "Browse priced equipment by category, filter by country compliance, and push items into a BOQ.",
        [
            step("Product categories", "Products are grouped into 21 categories with a central taxonomy.",
                 "Equipment is grouped by category. Each card shows the supplier price and compliance.",
                 target=".solar-card, .card"),
            step("Filter by country", "Compliance badges reflect the selected country's standards.",
                 "Pick your country to see which products are compliant for your market.",
                 target='select[name="country"], #country', action="moveCursor"),
            step("Search a product", "Search narrows the catalogue as you type.",
                 "Search for the item you need, for example an LV cable.",
                 target='input[type="search"], input[name="q"]', action="typeText",
                 type_text="LV cable"),
            step("Open a product", "The product page shows specification, supplier and datasheet.",
                 "Open a product to see its full specification and datasheet link.",
                 target='a[href*="/marketplace/product/"]', action="moveCursor"),
            step("Add to BOQ", "Selected products flow into your BOM, BOQ and procurement list.",
                 "Add the product to a bill of quantities to price your project.",
                 target='button[type="submit"], .btn-warning'),
        ],
    ),
    "procurement_center": (
        "Procurement Center", "Procurement",
        "Tick the products you need and generate a priced procurement list or RFQ.",
        [
            step("Pick products", "The checkbox grid is grouped by category.",
                 "Tick every product you intend to buy. They are grouped by category.",
                 target='input[type="checkbox"]'),
            step("Generate price sheet", "A ten-column sheet with supplier contact details.",
                 "Generate the price sheet to get supplier names, phones and addresses.",
                 target='button[type="submit"], .btn-warning'),
            step("Send an RFQ", "Requests for quotation go to the selected suppliers.",
                 "Send a request for quotation and compare the responses side by side.",
                 target='a[href*="/rfqs"]', action="moveCursor"),
        ],
    ),
    "boms_list": (
        "Bills of Quantities", "BOQ",
        "Build a BOM, apply rates, review compliance and export the priced BOQ.",
        [
            step("Create a BOM", "Start from a building, floor or service template.",
                 "Start by creating a bill of materials for your building.",
                 target='a[href="/boms/new"]', action="moveCursor"),
            step("Open the BOQ", "The BOQ nests under each BOM with bills and sections.",
                 "Open the bill of quantities to see every bill and section.",
                 target='a[href*="/boq"]', action="moveCursor"),
            step("Apply rates", "Rate build-up applies markup to material, labour and plant.",
                 "Apply your rate build-up so every line carries a real unit rate.",
                 target=".btn-warning, button[type=submit]"),
            step("Compliance review", "Missing specs, units and suppliers are flagged by severity.",
                 "The compliance review flags missing specifications before you quote.",
                 target=".alert, .solar-card"),
            step("Export", "Excel and PDF exports are client-ready.",
                 "Export the priced BOQ to Excel or PDF for your client.",
                 target='a[href$=".xlsx"], a[href$=".pdf"]', action="moveCursor"),
        ],
    ),
    "capital_investment_landing": (
        "Generation Station Design", "Generation Station",
        "The 14-step utility-scale wizard: site, buildings, PV field, SCADA, finance, BOQ, reports.",
        [
            step("Create a plant", "Each project carries site, technology, electrical and finance config.",
                 "Create a plant to start the fourteen-step utility-scale wizard.",
                 target='a[href*="/large-scale-solar/new"]', action="moveCursor"),
            step("Your plants", "Open any plant to resume where you left off.",
                 "Your existing plants are listed here. Open one to resume the wizard.",
                 target=".solar-card, .card"),
        ],
    ),
    "capital_investment_project": (
        "Generation Station Project", "Generation Station",
        "Run the wizard steps, then open the twin, the SLD, the reports and the funding pack.",
        [
            step("The 14 steps", "Complete steps in order; each unlocks the next output.",
                 "Work through the fourteen steps. Step seven commits your PV sizing.",
                 target=".card, .solar-card"),
            step("Cost Plan Deck", "A board-ready capital cost deck.",
                 "The cost plan deck summarises capital cost for your investors.",
                 target='a[href*="/cost-plan"]', action="moveCursor"),
            step("3D Digital Twin", "An interactive model of the plant you designed.",
                 "Open the three-D digital twin to walk through the plant you designed.",
                 target='a[href*="/digital-twin"]', action="moveCursor"),
            step("Project Funding", "Submit the plant to a financial institution.",
                 "Project funding packages your design for a financial institution.",
                 target='a[href*="/funding"]', action="moveCursor"),
        ],
    ),
    "capital_investment_digital_twin": (
        "3D Digital Twin", "3D Digital Twin",
        "Rotate the plant, run the sun path, compute shading, inspect equipment and export the scene.",
        [
            step("The 3D viewport", "Drag to orbit, scroll to zoom, click any object to inspect it.",
                 "This is your plant in three dimensions. Drag to orbit and scroll to zoom.",
                 target="#dt-viewport", duration=1100),
            step("Design parameters", "Change tilt, azimuth or row spacing and re-run the simulation.",
                 "Change the tilt, azimuth or row spacing on the left.",
                 target="#dt-param-body, .dt-card-title", action="moveCursor"),
            step("Run the simulation", "The server recomputes shading, yield and the BOQ.",
                 "Run the simulation. The server recomputes shading, yield and the bill of quantities.",
                 target="#dt-run-sim", action="click"),
            step("Sun path and shading", "Scrub month and hour to see shadows move across the array.",
                 "Scrub the month and hour sliders to watch shadows move across the array.",
                 target="#dt-timeline-ov", duration=1000),
            step("Inspect equipment", "Click a transformer or inverter for its specification and BOQ link.",
                 "Click any transformer or inverter to inspect its specification.",
                 target="#dt-props, .dt-analysis-pane", action="moveCursor"),
            step("Camera presets", "Aerial, ground, inverter, substation and night views.",
                 "The virtual reality cards fly the camera to a preset viewpoint.",
                 target=".dt-vr-card", action="moveCursor"),
            step("Export", "Export a PNG, the scene JSON, the object schedule or a shadow report.",
                 "Export an investor image, the scene, or the shadow report.",
                 target="#exp-png", action="moveCursor"),
        ],
    ),
    "capital_investment_electrical_sld": (
        "Electrical Single-Line Diagram", "Reports",
        "The as-designed one-line: array, strings, combiners, inverters, transformers, MV busbar and grid POI.",
        [
            step("The single-line diagram", "Drawn from the same sizing that feeds the equipment schedule.",
                 "This is the single-line diagram of your plant, drawn from your committed sizing.",
                 target='svg[aria-label="Single-line diagram"]', duration=1400),
            step("One inverter station", "The dashed boundary is the typical station, repeated N times.",
                 "The dashed boundary shows one typical inverter station, repeated across the plant.",
                 target='svg[aria-label="Single-line diagram"]'),
            step("Equipment schedule", "Every stage carries its ratings, protection and standards.",
                 "Below the drawing, each stage lists its ratings, protection and the standards applied.",
                 target=".sld-chain"),
            step("Cable schedule", "Segment, type, size and length for every connection.",
                 "The cable schedule gives the type, size and length of every connection.",
                 target="table"),
            step("Print or export", "The page prints to a clean A4 PDF.",
                 "Print the diagram to PDF for your submission pack.",
                 target='button[onclick*="print"]', action="moveCursor"),
        ],
    ),
    "capital_investment_funding": (
        "Project Funding", "Project Funding",
        "Package the design, pick a financial institution, consent, submit and track the review.",
        [
            step("Funding overview", "The pack bundles design, BOQ and financial model.",
                 "The funding pack bundles your design, bill of quantities and financial model.",
                 target=".solar-card"),
            step("Choose an institution", "Registered financial institutions appear here.",
                 "Choose the financial institution you want to approach.",
                 target="select, .card", action="moveCursor"),
            step("Consent and submit", "You must consent before your data is shared.",
                 "Give consent, then submit. Nothing is shared until you consent.",
                 target='button[type="submit"], .btn-warning'),
            step("Track the review", "The bank workspace shows status and any request for information.",
                 "Track the review status and respond to any request for information.",
                 target=".badge, .solar-card"),
        ],
    ),
    "support": (
        "Support & Guides", "Support",
        "Guides, the helpline assistant, and the guided tour for every page.",
        [
            step("Guides", "User, technical and portal guides, downloadable as PDF.",
                 "The guides cover the platform end to end and download as PDF.",
                 target='a[href*="/guides/"]', action="moveCursor"),
            step("Every page teaches itself", "Look for Help & Tutorial at the bottom-left of any page.",
                 "On any page, use Help and Tutorial to run a guided tour, an auto demo, "
                 "or ask the assistant to explain the page.",
                 target=".sp-tut-launcher", duration=1400),
            step("Record your own video", "The Record button exports the demo as a .webm video.",
                 "During a demo you can record the screen and export it as a video file.",
                 target=".sp-tut-launcher"),
        ],
    ),
}


def main() -> int:
    """Write one JSON per endpoint plus an index manifest. out: exit code."""
    os.makedirs(OUT, exist_ok=True)
    index = []
    for endpoint, (title, module, desc, stps) in SCENARIOS.items():
        doc = {
            "tutorialId": f"tut-{endpoint}",
            "pageId": endpoint,
            "title": title,
            "module": module,
            "description": desc,
            "version": 1,
            "language": "en-US",
            "estimatedDuration": sum(s.get("duration", 700) + 900 for s in stps) // 1000,
            "steps": [dict(s, stepNumber=i + 1) for i, s in enumerate(stps)],
        }
        path = os.path.join(OUT, f"{endpoint}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
        index.append({"pageId": endpoint, "title": title, "module": module,
                      "steps": len(stps), "estimatedDuration": doc["estimatedDuration"]})
        print(f"  {endpoint:38} {len(stps)} steps")

    with open(os.path.join(OUT, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"version": 1, "tutorials": index}, f, indent=2, ensure_ascii=False)
    print(f"\n{len(index)} scenarios -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
