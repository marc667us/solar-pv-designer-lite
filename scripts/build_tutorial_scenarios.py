"""Author the Tutorial & Demo Engine's scenario definitions.

Every SolarPro page registers its tutorial as a JSON definition keyed by the
Flask endpoint name; the engine (static/tutorial/tutorial-engine.js) loads
/static/tutorial/scenarios/<endpoint>.json and plays it. Pages never hard-code a
tutorial (spec: pvsolar1/"video tutorial.txt").

Three rules this file enforces, per the owner's brief:

1. A tutorial shows EVERY SCREEN involved in running the feature. A `nav()` step
   carries the tour to the next screen; the engine parks its place in
   sessionStorage and resumes there. Destinations that need a record id are
   resolved at run time from a link on the page (`href_from`), because the id is
   unknowable when the scenario is authored.

2. EVERY screen shows cursor movement. `step()` defaults to the `moveCursor`
   action whenever it has a target, so the animated cursor visibly travels to
   each control it is talking about. Only steps with no target (a whole-page
   remark) stay as `highlightOnly`.

3. Coverage is checked, not assumed. `scripts/sync_tutorials.py` fails when a
   user-facing feature has no scenario, or when a scenario points at a control
   that no longer exists -- so adding or changing a feature forces the tutorial
   to be created or updated.

Regenerate:  python scripts/build_tutorial_scenarios.py
in : SCENARIOS (below)
out: static/tutorial/scenarios/<endpoint>.json + index.json (coverage manifest)
"""
from __future__ import annotations

import json
import os

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "static", "tutorial", "scenarios")

CURSOR_ACTIONS = {"moveCursor", "hover", "click", "doubleClick", "typeText",
                  "selectOption", "drag", "drop", "rotate3D", "zoom", "pan"}


def step(title, desc, voice, *, target="", action=None, type_text="",
         dispatch=False, duration=700, fallback="", screen="", dynamic=False):
    """One scenario step.

    Defaults to `moveCursor` when a target is given so every screen shows the
    cursor travelling to the control being described (owner rule 2).

    in : copy + selector + optional action override
    out: dict matching the engine's step contract
    """
    if action is None:
        action = "moveCursor" if target else "highlightOnly"
    s = {
        "title": title,
        "description": desc,
        "voiceScript": voice,
        "captionText": voice,
        "targetSelector": target,
        "action": action,
        "duration": duration,
        "delayBefore": 120,
        "screen": screen,
        "fallbackMessage": fallback or f"{title}: not visible on this screen yet.",
    }
    if type_text:
        s["typeText"] = type_text
    if dispatch:
        s["dispatch"] = True
    if dynamic:
        # Injected by client JS, so it is absent from the server-rendered HTML.
        # sync_tutorials.py must not report it as a dead selector.
        s["dynamic"] = True
    return s


def nav(title, desc, voice, *, href="", href_from="", target="", screen="",
        fallback=""):
    """A hop to the next screen of the same feature (owner rule 1).

    Exactly one of `href` (a static URL) or `href_from` (a CSS selector whose
    anchor supplies the URL at run time, for id-bearing routes) must be given.
    """
    assert bool(href) ^ bool(href_from), f"{title}: give href OR href_from"
    s = step(title, desc, voice, target=target or href_from,
             action="navigate", screen=screen,
             fallback=fallback or f"{title}: the next screen is not reachable from here.")
    if href:
        s["href"] = href
    else:
        s["hrefFromSelector"] = href_from
    return s


# A flow that walks other pages "covers" them: those pages need no duplicate
# tutorial of their own. sync_tutorials.py reads this from the emitted JSON.
# `covers` is a claim that this flow ACTUALLY NAVIGATES to those screens -- it is
# not a place to silence the coverage gate. Every entry below corresponds to a
# nav() step in the flow. Screens nothing walks are drafted by
# `scripts/sync_tutorials.py --write` and marked {"draft": true}; the engine never
# shows a draft to a user, so a draft is visible backlog, not a shipped tutorial.
COVERS: dict[str, list[str]] = {
    "marketplace_public": ["marketplace_product_detail", "procurement_center",
                           "rfqs_list"],
    "boms_list": ["boms_new", "boms_boq"],
    "rfqs_list": ["rfqs_new"],
    "boq_projects_list": ["boq_wizard"],
    "supplier_dashboard": ["supplier_product_add"],
    "admin_sales": ["admin_pipeline"],
    "procurement_center": ["rfqs_list"],
    "procurement": ["procurement_catalog", "procurement_suppliers"],
    "capital_investment_landing": [
        "capital_investment_project", "capital_investment_digital_twin",
        "capital_investment_electrical_sld", "capital_investment_funding",
    ],
    # The wizard flow walks every numbered step screen.
    "capital_investment_project": [f"capital_investment_step{n}" for n in range(2, 15)],
    "capital_investment_digital_twin": ["capital_investment_electrical_sld"],
    # The reports flow walks these four; the rest are drafted.
    "report_pv": ["report_energy", "report_cable", "report_boq", "report_economic"],
    "project_results": ["report_pv"],
}


def wizard_steps() -> list:
    """Walk the Generation Station wizard's numbered screens (owner rule 1).

    Each hop resolves its href from the step link on the current page, because
    the URL carries a project id we cannot know at authoring time.
    out: list of steps
    """
    titles = {
        2: ("Site", "Land area, GPS and terrain."),
        3: ("Buildings", "Control room, O&M building, warehouse."),
        4: ("Technology", "Module technology and mounting."),
        5: ("Electrical", "Voltages, MV collection and the point of interconnection."),
        6: ("Control & SCADA", "Plant controller, metering and telemetry."),
        7: ("PV sizing", "The step that commits the sizing everything else depends on."),
        8: ("Finance", "Capex, opex, tariff and the financial model."),
        9: ("BOQ", "The priced bill of quantities, built from the sizing."),
        10: ("Marketplace", "Price the BOQ against real supplier products."),
        11: ("Procurement", "Turn the priced BOQ into a buying list."),
        12: ("Regulatory", "Land tenure, permits and grid consent."),
        13: ("Reports", "Thirteen downloadable engineering and finance reports."),
        14: ("AI agents", "Fifteen specialist agents review the design."),
    }
    out = []
    for n, (name, desc) in titles.items():
        out.append(nav(f"Step {n}: {name}", desc,
                       f"Step {n}. {desc}",
                       href_from=f'a[href$="/step{n}"]', screen=f"Step {n}",
                       fallback=f"Step {n} is not unlocked yet."))
        out.append(step(f"{name} screen", desc, f"This is the {name.lower()} screen.",
                        target="form, .solar-card, .card", screen=f"Step {n}"))
    return out


# endpoint -> (title, module, description, [steps])
SCENARIOS: dict[str, tuple] = {
    # ---------------------------------------------------------------- core
    "dashboard": (
        "Dashboard", "Dashboard",
        "Your projects, the quick actions, and the way into every other module.",
        [
            step("Your projects", "Every design you create is listed here with its status.",
                 "This is your dashboard. Every solar design you create appears here.",
                 target=".solar-card", screen="Dashboard"),
            step("Create a design", "Start a residential, commercial or industrial PV design.",
                 "To begin a new design, use Create Standard Project.",
                 target='a[href="/project/new"], a[href*="project/new"]', screen="Dashboard"),
            step("Generation Station", "Utility-scale plants use the 14-step wizard.",
                 "For utility-scale plants, open Generation Station Design.",
                 target='a[href="/large-scale-solar"]', screen="Dashboard"),
            step("Marketplace", "Priced equipment feeds your BOQ and procurement lists.",
                 "The Marketplace supplies live equipment prices to your bills of quantities.",
                 target='a[href*="/marketplace"]', screen="Dashboard"),
        ],
    ),
    "project_new": (
        "Create a Solar Design", "Solar Design",
        "Name the design, file it, then set the location that fixes irradiance and tariff.",
        [
            step("Project name", "Every design starts with a name.",
                 "Start by naming the project.", target='input[name="name"]',
                 action="typeText", type_text="Accra Rooftop 25 kWp", screen="New project"),
            step("Folder", "Designs are filed so you can find them later.",
                 "File it in a folder so you can find it again.",
                 target='input[name="folder"]', screen="New project"),
            step("Create and set location", "The next screen is the globe: pick the site.",
                 "Create the project. The next screen is the globe, where you pick the site. "
                 "Location fixes the sun hours, the temperature and the tariff.",
                 target='button[type="submit"]', screen="New project"),
        ],
    ),
    "project_location": (
        "Set the Site Location", "Solar Design",
        "The globe fixes irradiance, temperature, tariff and currency for the design.",
        [
            step("Spin the globe", "Click your site, or search for it.",
                 "Click your site on the globe. The marker turns green once it is set.",
                 target="canvas, #globe", action="drag", duration=1200, screen="Location"),
            step("Search instead", "Typing a place name flies the globe to it.",
                 "You can also type a place name and the globe flies to it.",
                 target='input[type="text"], input[name*="search"]', screen="Location"),
            step("Continue to loads", "Location fixes sun hours, temperature and tariff.",
                 "Continue. Your location now fixes the sun hours, temperature and tariff.",
                 target='button[type="submit"], .btn-warning', screen="Location"),
        ],
    ),
    "project_loads": (
        "Load Schedule", "Solar Design",
        "List what the building runs, and for how long, so the array can be sized.",
        [
            step("Add appliances", "Each load carries a wattage and daily hours.",
                 "Add each appliance with its wattage and how many hours it runs.",
                 target="table, .solar-card", screen="Loads"),
            step("Daily energy", "The total drives the PV, battery and inverter sizing.",
                 "The daily energy total drives the array, battery and inverter sizing.",
                 target=".solar-card, tfoot", screen="Loads"),
            step("Run the design", "Loads, PV, battery, inverter, MPPT, cables, BOQ, economics.",
                 "Run the design. The engine sizes everything from this schedule.",
                 target='button[type="submit"], .btn-warning', screen="Loads"),
        ],
    ),
    "project_results": (
        "Design Results", "Solar Design",
        "The sized system, and every report that falls out of it.",
        [
            step("The sized system", "Array, inverter, battery, cables and economics.",
                 "Here is the sized system: array, inverter, battery, cables and payback.",
                 target=".solar-card, .kpi-card", screen="Results"),
            nav("Open the PV report", "The engineering report behind the numbers.",
                "Let us open the PV report that explains those numbers.",
                href_from='a[href*="/report/pv"]', screen="Results"),
            step("The PV report", "Every calculation, its inputs and its standard.",
                 "Each calculation shows its inputs, its result and the standard behind it.",
                 target=".solar-card, table", screen="PV report"),
        ],
    ),
    "report_pv": (
        "Engineering Reports", "Reports",
        "Every report the design produces: PV, energy, cable, BOQ, economics, proposal.",
        [
            step("The PV report", "Array sizing, string design and derating.",
                 "The PV report covers array sizing, string design and derating.",
                 target=".solar-card, table", screen="PV report"),
            nav("Energy report", "Yield month by month.",
                "The energy report gives the yield month by month.",
                href_from='a[href*="/report/energy"]', screen="PV report"),
            step("Energy yield", "Monthly production against the load schedule.",
                 "Monthly production is compared against your load schedule.",
                 target=".solar-card, table", screen="Energy report"),
            nav("Cable report", "Sizing, volt drop and protection.",
                "The cable report sizes every run and checks volt drop.",
                href_from='a[href*="/report/cable"]', screen="Energy report"),
            step("Cable sizing", "Volt drop and current capacity per run.",
                 "Each run is checked for current capacity and volt drop.",
                 target=".solar-card, table", screen="Cable report"),
            nav("BOQ report", "The priced bill for the design.",
                "The BOQ report prices the whole design.",
                href_from='a[href*="/report/boq"]', screen="Cable report"),
            step("The priced bill", "Every item, rate and total.",
                 "Every item carries its rate and its total.",
                 target="table, .solar-card", screen="BOQ report"),
            nav("Economic report", "Payback, IRR and lifetime savings.",
                "Finally the economic report: payback, internal rate of return and savings.",
                href_from='a[href*="/report/economic"]', screen="BOQ report"),
            step("Payback", "Against the tariff at your location.",
                 "Payback is computed against the tariff at your location.",
                 target=".solar-card, table", screen="Economic report"),
        ],
    ),
    "marketplace_product_detail": (
        "Product Detail", "Marketplace",
        "The full specification, the supplier, the datasheet and the way into a BOQ.",
        [
            step("Specification", "Voltage, size, standard and compliance.",
                 "This is the full specification, with the standards it complies with.",
                 target=".solar-card, table", screen="Product"),
            step("Datasheet", "Links resolve to the manufacturer's own document.",
                 "The datasheet link resolves to the manufacturer's own document.",
                 target='a[href*="doc"], a[target="_blank"]', screen="Product"),
            step("Add to BOQ", "The product joins your bill of quantities.",
                 "Adding it puts the product into your bill of quantities.",
                 target='button[type="submit"], .btn-warning', screen="Product"),
        ],
    ),
    "price_sheet_view": (
        "Price Sheet", "Procurement",
        "A ten-column buying sheet with supplier contact details, ready to send.",
        [
            step("The sheet", "Item, quantity, unit, price, supplier and contact.",
                 "Each line carries the price, the supplier, and how to reach them.",
                 target="table, .solar-card", screen="Price sheet"),
            step("Send or print", "Prices are a snapshot from when it was built.",
                 "Send or print it. The prices are a snapshot from when you built it.",
                 target="button, a", screen="Price sheet"),
        ],
    ),
    "account": (
        "Account & Subscription", "Billing",
        "Your plan, invoices, and how to change or cancel.",
        [
            step("Your plan", "The trial converts without losing any work.",
                 "This is your current plan. Upgrading never touches your designs.",
                 target=".solar-card", screen="Account"),
            step("Manage the subscription", "Cancel or change plan at any time.",
                 "You can change or cancel the subscription at any time.",
                 target="button", screen="Account"),
        ],
    ),
    "assessment_request": (
        "Energy Assessment", "Energy Assessment",
        "Capture the site's loads and consumption before designing anything.",
        [
            step("Tell us about the site", "The assessment feeds the design's load schedule.",
                 "Describe the site. This becomes the load schedule your design is sized against.",
                 target="form, .solar-card", screen="Assessment"),
            step("Submit", "Our team reviews and returns a recommendation.",
                 "Submit the assessment and we return a sizing recommendation.",
                 target='button[type="submit"]', screen="Assessment"),
        ],
    ),
    "bill_check_landing": (
        "Check My Bill", "Bill Check",
        "Enter a utility bill, compare it against the PURC tariff, and see solar coverage.",
        [
            step("Enter your bill", "Type the amount from your latest electricity bill.",
                 "Enter the amount on your latest electricity bill.",
                 target='input[type="number"], input[name*="bill"]',
                 action="typeText", type_text="850", screen="Bill Check"),
            step("Check it", "We invert the PURC tariff to find your true consumption.",
                 "We compare it against the current PURC tariff to find your real consumption.",
                 target='button[type="submit"], .btn-warning', screen="Bill Check"),
            step("Solar coverage", "How much of that bill a solar design would remove.",
                 "The result shows how much of the bill solar would cover.",
                 target=".solar-card", screen="Bill Check"),
        ],
    ),
    "project_shading": (
        "Shading Simulation", "Shading",
        "Move the sun through the year and watch obstructions shade the array.",
        [
            step("The site model", "Buildings and obstructions are drawn to scale.",
                 "This is your site with its buildings and obstructions drawn to scale.",
                 target="svg, canvas", screen="Shading"),
            step("Move the sun", "Scrub month and hour to sweep the sun path.",
                 "Scrub the month and hour to move the sun across the sky.",
                 target='input[type="range"]', action="drag", screen="Shading"),
            step("Read the losses", "Row-by-row shading loss drives the yield estimate.",
                 "The shading loss per row feeds straight into the yield estimate.",
                 target=".solar-card, table", screen="Shading"),
        ],
    ),

    # ------------------------------------------- marketplace -> BOQ -> RFQ flow
    "marketplace_public": (
        "Marketplace → Product → Procurement", "Marketplace",
        "Every screen of buying: browse the catalogue, open a product, "
        "build a procurement list, then raise an RFQ.",
        [
            step("Product categories", "Products are grouped into 21 categories.",
                 "Equipment is grouped by category, each card showing its supplier price.",
                 target=".solar-card, .card", screen="Marketplace"),
            step("Filter by country", "Compliance badges follow the selected market.",
                 "Pick your country to see which products are compliant for your market.",
                 target='select[name="country"], #country', screen="Marketplace"),
            step("Search", "Search narrows the catalogue as you type.",
                 "Search for the item you need, for example an LV cable.",
                 target='input[type="search"], input[name="q"]',
                 action="typeText", type_text="LV cable", screen="Marketplace"),
            nav("Open a product", "The product screen carries the full specification.",
                "Let us open a product to see its full specification.",
                href_from='a[href*="/marketplace/product/"]', screen="Marketplace"),
            step("Specification", "Voltage, size, standard and datasheet link.",
                 "This is the product specification, with a link to the manufacturer datasheet.",
                 target=".solar-card, table", screen="Product"),
            step("Add to BOQ", "Selected products flow into your BOM and BOQ.",
                 "Adding the product puts it into your bill of quantities.",
                 target='button[type="submit"], .btn-warning', screen="Product"),
            nav("Procurement Center", "Where the buying list is assembled.",
                "Now we move to the Procurement Center to assemble the buying list.",
                href="/procurement-center", screen="Product"),
            step("Tick what you need", "The checkbox grid is grouped by category.",
                 "Tick every product you intend to buy.",
                 target='input[type="checkbox"]', screen="Procurement Center"),
            step("Generate the price sheet", "Ten columns including supplier contact details.",
                 "Generate the price sheet: supplier names, phones and addresses included.",
                 target='button[type="submit"], .btn-warning', screen="Procurement Center"),
            nav("Raise an RFQ", "Ask suppliers to quote against the list.",
                "Finally, raise a request for quotation so suppliers can bid.",
                href="/rfqs", screen="Procurement Center"),
            step("Your RFQs", "Track every quotation request and compare responses.",
                 "Every quotation request is tracked here so you can compare the responses.",
                 target=".solar-card, table", screen="RFQs"),
        ],
    ),
    "procurement_center": (
        "Procurement Center", "Procurement",
        "Tick the products you need and generate a priced procurement list or RFQ.",
        [
            step("Pick products", "The checkbox grid is grouped by category.",
                 "Tick every product you intend to buy.",
                 target='input[type="checkbox"]', screen="Procurement Center"),
            step("Generate price sheet", "A ten-column sheet with supplier contacts.",
                 "Generate the price sheet to get supplier names, phones and addresses.",
                 target='button[type="submit"], .btn-warning', screen="Procurement Center"),
            nav("Send an RFQ", "Requests for quotation go to the selected suppliers.",
                "Send a request for quotation and compare the responses side by side.",
                href="/rfqs", screen="Procurement Center"),
            step("RFQ list", "Every request and its responses.",
                 "Here is every request you have raised.",
                 target=".solar-card, table", screen="RFQs"),
        ],
    ),
    "rfqs_list": (
        "Requests for Quotation", "Procurement",
        "Raise a quotation request, watch supplier responses arrive, and compare them.",
        [
            step("Your requests", "Each RFQ carries its targeted suppliers and status.",
                 "Each request shows the suppliers it went to and where it stands.",
                 target=".solar-card, table", screen="RFQs"),
            nav("Raise a new RFQ", "Pick products and suppliers.",
                "Let us raise a new request for quotation.",
                href="/rfqs/new", screen="RFQs"),
            step("Choose suppliers", "An RFQ with no targets is rejected.",
                 "Choose the suppliers who should quote. An RFQ needs at least one.",
                 target="select, input[type=checkbox]", screen="New RFQ"),
            step("Send it", "Suppliers are emailed and respond in their portal.",
                 "Send it. Suppliers are notified and respond in their own portal.",
                 target='button[type="submit"], .btn-warning', screen="New RFQ"),
        ],
    ),
    "price_sheets_list": (
        "Price Sheets", "Procurement",
        "Every generated price sheet, ready to send to a client or a buyer.",
        [
            step("Saved sheets", "Each sheet snapshots the prices at the time it was built.",
                 "Each price sheet snapshots the supplier prices at the moment you built it.",
                 target=".solar-card, table", screen="Price sheets"),
            step("Open one", "Item, quantity, unit, price, supplier and contact.",
                 "Open a sheet to see the items, prices and supplier contacts.",
                 target="a", screen="Price sheets"),
        ],
    ),

    # -------------------------------------------------------------- BOQ / rates
    "boms_list": (
        "BOM → BOQ → Export", "BOQ",
        "Every screen of pricing a job: build the BOM, open the BOQ, apply rates, export.",
        [
            step("Your bills of materials", "A BOM lists what the job needs.",
                 "A bill of materials lists everything the job needs.",
                 target=".solar-card, table", screen="BOMs"),
            nav("Create a BOM", "Start from a building, floor or service template.",
                "Let us create one from a template.", href="/boms/new", screen="BOMs"),
            step("Choose the template", "Five floor templates and fifteen services.",
                 "Choose the building and the services this bill covers.",
                 target="select, form", screen="New BOM"),
            step("Create it", "The BOM opens with its sections ready for quantities.",
                 "Create it, and the sections open ready for quantities.",
                 target='button[type="submit"], .btn-warning', screen="New BOM"),
            nav("Open the BOQ", "The BOQ nests under the BOM as bills and sections.",
                "The bill of quantities nests under the BOM as bills and sections.",
                href_from='a[href*="/boq"]', screen="BOMs"),
            step("Compliance review", "Missing specs, units and suppliers, ranked by severity.",
                 "The compliance review flags missing specifications before you quote.",
                 target=".alert, .solar-card", screen="BOQ"),
            step("Export", "Excel and PDF exports are client-ready.",
                 "Export the priced bill to Excel or PDF for your client.",
                 target='a[href$=".xlsx"], a[href$=".pdf"]', screen="BOQ"),
        ],
    ),
    "boq_projects_list": (
        "BOQ Projects", "BOQ",
        "Campus, building and floor BOQs with cost roll-up to a single summary.",
        [
            step("Your BOQ projects", "Costs roll up floor → building → campus.",
                 "Costs roll up from each floor to the building and the whole campus.",
                 target=".solar-card, table", screen="BOQ projects"),
            nav("Start the wizard", "The wizard configures buildings, floors and services.",
                "The wizard walks you through buildings, floors and services.",
                href="/boq-projects/wizard", screen="BOQ projects"),
            step("Configure", "Pick the services each floor carries.",
                 "Pick the services each floor carries, then generate the bills.",
                 target="form, .solar-card", screen="Wizard"),
        ],
    ),
    "rate_form": (
        "Rate Build-Up", "Rate Build-Up",
        "Build a unit rate from material, labour, plant, overhead and profit.",
        [
            step("Material, labour, plant", "Each component is entered separately.",
                 "Enter the material, labour and plant that make up the rate.",
                 target="input, form", screen="Rate build-up"),
            step("Overhead and profit", "Markup is applied on top, never inside, the cost.",
                 "Overhead and profit are applied as markup on top of the cost.",
                 target='input[name*="markup"], input', screen="Rate build-up"),
            step("Compute", "The compound rate flows into every BOQ line that uses it.",
                 "The computed rate flows into every bill of quantities line that uses it.",
                 target='button[type="submit"], .btn-warning', screen="Rate build-up"),
        ],
    ),

    # ----------------------------------------------- Generation Station flow
    "capital_investment_landing": (
        "Generation Station: every screen", "Generation Station",
        "From creating the plant, through the wizard, to the twin, the SLD and funding.",
        [
            step("Your plants", "Each plant carries site, technology, electrical and finance config.",
                 "Each utility-scale plant you create is listed here.",
                 target=".solar-card, .card", screen="Generation Station"),
            step("Create a plant", "Starts the fourteen-step wizard.",
                 "Creating a plant starts the fourteen-step wizard.",
                 target='a[href*="/large-scale-solar/new"]', screen="Generation Station"),
            nav("Open a plant", "The project screen is the hub for every output.",
                "Let us open an existing plant.",
                href_from='a[href^="/large-scale-solar/"]', screen="Generation Station"),
            step("The 14 steps", "Step 7 commits the PV sizing everything else depends on.",
                 "Work through the fourteen steps. Step seven commits the PV sizing.",
                 target=".card, .solar-card", screen="Project"),
            step("Cost Plan Deck", "A board-ready capital cost deck.",
                 "The cost plan deck summarises capital cost for your investors.",
                 target='a[href*="/cost-plan"]', screen="Project"),
            nav("Open the 3D twin", "The plant you designed, in three dimensions.",
                "Now we open the three-D digital twin of the plant.",
                href_from='a[href*="/digital-twin"]', screen="Project"),
            step("Orbit the plant", "Drag to orbit, scroll to zoom, click to inspect.",
                 "Drag to orbit and scroll to zoom around your plant.",
                 target="#dt-viewport", action="rotate3D", duration=1200, screen="Digital twin"),
            step("Run the simulation", "Recomputes shading, yield and the BOQ.",
                 "Running the simulation recomputes shading, yield and the bill of quantities.",
                 target="#dt-run-sim", action="click", screen="Digital twin"),
            nav("Open the single-line diagram", "The as-designed electrical one-line.",
                "From the outputs rail we open the electrical single-line diagram.",
                href_from='a[href*="/electrical-sld"]', screen="Digital twin"),
            step("The one-line", "Array to grid, drawn from the committed sizing.",
                 "This is the plant's one-line, from the array all the way to the grid.",
                 target='svg[aria-label="Single-line diagram"]', duration=1400, screen="SLD"),
            nav("Project funding", "Package the design for a financial institution.",
                "Finally, project funding packages the design for a bank.",
                href_from='a[href*="/funding"]', screen="SLD",
                fallback="Funding: open it from the project screen."),
            step("Submit for funding", "Consent first; nothing is shared until you do.",
                 "Give consent and submit. Nothing is shared with a bank until you consent.",
                 target='button[type="submit"], .btn-warning', screen="Funding"),
        ],
    ),
    "capital_investment_project": (
        "Generation Station: the 14-step wizard", "Generation Station",
        "Every screen of the wizard, from site through PV sizing and BOQ to the reports.",
        [
            step("The 14 steps", "Complete them in order; each unlocks the next output.",
                 "The wizard has fourteen steps. We will walk every one of them.",
                 target=".card, .solar-card", screen="Project"),
            step("Cost Plan Deck", "A board-ready capital cost deck.",
                 "The cost plan deck summarises capital cost for your investors.",
                 target='a[href*="/cost-plan"]', screen="Project"),
            *wizard_steps(),
        ],
    ),
    "capital_investment_digital_twin": (
        "3D Digital Twin", "3D Digital Twin",
        "Rotate the plant, run the sun path, compute shading, inspect equipment, export the scene.",
        [
            step("The 3D viewport", "Drag to orbit, scroll to zoom, click any object.",
                 "This is your plant in three dimensions. Drag to orbit and scroll to zoom.",
                 target="#dt-viewport", action="rotate3D", duration=1200, screen="Digital twin"),
            step("Design parameters", "Change tilt, azimuth or row spacing.",
                 "Change the tilt, azimuth or row spacing on the left.",
                 target="#dt-param-body, .dt-card-title", screen="Digital twin"),
            step("Run the simulation", "The server recomputes shading, yield and the BOQ.",
                 "Run the simulation. The server recomputes shading, yield and the BOQ.",
                 target="#dt-run-sim", action="click", screen="Digital twin"),
            step("Sun path and shading", "Scrub month and hour to move the shadows.",
                 "Scrub the month and hour sliders to watch shadows cross the array.",
                 target="#dt-timeline-ov", action="drag", duration=1000, screen="Digital twin"),
            step("Inspect equipment", "Click a transformer for its spec and BOQ link.",
                 "Click any transformer or inverter to inspect its specification.",
                 target="#dt-props, .dt-analysis-pane", screen="Digital twin"),
            step("Camera presets", "Aerial, ground, inverter, substation, night.",
                 "The virtual-reality cards fly the camera to a preset viewpoint.",
                 target=".dt-vr-card", screen="Digital twin"),
            step("Export", "PNG, scene JSON, object schedule or shadow report.",
                 "Export an investor image, the scene, or the shadow report.",
                 target="#exp-png", screen="Digital twin"),
            nav("The single-line diagram", "The electrical view of the same plant.",
                "The outputs rail also carries the electrical single-line diagram.",
                href_from='a[href*="/electrical-sld"]', screen="Digital twin"),
            step("The one-line", "Array to grid POI, from the committed sizing.",
                 "Here is the same plant drawn as an electrical one-line.",
                 target='svg[aria-label="Single-line diagram"]', duration=1400, screen="SLD"),
        ],
    ),
    "capital_investment_electrical_sld": (
        "Electrical Single-Line Diagram", "Reports",
        "The as-designed one-line: array, strings, combiners, inverters, transformers, busbar, POI.",
        [
            step("The single-line diagram", "Drawn from the sizing that feeds the schedule.",
                 "This is the single-line diagram of your plant, from your committed sizing.",
                 target='svg[aria-label="Single-line diagram"]', duration=1400, screen="SLD"),
            step("One inverter station", "The dashed boundary repeats across the plant.",
                 "The dashed boundary is one typical inverter station, repeated N times.",
                 target='svg[aria-label="Single-line diagram"]', screen="SLD"),
            step("Equipment schedule", "Ratings, protection and standards per stage.",
                 "Below the drawing, each stage lists its ratings, protection and standards.",
                 target=".sld-chain", screen="SLD"),
            step("Cable schedule", "Segment, type, size and length.",
                 "The cable schedule gives the type, size and length of every connection.",
                 target="table", screen="SLD"),
            step("Print or export", "The page prints to a clean A4 PDF.",
                 "Print the diagram to PDF for your submission pack.",
                 target='button[onclick*="print"]', screen="SLD"),
        ],
    ),
    "capital_investment_funding": (
        "Project Funding", "Project Funding",
        "Package the design, pick an institution, consent, submit and track the review.",
        [
            step("Funding overview", "The pack bundles design, BOQ and financial model.",
                 "The funding pack bundles your design, BOQ and financial model.",
                 target=".solar-card", screen="Funding"),
            step("Choose an institution", "Registered financial institutions appear here.",
                 "Choose the financial institution you want to approach.",
                 target="select, .card", screen="Funding"),
            step("Consent and submit", "Nothing is shared until you consent.",
                 "Give consent, then submit. Nothing is shared until you consent.",
                 target='button[type="submit"], .btn-warning', screen="Funding"),
            step("Track the review", "The bank workspace shows status and any RFI.",
                 "Track the review and respond to any request for information.",
                 target=".badge, .solar-card", screen="Funding"),
        ],
    ),

    # ------------------------------------------------------------ supplier side
    "supplier_dashboard": (
        "Supplier Portal", "Marketplace",
        "List products, answer RFQs, and keep your prices current.",
        [
            step("Your products", "Verified products appear in the public catalogue.",
                 "Your listed products appear in the public catalogue once verified.",
                 target=".solar-card, table", screen="Supplier dashboard"),
            nav("Add a product", "Category drives the required specification fields.",
                "Let us add a product. The category drives which specs are required.",
                href="/supplier/products/add", screen="Supplier dashboard"),
            step("Specification fields", "Missing specs are flagged in a buyer's BOQ.",
                 "Fill the required specification fields, or buyers will see them flagged.",
                 target="form, input", screen="Add product"),
            step("Submit for verification", "An admin verifies before it goes public.",
                 "Submit it. An administrator verifies the listing before it goes public.",
                 target='button[type="submit"]', screen="Add product"),
        ],
    ),
    "supplier_rfqs_inbox": (
        "Supplier RFQ Inbox", "Marketplace",
        "See the quotation requests buyers sent you and respond with prices.",
        [
            step("Incoming requests", "Each request lists the products and quantities.",
                 "Each incoming request lists the products and quantities a buyer needs.",
                 target=".solar-card, table", screen="RFQ inbox"),
            step("Respond", "Your price and lead time go straight back to the buyer.",
                 "Respond with your price and lead time.",
                 target="a, button", screen="RFQ inbox"),
        ],
    ),

    # ------------------------------------------------------------- growth / CRM
    "admin_sales": (
        "Sales & CRM", "CRM",
        "Leads, their source, and the actions that move them along.",
        [
            step("The lead list", "Every lead carries a source and a score.",
                 "Every lead carries the source it came from and a score.",
                 target="table, .solar-card", screen="Sales"),
            nav("The pipeline", "Leads by stage, from new to won.",
                "The pipeline shows those leads by stage.",
                href="/admin/pipeline", screen="Sales"),
            step("Stages", "Drag a lead to move it along the pipeline.",
                 "Move a lead along the pipeline as it progresses.",
                 target=".solar-card, .card", screen="Pipeline"),
        ],
    ),
    "admin_pipeline": (
        "Sales Pipeline", "Sales Pipeline",
        "Leads by stage, with the value and age of each opportunity.",
        [
            step("Stages", "New, contacted, qualified, proposal, won.",
                 "The pipeline groups every opportunity by its stage.",
                 target=".solar-card, .card", screen="Pipeline"),
            step("Move a lead", "Moving a lead records an activity against it.",
                 "Moving a lead records an activity so nothing is lost.",
                 target=".card, .badge", screen="Pipeline"),
        ],
    ),
    "admin_users": (
        "User Administration", "Administration",
        "Accounts, roles and the audit trail behind every admin action.",
        [
            step("Accounts", "Roles decide which modules a user can reach.",
                 "Each account carries roles that decide which modules it can reach.",
                 target="table, .solar-card", screen="Users"),
            step("Every action is audited", "Admin actions are written to the audit chain.",
                 "Every administrative action is written to a tamper-evident audit chain.",
                 target=".solar-card", screen="Users"),
        ],
    ),
    "me_dashboard": (
        "My Workspace", "Support",
        "The work assigned to you, and the shortcuts into it.",
        [
            step("Assigned to you", "Tickets, RFQs and tasks in one place.",
                 "Everything assigned to you appears here.",
                 target=".solar-card, table", screen="My workspace"),
        ],
    ),
    "referrals_page": (
        "Referrals", "Growth",
        "Share your link, earn credit when a referral converts.",
        [
            step("Your referral link", "Every signup through it is attributed to you.",
                 "This is your referral link. Every signup through it is credited to you.",
                 target="input, code, .solar-card", screen="Referrals"),
            step("Your conversions", "Credit is applied when a referral upgrades.",
                 "Credit is applied when a referral upgrades to a paid plan.",
                 target="table, .solar-card", screen="Referrals"),
        ],
    ),
    "upgrade": (
        "Plans & Upgrade", "Billing",
        "Compare plans and upgrade; the trial converts without losing your work.",
        [
            step("Compare the plans", "Free trial, professional, business, enterprise.",
                 "Compare the plans. Your projects survive the upgrade untouched.",
                 target=".solar-card, .card", screen="Upgrade"),
            step("Upgrade", "Payment is handled by Paystack or Stripe.",
                 "Choose a plan and complete payment securely.",
                 target="button, .btn-warning", screen="Upgrade"),
        ],
    ),
    # ------------------------------------------------------- remaining features
    "landing": (
        "Welcome to SolarPro", "Dashboard",
        "What the platform does and where to start.",
        [
            step("What SolarPro does", "Design, price, procure and finance solar.",
                 "SolarPro designs, prices, procures and finances solar projects.",
                 target=".solar-card, section, h1", screen="Landing"),
            step("Start free", "A 14-day trial opens every module.",
                 "Start free. The trial opens every module for fourteen days.",
                 target='a[href*="register"], .btn-warning', screen="Landing"),
        ],
    ),
    "myproject_list": (
        "My Projects", "Dashboard",
        "Everything you have designed, with its status and reports.",
        [
            step("Your projects", "Open one to resume, report or export.",
                 "Open any project to resume it, or jump straight to its reports.",
                 target=".solar-card, table", screen="My projects"),
        ],
    ),
    "project_open": (
        "Open a Project", "Dashboard",
        "Reopen a saved design by name.",
        [
            step("Pick a project", "Designs are stored per user and tenant.",
                 "Pick the design you want to reopen.",
                 target="select, table, .solar-card", screen="Open project"),
        ],
    ),
    "folders_index": (
        "Document Folders", "Support",
        "Project documents, datasheets and generated reports in one place.",
        [
            step("Your folders", "Reports and uploads are filed per project.",
                 "Reports and uploads are filed against the project they belong to.",
                 target=".solar-card, table", screen="Folders"),
        ],
    ),
    "settings": (
        "Settings", "Administration",
        "Profile, currency, country and notification preferences.",
        [
            step("Your profile", "Country and currency drive prices across the app.",
                 "Your country and currency drive the prices you see everywhere.",
                 target="form, .solar-card", screen="Settings"),
            step("Save", "Changes apply immediately across every module.",
                 "Save. The change applies immediately across every module.",
                 target='button[type="submit"]', screen="Settings"),
        ],
    ),
    "tickets": (
        "Support Tickets", "Support",
        "Raise a ticket, track it, and escalate when the assistant cannot help.",
        [
            step("Your tickets", "Each ticket carries a priority and a status.",
                 "Each ticket carries a priority and a status you can follow.",
                 target=".solar-card, table", screen="Tickets"),
            step("Raise one", "The helpline assistant can escalate for you.",
                 "Raise a ticket, or let the helpline assistant escalate for you.",
                 target="a, button", screen="Tickets"),
        ],
    ),
    "support_dashboard": (
        "Installation Support", "Support",
        "Guidance for installers on site, from method statement to commissioning.",
        [
            step("Installation guidance", "Method statements and commissioning checks.",
                 "Method statements and commissioning checks for the crew on site.",
                 target=".solar-card", screen="Installation support"),
        ],
    ),
    "news_index": (
        "Industry News", "Growth",
        "Solar news and tenders, filtered for relevance and refreshed daily.",
        [
            step("The feed", "Non-solar results are filtered out automatically.",
                 "The feed carries solar news and tenders, filtered for relevance.",
                 target=".solar-card, article", screen="News"),
        ],
    ),
    "newsfeed_public": (
        "Community Feed", "Growth",
        "Installer achievements, supplier products and before/after roofs.",
        [
            step("The community feed", "Share your work and win referrals.",
                 "Share your installations here; each post can carry a referral link.",
                 target=".solar-card, article", screen="Newsfeed"),
        ],
    ),
    "public_opportunities": (
        "Tenders & Opportunities", "Growth",
        "Live solar tenders across Ghana and Africa, crawled and de-duplicated.",
        [
            step("Live opportunities", "History accumulates across deployments.",
                 "These are live solar tenders, crawled daily and de-duplicated.",
                 target=".solar-card, table", screen="Opportunities"),
        ],
    ),
    "growth_dashboard_page": (
        "Growth", "Growth",
        "Referrals, shares, leads and the campaigns that produced them.",
        [
            step("Growth activity", "Every share and referral is attributed.",
                 "Every share and referral is attributed back to the person who made it.",
                 target=".solar-card", screen="Growth"),
        ],
    ),
    "procurement": (
        "Procurement", "Procurement",
        "The catalogue, the suppliers, and the buying list built from them.",
        [
            step("Procurement home", "Catalogue, suppliers and price sheets.",
                 "Procurement brings together the catalogue, the suppliers and your buying list.",
                 target=".solar-card, .card", screen="Procurement"),
            nav("Product Catalogue", "Every product available to price a job.",
                "The product catalogue lists everything available to price a job.",
                href="/procurement/catalog", screen="Procurement"),
            step("Browse the catalogue", "Filter by category and specification.",
                 "Filter by category and specification to find the part you need.",
                 target=".solar-card, table", screen="Catalogue"),
            nav("Suppliers", "Who supplies each product, and how to reach them.",
                "The supplier register shows who supplies each product.",
                href="/procurement/suppliers", screen="Catalogue"),
            step("Supplier register", "Contact details travel into the price sheet.",
                 "These contact details travel straight into your price sheet.",
                 target=".solar-card, table", screen="Suppliers"),
        ],
    ),
    "installer_register": (
        "Installer Registration", "Growth",
        "Join the installer network and receive qualified leads.",
        [
            step("Register", "Verified installers receive routed leads.",
                 "Register as an installer to receive leads routed to your region.",
                 target="form, input", screen="Installer registration"),
            step("Submit", "An administrator verifies before you go live.",
                 "Submit. An administrator verifies you before you go live.",
                 target='button[type="submit"]', screen="Installer registration"),
        ],
    ),
    "funding_institution_workspace": (
        "Financial Institution Workspace", "Project Funding",
        "Every screen a bank uses: the queue, the applicant, the reports, the decision.",
        [
            step("Your review queue", "Applications routed to your institution.",
                 "Applications submitted to your institution land in this queue.",
                 target=".solar-card, table", screen="Workspace"),
            step("Open an applicant", "Design, BOQ and financial model in one pack.",
                 "Open an applicant to read the design, the BOQ and the financial model.",
                 target="a, tr", screen="Workspace"),
            step("Assess", "An AI assessment scores the application.",
                 "An AI assessment scores the application against your criteria.",
                 target=".solar-card, .badge", screen="Applicant"),
            step("Decide", "Approve in principle, request information, or decline.",
                 "Approve in principle, request more information, or decline.",
                 target="button, .btn-warning", screen="Applicant"),
        ],
    ),
    "support": (
        "Support & Guides", "Support",
        "Guides, the helpline assistant, and the guided tour on every page.",
        [
            step("Guides", "User, technical and portal guides, downloadable as PDF.",
                 "The guides cover the platform end to end and download as PDF.",
                 target='a[href*="/guides/"]', screen="Support"),
            step("Every page teaches itself", "Help & Tutorial sits on every page.",
                 "On any page, Help and Tutorial runs a guided tour, an auto demo, "
                 "or asks the assistant to explain the page.",
                 target=".sp-tut-launcher", duration=1400, screen="Support", dynamic=True),
            step("Record your own video", "The Record button exports the demo as .webm.",
                 "During a demo you can record the screen and export it as a video file.",
                 target=".sp-tut-launcher", screen="Support", dynamic=True),
        ],
    ),
}


def build_doc(endpoint: str, title: str, module: str, desc: str, stps: list) -> dict:
    """Assemble one scenario document. out: dict ready to serialise."""
    screens = []
    for s in stps:
        sc = s.get("screen") or ""
        if sc and sc not in screens:
            screens.append(sc)
    return {
        "tutorialId": f"tut-{endpoint}",
        "pageId": endpoint,
        "title": title,
        "module": module,
        "description": desc,
        "version": 2,
        "language": "en-US",
        "screens": screens,
        "covers": COVERS.get(endpoint, []),
        "estimatedDuration": sum(s.get("duration", 700) + 900 for s in stps) // 1000,
        "steps": [dict(s, stepNumber=i + 1) for i, s in enumerate(stps)],
    }


def main() -> int:
    """Write one JSON per endpoint plus an index manifest. out: exit code."""
    os.makedirs(OUT, exist_ok=True)
    index = []
    for endpoint, (title, module, desc, stps) in SCENARIOS.items():
        doc = build_doc(endpoint, title, module, desc, stps)
        with open(os.path.join(OUT, f"{endpoint}.json"), "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
        cursor = sum(1 for s in stps if s["action"] in CURSOR_ACTIONS)
        index.append({"pageId": endpoint, "title": title, "module": module,
                      "steps": len(stps), "screens": doc["screens"],
                      "estimatedDuration": doc["estimatedDuration"]})
        print(f"  {endpoint:36} {len(stps):2} steps  {cursor:2} cursor  "
              f"{len(doc['screens'])} screen(s)")

    with open(os.path.join(OUT, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"version": 2, "tutorials": index}, f, indent=2, ensure_ascii=False)
    print(f"\n{len(index)} scenarios -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
