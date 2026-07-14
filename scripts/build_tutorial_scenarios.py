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
    # The Quick Start flow walks onto the New Project screen (owner rule 1).
    "dashboard": ["project_new"],
    "marketplace_public": ["marketplace_product_detail", "procurement_center",
                           "rfqs_list"],
    "boms_list": ["boms_new", "boms_boq"],
    "rfqs_list": ["rfqs_new"],
    "boq_projects_list": ["boq_wizard"],
    "supplier_dashboard": ["supplier_product_add"],
    "admin_sales": ["admin_pipeline"],
    "procurement_center": ["rfqs_list"],
    "procurement": ["procurement_catalog", "procurement_suppliers"],
    # The Generate step lands on the report page, and the register's View button
    # goes back to it -- so the flow really does walk this screen.
    "enterprise_lifecycle_documents": ["enterprise_document_view"],
    "capital_investment_landing": [
        "capital_investment_project", "capital_investment_digital_twin",
        "capital_investment_electrical_sld", "capital_investment_funding",
    ],
    # The wizard flow walks every numbered step screen.
    "capital_investment_project": [f"capital_investment_step{n}" for n in range(2, 15)],
    "capital_investment_digital_twin": ["capital_investment_electrical_sld",
                                       "capital_investment_equipment_layout"],
    # The reports flow walks these four; the rest are drafted.
    "report_pv": ["report_energy", "report_cable", "report_boq", "report_economic"],
    "project_results": ["report_pv"],
    # Enterprise Programme. Each entry below is a real nav() step in that flow:
    # home -> /enterprise/templates -> /enterprise/members, and
    # programme_detail -> .../design. Nothing is listed here that the flow does not walk.
    "enterprise_home": ["enterprise_templates", "enterprise_members"],
    "enterprise_templates": ["enterprise_template_new"],
    "enterprise_programme_detail": ["enterprise_design"],
    "enterprise_priority_list": ["enterprise_qualify_site"],
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
        "Quick Start — Create Your First Design", "Dashboard",
        "The 3-minute path from an empty dashboard to a fully sized solar design. "
        "The cursor leads and the tour walks onto the New Project screen for you.",
        [
            step("Your dashboard", "Every design you create is listed here with its status.",
                 "Welcome to SolarPro. This is your dashboard — every solar design you create "
                 "appears here with its status.",
                 target=".solar-card", screen="Dashboard"),
            step("Where you start a design", "Residential, commercial and industrial PV all start here.",
                 "To begin a new design you use Create Standard Project. Watch the cursor move to it.",
                 target='a[href="/project/new"], a[href*="project/new"]', screen="Dashboard"),
            nav("Open the New Project screen", "The tour now walks onto the design form.",
                "Let us open it — the tour will now take you onto the New Project screen.",
                href_from='a[href="/project/new"], a[href*="project/new"]', screen="Dashboard"),
            step("Name the design", "Every design starts with a memorable name.",
                 "On this new screen we start by naming the design — for example, "
                 "Accra Rooftop 25 kilowatt-peak. The cursor is typing it for you now.",
                 target='input[name="name"]', action="typeText",
                 type_text="Accra Rooftop 25 kWp", screen="New project"),
            step("File it in a folder", "Folders keep your growing list of designs organised.",
                 "Next we file it in a folder so it is easy to find again later.",
                 target='input[name="folder"]', screen="New project"),
            step("Create and continue", "Creating the project opens the globe to set your site.",
                 "Now we create the project. This opens the globe where you pick your site — that "
                 "fixes your sun hours, temperature and tariff. From there you add your loads, and the "
                 "engine sizes the array, battery, inverter and cables, with twenty-five-year economics, "
                 "all ready as PDF reports. That is the whole quick start.",
                 target='button[type="submit"]', screen="New project"),
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
            nav("Equipment general arrangement", "The same equipment, drawn to scale in plan.",
                "The outputs rail also carries the equipment general-arrangement drawing.",
                href_from='a[href*="/equipment-layout"]', screen="Digital twin"),
            step("The GA drawing", "Rooms, clearances and equipment, to scale.",
                 "Each room is drawn to scale with its equipment and working clearances.",
                 target='svg[aria-label$="equipment general arrangement"]',
                 duration=1400, screen="Equipment layout"),
            nav("The single-line diagram", "The electrical view of the same plant.",
                "The GA drawing links on to the electrical single-line diagram.",
                href_from='a[href*="/electrical-sld"]', screen="Equipment layout"),
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
    # --- backlog scenarios (2026-07-11) spliced ---

    # ---------------------------------------------------------------- BOQ family
    "boq_project_overview": (
        "BOQ Project", "BOQ",
        "The home of a building-services BOQ project: its buildings, cost roll-up and exports.",
        [
            step("Project buildings", "Every building in this BOQ project is listed here.",
                 "This is your BOQ project. Each building you add appears here with its cost.",
                 target=".solar-card, .card, table", screen="BOQ project"),
            step("Add a building", "A BOQ is built building by building, floor by floor.",
                 "Add a building to start pricing its floors and services.",
                 target='a[href*="/buildings/new"], .btn-primary', screen="BOQ project"),
            step("Cost plan and summary", "The roll-up totals every building and floor.",
                 "The cost plan and summary roll every floor and building into one total.",
                 target='a[href*="/cost-plan"], a[href*="/summary"]', screen="BOQ project"),
        ],
    ),
    "boq_project_edit": (
        "Edit BOQ Project", "BOQ",
        "Rename the project, change its client and currency, then save.",
        [
            step("Project details", "Name, client and currency drive every printed deliverable.",
                 "Edit the project name, client and currency here.",
                 target="form, .solar-card", screen="Edit project"),
            step("Currency", "The currency shows on every bill and export.",
                 "The currency you set flows onto every bill of quantities and export.",
                 target='select[name*="currency"], input[name*="currency"]', screen="Edit project"),
            step("Save changes", "Saved details apply across the whole project.",
                 "Save. Your changes apply across the whole project immediately.",
                 target='button[type="submit"], .btn-primary', screen="Edit project"),
        ],
    ),
    "boq_project_summary": (
        "BOQ Project Summary", "BOQ",
        "The campus-level roll-up: every building and floor totalled in one place.",
        [
            step("Campus total", "Every building's cost, summed for the project.",
                 "This summary rolls up every building into the project total.",
                 target=".solar-card, table, .card", screen="Summary"),
            step("Per-building breakdown", "Drill from the total into any building.",
                 "Each building's contribution is listed so you can drill into it.",
                 target="table, .solar-card", screen="Summary"),
            step("Export", "The summary prints as a client-ready cost document.",
                 "Export the summary as a client-ready cost document.",
                 target='a[href*="export"], a[href$=".pdf"], .btn-primary', screen="Summary"),
        ],
    ),
    "boq_project_boq": (
        "Project BOQ", "BOQ",
        "The consolidated bill of quantities for the whole project, ready to export.",
        [
            step("Consolidated BOQ", "Every priced item across every building and floor.",
                 "This is the consolidated bill of quantities for the whole project.",
                 target="table, .solar-card", screen="Project BOQ"),
            step("Compliance review", "Missing spec fields and prices are flagged.",
                 "The compliance panel flags any item missing a spec field, price or supplier.",
                 target=".alert, .no-print, .card", screen="Project BOQ"),
            step("Export to Excel or PDF", "The deliverable your client and QS receive.",
                 "Export the BOQ to Excel or PDF for your client and quantity surveyor.",
                 target='a[href$=".xlsx"], a[href$=".pdf"], .btn-primary', screen="Project BOQ"),
        ],
    ),
    "boq_cost_plan": (
        "Cost Plan", "BOQ",
        "An elemental cost plan: the project's spend grouped by building and bill.",
        [
            step("Elemental cost plan", "Spend grouped by building, floor and bill.",
                 "The cost plan groups the project's spend by building, floor and bill.",
                 target="table, .solar-card, .card", screen="Cost plan"),
            step("Building contributions", "See which building drives the cost.",
                 "Each building's share of the cost is shown so you can see the cost drivers.",
                 target="table, .solar-card", screen="Cost plan"),
            step("Export the deck", "The cost plan prints as a decision deck.",
                 "Export the cost plan as a decision-ready deck.",
                 target='a[href*="export"], a[href$=".pdf"], .btn-primary', screen="Cost plan"),
        ],
    ),
    "boq_building_new": (
        "Add a Building", "BOQ",
        "Name the building and set its floors so its bills can be raised.",
        [
            step("Building name", "Each building is priced on its own.",
                 "Name the building. Each building is priced separately.",
                 target='input[name="name"], form input[type="text"]',
                 action="typeText", type_text="Block A", screen="New building"),
            step("Floors", "Floors carry the service bills you will price.",
                 "Set the floors. Each floor carries the service bills you will price.",
                 target='input[name*="floor"], form', screen="New building"),
            step("Create the building", "The next screen lets you add its floors and bills.",
                 "Create the building, then add its floors and service bills.",
                 target='button[type="submit"], .btn-primary', screen="New building"),
        ],
    ),
    "boq_building_view": (
        "Building", "BOQ",
        "A building's floors, each with its own set of priced service bills.",
        [
            step("Floors", "Every floor of this building is listed here.",
                 "This building's floors are listed here, each priced on its own.",
                 target=".solar-card, .card, table", screen="Building"),
            step("Open a floor", "A floor holds the bills for each service.",
                 "Open a floor to raise and price its service bills.",
                 target='a[href*="/floors/"], .btn-primary', screen="Building"),
            step("Building summary", "The floors roll up into a building total.",
                 "The building summary rolls every floor into one total.",
                 target='a[href*="/summary"]', screen="Building"),
        ],
    ),
    "boq_building_summary": (
        "Building Summary", "BOQ",
        "Every floor of a building, totalled into the building's cost.",
        [
            step("Floor totals", "Each floor's priced bills, summed.",
                 "This summary totals every floor of the building.",
                 target="table, .solar-card", screen="Building summary"),
            step("Building total", "The figure that feeds the project roll-up.",
                 "The building total feeds straight into the project cost plan.",
                 target=".solar-card, tfoot, .card", screen="Building summary"),
            step("Export", "The building summary prints for the file.",
                 "Export the building summary for your project file.",
                 target='a[href*="export"], a[href$=".pdf"], .btn-primary', screen="Building summary"),
        ],
    ),
    "boq_floor_view": (
        "Floor", "BOQ",
        "A floor's service bills — the working surface where quantities and rates meet.",
        [
            step("Service bills", "Each bill covers one service, section by section.",
                 "This floor's service bills are listed here, each covering one service.",
                 target=".solar-card, .card, table", screen="Floor"),
            step("Set up a section", "A section groups related BOQ items.",
                 "Set up a section to start adding related BOQ items.",
                 target='a[href*="/section/new"], .btn-primary', screen="Floor"),
            step("Generate and review", "The floor BOQ compiles every section's items.",
                 "Generate the floor BOQ to compile every section into one reviewable bill.",
                 target='a[href*="/boq"], .btn-warning', screen="Floor"),
        ],
    ),
    "boq_floor_summary": (
        "Floor Summary", "BOQ",
        "Every section of a floor, totalled into the floor's cost.",
        [
            step("Section totals", "Each section's items, priced and summed.",
                 "This summary totals every section on the floor.",
                 target="table, .solar-card", screen="Floor summary"),
            step("Floor total", "The number that rolls into the building.",
                 "The floor total rolls up into the building summary.",
                 target=".solar-card, tfoot", screen="Floor summary"),
            step("Export", "The floor summary prints for the record.",
                 "Export the floor summary for the record.",
                 target='a[href*="export"], a[href$=".pdf"], .btn-primary', screen="Floor summary"),
        ],
    ),
    "boq_floor_boq_review": (
        "Floor BOQ Review", "BOQ",
        "The compiled floor bill with a compliance check before you export it.",
        [
            step("The compiled BOQ", "Every section's items in one priced bill.",
                 "Here is the floor's compiled bill of quantities, section by section.",
                 target="table, .solar-card", screen="Floor BOQ"),
            step("Compliance findings", "Missing specs, prices and suppliers are flagged.",
                 "The compliance review flags any item missing a spec, price or supplier.",
                 target=".alert, .no-print, .card", screen="Floor BOQ"),
            step("Export", "Export the compliant floor bill.",
                 "Export the floor bill once the findings are clear.",
                 target='a[href$=".xlsx"], a[href$=".pdf"], .btn-primary', screen="Floor BOQ"),
        ],
    ),
    "boq_floor_item_edit": (
        "Edit BOQ Item", "BOQ",
        "Adjust one line's description, quantity, unit and rate.",
        [
            step("Item description", "The wording that appears on the printed bill.",
                 "Edit the item description exactly as it should read on the bill.",
                 target='input[name*="desc"], textarea, form', screen="Edit item"),
            step("Quantity and rate", "Quantity times rate gives the line total.",
                 "Set the quantity and rate. The line total is quantity times rate.",
                 target='input[name*="qty"], input[name*="rate"]', screen="Edit item"),
            step("Save the line", "The section and floor totals update at once.",
                 "Save. The section and floor totals recalculate immediately.",
                 target='button[type="submit"], .btn-primary', screen="Edit item"),
        ],
    ),
    "boq_section_setup": (
        "New BOQ Section", "BOQ",
        "Create a section under a floor's bill to group related items.",
        [
            step("Section letter and name", "Sections are lettered A, B, C within a bill.",
                 "Give the section its letter and name. Sections are lettered within a bill.",
                 target='input[name*="section"], input[name*="letter"], form',
                 screen="New section"),
            step("Service", "The service decides which template items are offered.",
                 "Choose the service. It decides which template items you can add.",
                 target='select, input[name*="service"]', screen="New section"),
            step("Create the section", "The grid then lets you add and price items.",
                 "Create the section, then add and price its items in the grid.",
                 target='button[type="submit"], .btn-primary', screen="New section"),
        ],
    ),
    "boq_section_loop": (
        "BOQ Section", "BOQ",
        "One section's items, added from templates and priced line by line.",
        [
            step("Section items", "Each line carries a description, unit, quantity and rate.",
                 "This section's items are listed here, each with its unit, quantity and rate.",
                 target="table, .solar-card", screen="Section"),
            step("Open the grid", "The grid is the fast way to add many items.",
                 "Open the grid to add and price many items quickly.",
                 target='a[href*="/grid"], .btn-primary', screen="Section"),
            step("Section total", "The section rolls up into the floor bill.",
                 "The section total rolls up into the floor bill.",
                 target="tfoot, .solar-card", screen="Section"),
        ],
    ),
    "boq_section_grid": (
        "BOQ Section Grid", "BOQ",
        "A spreadsheet-style grid to add, quantify and rate a section's items fast.",
        [
            step("The grid", "Rows are items; columns are unit, quantity and rate.",
                 "This grid is the fast surface for a section: rows are items, columns price them.",
                 target="table, .solar-card", screen="Grid"),
            step("Fill quantities and rates", "Line totals compute as you type.",
                 "Fill in quantities and rates. Each line total computes as you type.",
                 target='input[type="number"], td input', screen="Grid"),
            step("Save the grid", "The section and floor totals update together.",
                 "Save the grid. The section and floor totals update together.",
                 target='button[type="submit"], .btn-primary, .btn-success', screen="Grid"),
        ],
    ),
    # ---------------------------------------------------------------- BOM / market / supplier
    "boms_view": (
        "Bill of Materials", "Marketplace",
        "A BOM's line items, priced from the marketplace, ready to become a BOQ.",
        [
            step("BOM items", "Each material with its quantity and marketplace price.",
                 "This bill of materials lists each item with its quantity and price.",
                 target="table, .solar-card", screen="BOM"),
            step("Rate build-up", "See how each rate is composed.",
                 "Open the rate build-up to see how each unit price is composed.",
                 target='a[href*="/rate-buildup"], .btn-primary', screen="BOM"),
            step("Turn it into a BOQ", "The BOM feeds the priced bill of quantities.",
                 "Convert the BOM into a bill of quantities for the client.",
                 target='a[href*="/boq"], .btn-warning', screen="BOM"),
        ],
    ),
    "boms_rate_buildup": (
        "Rate Build-Up", "Marketplace",
        "How each unit rate is composed: material, labour, overhead and markup.",
        [
            step("Rate components", "Material, labour, overhead and margin per unit.",
                 "Each rate is built from material, labour, overhead and margin.",
                 target="table, .solar-card", screen="Rate build-up"),
            step("Adjust the markup", "The markup sets your selling rate.",
                 "Adjust the markup to set your selling rate over cost.",
                 target='input[name*="markup"], input[type="number"]', screen="Rate build-up"),
            step("Apply the rates", "The composed rates flow onto the BOM and BOQ.",
                 "Apply the rates. They flow onto the bill of materials and the BOQ.",
                 target='button[type="submit"], .btn-primary', screen="Rate build-up"),
        ],
    ),
    "boms_basic_prices": (
        "Basic Prices", "Marketplace",
        "The base material prices behind the BOM, sourced from the marketplace.",
        [
            step("Base prices", "The raw material cost before labour and markup.",
                 "These are the base material prices behind the bill, before labour and markup.",
                 target="table, .solar-card", screen="Basic prices"),
            step("Source from the marketplace", "Live supplier prices keep the BOM current.",
                 "Prices are sourced from the marketplace so the bill stays current.",
                 target='a[href*="/marketplace"], .card', screen="Basic prices"),
            step("Feed the rate build-up", "Base prices are the first layer of every rate.",
                 "The base prices become the first layer of every rate build-up.",
                 target='a[href*="/rate-buildup"], .btn-primary', screen="Basic prices"),
        ],
    ),
    "marketplace_product_docs_listing": (
        "Product Documents", "Marketplace",
        "The datasheets, certificates and manuals attached to a marketplace product.",
        [
            step("Document list", "Datasheets, certificates and manuals for the product.",
                 "Every document attached to this product is listed here.",
                 target="table, .solar-card, .list-group", screen="Product docs"),
            step("Open a datasheet", "Specs you can cite in a BOQ compliance check.",
                 "Open a datasheet to read the specs you cite in a compliance check.",
                 target='a[target="_blank"], a[href*="doc"]', screen="Product docs"),
            step("Back to the product", "Return to add the product to a BOM or RFQ.",
                 "Return to the product to add it to a bill of materials or an RFQ.",
                 target='a[href*="/marketplace/product/"], .btn-primary', screen="Product docs"),
        ],
    ),
    "rfqs_view": (
        "Request for Quotation", "Procurement",
        "One RFQ: the items sent to suppliers and the quotes coming back.",
        [
            step("RFQ items", "The materials and quantities you asked suppliers to price.",
                 "This RFQ lists the items and quantities you sent out for pricing.",
                 target="table, .solar-card", screen="RFQ"),
            step("Supplier responses", "Compare quotes as suppliers reply.",
                 "Supplier responses appear here so you can compare quotes side by side.",
                 target=".solar-card, table, .card", screen="RFQ"),
            step("Award or add to BOQ", "Turn the best quote into a purchase.",
                 "Take the best quote onto your bill of quantities or procurement list.",
                 target='.btn-primary, .btn-success', screen="RFQ"),
        ],
    ),
    "supplier_products": (
        "My Products", "Supplier",
        "A supplier's catalogue: the products you list for buyers to price and RFQ.",
        [
            step("Your catalogue", "Every product you have listed, with its price and status.",
                 "This is your product catalogue: everything you have listed for buyers.",
                 target="table, .solar-card", screen="My products"),
            step("Add a product", "Listed products appear in buyer searches and RFQs.",
                 "Add a product. Listed products appear in buyer searches and RFQs.",
                 target='a[href*="/products/add"], a[href*="/upload"], .btn-primary',
                 screen="My products"),
            step("Edit a listing", "Keep prices and specs current so buyers trust them.",
                 "Edit a listing to keep its price and specs current.",
                 target='a[href*="/edit"], .btn-outline-secondary', screen="My products"),
        ],
    ),
    "supplier_product_edit": (
        "Edit Product", "Supplier",
        "Update one product's price, specs and documents so buyers see it correctly.",
        [
            step("Price and specs", "The fields buyers filter and compare on.",
                 "Update the price and the technical specs buyers filter and compare on.",
                 target="form, .solar-card", screen="Edit product"),
            step("Required spec fields", "A complete spec passes the BOQ compliance check.",
                 "Fill the required spec fields so the product passes buyers' compliance checks.",
                 target='input, select, textarea', screen="Edit product"),
            step("Save the listing", "Buyers see the update immediately.",
                 "Save. Buyers see the updated listing immediately.",
                 target='button[type="submit"], .btn-primary', screen="Edit product"),
        ],
    ),
    "supplier_upload": (
        "Upload Products", "Supplier",
        "Add products one by one, or bulk-upload a spreadsheet, into your catalogue.",
        [
            step("Category and subcategory", "The category decides the required spec fields.",
                 "Pick the category and subcategory. They set the required spec fields.",
                 target='select[name*="cat"], form', screen="Upload"),
            step("Product details", "Name, price, unit and specs make a complete listing.",
                 "Enter the product name, price, unit and specs for a complete listing.",
                 target='input[name*="name"], form input[type="text"]',
                 action="typeText", type_text="LV Cable 4mm2", screen="Upload"),
            step("Publish to the catalogue", "Published products enter buyer searches.",
                 "Publish. The product enters buyer searches and RFQs.",
                 target='button[type="submit"], .btn-primary', screen="Upload"),
        ],
    ),
    "supplier_register": (
        "Become a Supplier", "Supplier",
        "Register a supplier account to list products and receive RFQs.",
        [
            step("Company details", "Buyers see your company name and contact.",
                 "Start with your company name and contact details.",
                 target='input[name*="company"], input[name="name"], form',
                 action="typeText", type_text="Accra Solar Supplies", screen="Register"),
            step("Contact and coverage", "Where you supply decides which buyers see you.",
                 "Set your contact and the regions you supply. It decides which buyers see you.",
                 target='input[name*="email"], input[name*="phone"], select', screen="Register"),
            step("Create the account", "You then reach your supplier dashboard.",
                 "Create the account to reach your supplier dashboard and list products.",
                 target='button[type="submit"], .btn-primary', screen="Register"),
        ],
    ),
    "supplier_rfqs_respond": (
        "Respond to an RFQ", "Supplier",
        "Price a buyer's RFQ line by line and send your quote back.",
        [
            step("The buyer's items", "What the buyer asked you to price, with quantities.",
                 "This RFQ shows exactly what the buyer asked you to price.",
                 target="table, .solar-card", screen="Respond"),
            step("Enter your prices", "Your unit prices become the quote the buyer compares.",
                 "Enter your unit prices. They become the quote the buyer compares.",
                 target='input[type="number"], td input', screen="Respond"),
            step("Send the quote", "The buyer sees your response in their RFQ.",
                 "Send the quote. It appears in the buyer's RFQ immediately.",
                 target='button[type="submit"], .btn-success, .btn-primary', screen="Respond"),
        ],
    ),
    # ---------------------------------------------------------------- reports
    "report_circuits": (
        "Circuit Schedule Report", "Reports",
        "The final-circuit schedule: every circuit, its cable, breaker and load.",
        [
            step("Circuit schedule", "Each circuit with its cable size, breaker and load.",
                 "This report schedules every final circuit with its cable, breaker and load.",
                 target="table, .report-title, .solar-card", screen="Circuits"),
            step("Cable and protection", "Sized from the design's loads and lengths.",
                 "Cable sizes and protection are sized from the design's loads and runs.",
                 target="table", screen="Circuits"),
            step("Print or download", "The schedule prints as a signed-off document.",
                 "Print or download the circuit schedule for the installation file.",
                 target='.btn-primary, a[href$=".pdf"], .no-print', screen="Circuits"),
        ],
    ),
    "report_inspection": (
        "Inspection Report", "Reports",
        "The commissioning inspection record for the installed system.",
        [
            step("Inspection record", "The checks carried out at commissioning.",
                 "This report records the inspection checks carried out at commissioning.",
                 target=".report-title, table, .solar-card", screen="Inspection"),
            step("Results and notes", "Pass, fail and remedial notes per check.",
                 "Each check carries its result and any remedial note.",
                 target="table", screen="Inspection"),
            step("Download", "The signed inspection report goes in the handover pack.",
                 "Download the inspection report for the handover pack.",
                 target='.btn-primary, a[href$=".pdf"], .no-print', screen="Inspection"),
        ],
    ),
    "report_installation": (
        "Installation Report", "Reports",
        "The installation method, mounting and hardware for the design.",
        [
            step("Installation method", "Mounting type sets the hardware and drawings.",
                 "This report sets out the installation method for the chosen mounting type.",
                 target=".report-title, .solar-card, table", screen="Installation"),
            step("Hardware schedule", "Rails, clamps, posts and earthing for the array.",
                 "The hardware schedule lists rails, clamps, posts and earthing.",
                 target="table", screen="Installation"),
            step("Open the drawings", "The drawings show the layout to scale.",
                 "Open the installation drawings to see the layout to scale.",
                 target='a[href*="/drawings"], .btn-primary', screen="Installation"),
        ],
    ),
    "report_installation_drawings": (
        "Installation Drawings", "Reports",
        "Scaled layout and mounting drawings for the installation crew.",
        [
            step("Layout drawing", "The array laid out to scale on the roof or ground.",
                 "This drawing lays the array out to scale for the installation crew.",
                 target="svg, canvas, .report-title, img", screen="Drawings"),
            step("Mounting detail", "Fixings and footings suited to the mounting type.",
                 "The mounting detail shows the fixings and footings for this mounting type.",
                 target="svg, canvas, .solar-card", screen="Drawings"),
            step("Print to scale", "The crew works from the printed sheet.",
                 "Print the drawings to scale for the crew on site.",
                 target='.btn-primary, .no-print', screen="Drawings"),
        ],
    ),
    "report_proposal": (
        "Proposal Report", "Reports",
        "The client-facing proposal: system, savings and price in one document.",
        [
            step("The proposal", "System summary, savings and price for the client.",
                 "This is the client proposal: the system, its savings and its price.",
                 target=".report-title, .solar-card", screen="Proposal"),
            step("Savings and payback", "The numbers that win the decision.",
                 "The savings and payback figures are the numbers that win the decision.",
                 target="table, .kpi-card, .solar-card", screen="Proposal"),
            step("Send or download", "Deliver the proposal to your client.",
                 "Download or send the proposal straight to your client.",
                 target='.btn-primary, a[href$=".pdf"], .no-print', screen="Proposal"),
        ],
    ),
    "report_shading": (
        "Shading Report", "Reports",
        "The shading analysis: how nearby obstructions cut the array's yield.",
        [
            step("Shading analysis", "How buildings and objects shade the array.",
                 "This report analyses how nearby obstructions shade the array.",
                 target=".report-title, svg, canvas, .solar-card", screen="Shading"),
            step("Yield impact", "The energy lost to shading, month by month.",
                 "The yield impact shows the energy lost to shading through the year.",
                 target="table, .solar-card", screen="Shading"),
            step("Download", "The shading study supports the yield guarantee.",
                 "Download the shading study to support your yield guarantee.",
                 target='.btn-primary, a[href$=".pdf"], .no-print', screen="Shading"),
        ],
    ),
    "inspection_form": (
        "Site Inspection", "Solar Design",
        "Capture the on-site inspection that grounds the design in real conditions.",
        [
            step("Site checks", "Roof, orientation, shading and electrical intake.",
                 "Record the site checks: roof, orientation, shading and electrical intake.",
                 target="form, .solar-card", screen="Inspection"),
            step("Photos and notes", "Evidence the design and the client can rely on.",
                 "Attach photos and notes as evidence for the design and the client.",
                 target='input[type="file"], textarea', screen="Inspection"),
            step("Save the inspection", "It feeds the inspection report.",
                 "Save the inspection. It feeds straight into the inspection report.",
                 target='button[type="submit"], .btn-primary', screen="Inspection"),
        ],
    ),
    # ---------------------------------------------------------------- project sub-pages
    "project_funding": (
        "Project Funding", "Funding",
        "Package a design for finance and send it to a financial institution.",
        [
            step("Funding overview", "The design's cost, savings and financing need.",
                 "This is the funding view for the design: its cost, savings and financing need.",
                 target=".solar-card, .kpi-card, table", screen="Funding"),
            step("Generate the funding package", "A lender-ready pack of the numbers.",
                 "Generate the funding package: a lender-ready pack of the project's numbers.",
                 target='.btn-primary, a[href*="funding"]', screen="Funding"),
            step("Choose an institution", "Send the package to a financial institution.",
                 "Choose a financial institution and submit the package for review.",
                 target='select, .btn-success', screen="Funding"),
        ],
    ),
    "project_procurement": (
        "Project Procurement", "Procurement",
        "Turn a design's bill of materials into a buying list and supplier RFQs.",
        [
            step("Procurement list", "Every material the design needs to be built.",
                 "This is the procurement list: every material the design needs.",
                 target="table, .solar-card", screen="Procurement"),
            step("Add to RFQ", "Send items to suppliers to price.",
                 "Add items to an RFQ to send them to suppliers for pricing.",
                 target='.btn-primary, a[href*="rfq"]', screen="Procurement"),
            step("Track the buy", "Follow items from quote to order.",
                 "Track each item from quote through to order.",
                 target=".solar-card, table", screen="Procurement"),
        ],
    ),
    # ---------------------------------------------------------------- funding / growth
    "funding_application_review": (
        "Funding Application Review", "Funding",
        "The institution's workspace to review one applicant's project and decide.",
        [
            step("Applicant's project", "The design, its reports and its numbers.",
                 "Review the applicant's project: the design, its reports and its numbers.",
                 target=".solar-card, table, .card", screen="Review"),
            step("The reports", "Read the engineering and financial reports before deciding.",
                 "Open the reports to read the engineering and financial case.",
                 target='a[href*="report"], .btn-primary', screen="Review"),
            step("Decide", "Email the applicant and record your decision.",
                 "Email the applicant and record your decision in principle.",
                 target='.btn-success, .btn-primary', screen="Review"),
        ],
    ),
    "growth_proposal_beautifier": (
        "Beautified Proposal", "Growth",
        "A polished, shareable version of the proposal for prospects.",
        [
            step("Polished proposal", "The proposal, styled for a prospect to read.",
                 "This is the proposal, styled and polished for a prospect to read.",
                 target=".solar-card, .report-title", screen="Proposal"),
            step("The story", "System, savings and next step, laid out to persuade.",
                 "It lays out the system, the savings and the next step to persuade.",
                 target="table, .kpi-card, .solar-card", screen="Proposal"),
            step("Share it", "Send a link the prospect can open anywhere.",
                 "Share a link the prospect can open on any device.",
                 target='.btn-primary, a[href*="/s/"], a[href*="/share/"]', screen="Proposal"),
        ],
    ),
    "growth_public_preview": (
        "Public Proposal Preview", "Growth",
        "What a prospect sees when they open your shared proposal link.",
        [
            step("The public view", "The proposal as your prospect sees it.",
                 "This is exactly what your prospect sees when they open the shared link.",
                 target=".solar-card, .report-title", screen="Preview"),
            step("Key numbers", "Savings and payback, front and centre.",
                 "The key numbers, savings and payback, sit front and centre.",
                 target=".kpi-card, table, .solar-card", screen="Preview"),
            step("Call to action", "The prospect can reply or request a call.",
                 "The call to action lets the prospect reply or request a call.",
                 target='.btn-primary, a[href*="contact"], form', screen="Preview"),
        ],
    ),
    "growth_share_composer": (
        "Share a Proposal", "Growth",
        "Compose the shareable link and message for a project proposal.",
        [
            step("Compose the share", "A public link plus the message that frames it.",
                 "Compose the share: a public link and the message that frames it.",
                 target="form, .solar-card", screen="Share"),
            step("Personal message", "A line to the prospect lifts the open rate.",
                 "Add a personal line to the prospect. It lifts the open rate.",
                 target='textarea, input[type="text"]', screen="Share"),
            step("Create the link", "The prospect opens the public preview.",
                 "Create the link. The prospect opens the public proposal preview.",
                 target='button[type="submit"], .btn-primary', screen="Share"),
        ],
    ),
    # ---------------------------------------------------------------- misc
    "account_invoice": (
        "Invoice", "Account",
        "A single billing invoice for your subscription, ready to download.",
        [
            step("Invoice detail", "The plan, period and amount billed.",
                 "This invoice shows the plan, period and amount billed.",
                 target=".solar-card, table, .card", screen="Invoice"),
            step("Billing period", "The dates this charge covers.",
                 "The billing period shows exactly what dates this charge covers.",
                 target="table, .solar-card", screen="Invoice"),
            step("Download", "Keep the invoice for your records.",
                 "Download the invoice for your accounting records.",
                 target='.btn-primary, a[href$=".pdf"], .no-print', screen="Invoice"),
        ],
    ),
    "folder_detail": (
        "Folder", "Projects",
        "One folder's projects, grouped so you can find related designs fast.",
        [
            step("Folder contents", "Every project filed in this folder.",
                 "This folder groups related designs so you can find them fast.",
                 target=".solar-card, table, .card", screen="Folder"),
            step("Open a project", "Jump straight into any design.",
                 "Open any project to jump straight into its design.",
                 target='a[href*="/project/"], .solar-card', screen="Folder"),
            step("Back to all folders", "The folders index lists every folder.",
                 "Return to the folders index to see every folder you have.",
                 target='a[href*="/folder"], nav', screen="Folder"),
        ],
    ),
    "news_detail": (
        "News Article", "News",
        "A single news or update post from the SolarPro feed.",
        [
            step("The article", "The full post, headline and body.",
                 "This is the full news article, headline and body.",
                 target=".solar-card, article, .report-title", screen="Article"),
            step("Related updates", "More posts from the feed.",
                 "Related updates link on from here so you can keep reading.",
                 target='a[href*="/news"], .card', screen="Article"),
            step("Back to the feed", "The news index lists every post.",
                 "Return to the news feed to see every post.",
                 target='a[href="/news"], nav', screen="Article"),
        ],
    ),
    "ticket_detail": (
        "Support Ticket", "Support",
        "One support ticket: the conversation and its status.",
        [
            step("The conversation", "Your message and every reply, in order.",
                 "This ticket shows your message and every reply in order.",
                 target=".solar-card, .card, table", screen="Ticket"),
            step("Add a reply", "Keep the thread going until it is resolved.",
                 "Add a reply to keep the thread going until it is resolved.",
                 target='textarea, input[name*="message"]', screen="Ticket"),
            step("Status", "Open, pending or resolved, tracked here.",
                 "The status tracks whether the ticket is open, pending or resolved.",
                 target=".badge, .solar-card", screen="Ticket"),
        ],
    ),
    "upgrade_success": (
        "Upgrade Complete", "Account",
        "Confirmation that your plan upgrade went through, and what unlocks next.",
        [
            step("Payment confirmed", "Your upgrade is active on the account.",
                 "Your payment is confirmed and the upgrade is active on your account.",
                 target=".solar-card, .alert-success, .card", screen="Success"),
            step("What unlocks", "The features your new plan opens up.",
                 "Here is what your new plan unlocks across the platform.",
                 target=".solar-card, table", screen="Success"),
            step("Start using it", "Head to the dashboard and put it to work.",
                 "Head back to the dashboard and put the new plan to work.",
                 target='a[href="/dashboard"], .btn-primary', screen="Success"),
        ],
    ),
    "support_user_guide": (
        "User Guide", "Support",
        "The end-to-end user guide: how to run the platform, page by page.",
        [
            step("The guide", "How every module works, in one place.",
                 "This user guide explains how every module of the platform works.",
                 target=".solar-card, .report-title, article", screen="User guide"),
            step("Read it aloud", "The guide can be narrated by your browser.",
                 "The guide can be read aloud using your browser's voice.",
                 target='.btn-primary, .no-print, button', screen="User guide"),
            step("Every page also teaches itself", "Help & Tutorial runs on each page.",
                 "And on any page, Help and Tutorial runs a guided tour of that screen.",
                 target=".sp-tut-launcher", screen="User guide", dynamic=True),
        ],
    ),
    "capital_investment_demo": (
        "Generation Station Demo", "Generation Station",
        "A ready-made utility-scale project you can explore without building one.",
        [
            step("A worked example", "A complete Generation Station design to explore.",
                 "This is a worked utility-scale example you can explore without building one.",
                 target=".solar-card, .card, table", screen="Demo"),
            step("Walk the wizard", "See the 14 steps on a real project.",
                 "Walk the fourteen wizard steps as they appear on a real project.",
                 target='a[href*="/step"], .btn-primary', screen="Demo"),
            step("Start your own", "When ready, create your own Generation Station.",
                 "When you are ready, create your own Generation Station design.",
                 target='a[href="/large-scale-solar"], a[href*="/new"], .btn-warning', screen="Demo"),
        ],
    ),

    # --- Enterprise Programme (rebuild slices 1-7, live 2026-07-13) -------------
    #
    # Every nav() below follows a link that REALLY EXISTS on the page it starts from
    # (checked against templates/enterprise_programme/*.html). A nav whose anchor is not
    # on the current screen does not fail loudly -- the engine just shows the fallback and
    # walks on -- so a plausible-looking chain can silently teach nothing. The chains here
    # are: home -> templates -> members, and programme_detail -> design.
    "enterprise_home": (
        "Enterprise Programme", "Enterprise",
        "Run a national programme: one organisation, one design, hundreds of sites.",
        [
            step("Your organisations", "A programme belongs to an organisation, not a person.",
                 "An enterprise programme belongs to an organisation, not to one person. "
                 "Everyone who works on it is a member of that organisation.",
                 target=".ent-page .card, .card", screen="Enterprise"),
            step("Switch organisation", "You may belong to several. This chooses the active one.",
                 "If you belong to more than one organisation, this chooses which one you are "
                 "acting in. Everything on the page is scoped to it.",
                 target='select[name="tenant_id"], .form-select', screen="Enterprise"),
            step("Your programmes", "Each one carries 16 phases and 14 stage gates.",
                 "Each programme carries sixteen lifecycle phases and fourteen stage gates. "
                 "It opens at Phase 1, Concept.",
                 target=".table, table", screen="Enterprise"),
            step("Register a programme", "Name it, choose its design path, name its sponsor.",
                 "To start one, register it here. You name it, choose its design path, and "
                 "name a sponsor from your own members.",
                 target='a[href*="/enterprise/programmes/new"], .btn-warning',
                 screen="Enterprise"),
            nav("The template engine", "Templates define what every site gets.",
                "First, the template engine. A template defines what every site in the "
                "programme receives.",
                href="/enterprise/templates", screen="Enterprise"),
            step("Versioned, and approved", "A template is used only once approved.",
                 "Templates are versioned. A version is drafted, submitted, and approved "
                 "before any programme is allowed to build from it.",
                 target=".table, table, .card", screen="Templates"),
            nav("Who may do what", "Roles are granted here, and revoked here.",
                "Authority is granted on the members screen. The gates ask for a named role, "
                "not merely a permission.",
                href="/enterprise/members", screen="Templates"),
            step("Members and roles", "Each role is a separate, revocable row.",
                 "Each role is a separate row you can take back. When the ministry hires a real "
                 "technical director, you hand that role over and stop holding it.",
                 target=".table, table", screen="Members"),
        ],
    ),
    "enterprise_onboarding": (
        "Create an organisation", "Enterprise",
        "Register the ministry, agency or utility the programme belongs to.",
        [
            step("The legal entity", "This is the organisation, not your personal workspace.",
                 "This registers a real organisation. It is separate from your personal "
                 "workspace, and other people can be invited into it.",
                 target="form, .card", screen="Onboarding"),
            step("Name and type", "Ministry, agency, utility, NGO, donor.",
                 "Give its legal name and choose what kind of body it is.",
                 target='input[name="legal_name"], input, select', screen="Onboarding"),
            step("You become its owner", "And you are granted the roles to actually run it.",
                 "Creating it makes you its owner, and grants you the operational roles needed "
                 "to run a programme single-handed until you have colleagues to hand them to.",
                 target='button[type="submit"], .btn-warning', screen="Onboarding"),
        ],
    ),
    "enterprise_programme_new": (
        "Register a programme", "Enterprise",
        "A programme is born at Phase 1 with all 16 phases and 14 gates seeded.",
        [
            step("Code and name", "The code is how the programme is referenced everywhere.",
                 "Give the programme a code and a name. The code is how it is referenced "
                 "everywhere else.",
                 target='input[name="code"], input[name="name"], input', screen="New programme"),
            step("The design path", "Standard rooftop, or a generation station.",
                 "Choose the design path. Standard builds a system at every site. Generation "
                 "station builds one plant that supplies them all.",
                 target='select[name="design_strategy"], select', screen="New programme"),
            step("The sponsor", "Chosen from your members. Never typed.",
                 "The sponsor is chosen from your organisation's own members. A sponsor who is "
                 "not in the organisation is not a sponsor.",
                 target='select[name="sponsor_user_id"], select', screen="New programme"),
            step("Register it", "It opens at Phase 1, Concept, awaiting Gate 1.",
                 "Register it, and it opens at Phase 1, Concept, with all fourteen gates "
                 "waiting.",
                 target='button[type="submit"], .btn-warning', screen="New programme"),
        ],
    ),
    "enterprise_programme_detail": (
        "The lifecycle command centre", "Enterprise",
        "16 phases, 14 stage gates, and the one design every site is built from.",
        [
            step("Where the programme stands", "Its phase, and the gate it is waiting on.",
                 "This is the command centre. It shows which of the sixteen phases the "
                 "programme is in, and which gate it is waiting on.",
                 target=".ent-page .card, .card", screen="Programme"),
            step("The 14 stage gates", "A gate needs a NAMED AUTHORITY, not just permission.",
                 "Each gate must be approved by a named authority. Holding a general approval "
                 "permission is deliberately not enough -- the gate asks for the role.",
                 target=".table, table, .badge", screen="Programme"),
            step("Lifecycle documents", "Generated from the programme, not guessed.",
                 "Each phase has its real activities. The documents are written from the "
                 "programme's own answers, not invented.",
                 target='a[href*="/lifecycle-documents"], a[href*="/documents"]',
                 screen="Programme"),
            nav("The reference design", "ONE design. Every site is an instance of it.",
                "Now the heart of it. A programme holds one reference design, and every site "
                "is an instance of that same design.",
                href_from='a[href*="/design"]', screen="Programme"),
            step("One design, scaled", "The BOQ is the same at every site.",
                 "Because every site is the same design, the bill of quantities is the same at "
                 "every site, and the funding requirement is that cost times the number of "
                 "sites.",
                 target=".card, table", screen="Design"),
        ],
    ),
    "enterprise_design": (
        "One design, every site", "Enterprise",
        "The programme's single reference design, instantiated at every location.",
        [
            step("The reference design", "Built once, from an approved template version.",
                 "The programme's reference design is built once, from a template version "
                 "somebody approved.",
                 target=".card, form", screen="Design"),
            # The Approve/Roll-out buttons only exist ONCE a design has been created; on a
            # fresh programme this screen is just the create form. The selector therefore
            # lists the real controls first and falls back to the form that is always there,
            # so the step lands on something in BOTH states rather than silently showing a
            # fallback message on the empty one.
            step("Approve it", "Nothing is rolled out from an unapproved design.",
                 "It must be approved before anything is rolled out. That approval is control "
                 "C04, and it is checked again on the worker, not only here.",
                 target=".btn-success, .btn-warning, form, .card", screen="Design"),
            step("Roll it out", "Every qualified site is built from this one design.",
                 "Rolling out queues the work. Every qualified site is then built as a copy of "
                 "this design -- not redesigned, copied.",
                 target='button, .btn', screen="Design"),
            step("The survey is evidence, not an input", "A site that differs raises a flag.",
                 "A site whose survey disagrees with the reference does not get resized. It "
                 "raises a variance flag for engineering. Otherwise you would have as many "
                 "different bills of quantities as you have sites.",
                 target=".card, .alert, table", screen="Design"),
        ],
    ),
    "enterprise_templates": (
        "Programme templates", "Enterprise",
        "Versioned packages that define what every site in a programme receives.",
        [
            step("Your templates", "One per beneficiary type: school, clinic, home.",
                 "A template defines the package a site receives. Typically one per kind of "
                 "beneficiary -- a school, a clinic, a household.",
                 target=".table, table, .card", screen="Templates"),
            nav("Create one", "Give it a code, a name and a beneficiary type.",
                "Let us create one.", href="/enterprise/templates/new", screen="Templates"),
            step("Code, name, type", "The code must be unique in your organisation.",
                 "Give it a code, a name, and the beneficiary type it serves. The code must be "
                 "unique within your organisation.",
                 target='input[name="code"], input, form', screen="New template"),
            step("It is born as Draft v1", "Drafts cannot be built from.",
                 "It is created with version one, in Draft. A draft cannot be built from -- it "
                 "is submitted, then approved, and only then published.",
                 target='button[type="submit"], .btn-warning', screen="New template"),
        ],
    ),
    "enterprise_template_detail": (
        "Template versions", "Enterprise",
        "Draft, submit, approve, publish -- and a frozen version can never change.",
        [
            step("The versions", "Each one is a separate, auditable package.",
                 "Every version of the template is a separate, auditable package.",
                 target=".table, table", screen="Template"),
            step("Fill it in", "The parameters every site inherits.",
                 "The parameters here are what every site built from this version inherits.",
                 target="form, textarea, input", screen="Template"),
            step("Submit for approval", "The author does not certify their own work.",
                 "Submit it for approval. Authoring and approving are separate authorities.",
                 target=".btn-warning, .btn-primary, button", screen="Template"),
            step("Approved, then frozen", "An approved version can never be edited again.",
                 "Once approved and published, the version is frozen. It can never be edited "
                 "again -- you raise a new version instead. That is what makes a programme "
                 "built two years ago still explicable.",
                 target=".badge, .table", screen="Template"),
        ],
    ),
    "enterprise_beneficiaries": (
        "The site register", "Enterprise",
        "Register sites by hand, or import hundreds from a spreadsheet.",
        [
            step("Every site in the programme", "Schools, clinics, homes -- the register.",
                 "This is the register of every site in the programme.",
                 target=".table, table", screen="Register"),
            step("Add one by hand", "For a single site.",
                 "A single site can be registered by hand.",
                 target='a[href*="/beneficiaries/new"], .btn-warning', screen="Register"),
            step("Or import a spreadsheet", "Hundreds of rows, in one upload.",
                 "But a real programme arrives as a spreadsheet. Upload it here.",
                 target='input[type="file"], form, a[href*="/import"]', screen="Register"),
            step("Nothing is written until you commit", "The upload is STAGED first.",
                 "The upload does not touch the register. It is staged, so you see exactly what "
                 "would be created -- duplicates caught, invalid rows rejected -- and nothing "
                 "is written until you commit it.",
                 target=".alert, .card, table", screen="Register"),
        ],
    ),
    "enterprise_priority_list": (
        "Which site first?", "Enterprise",
        "Score every site, and let the programme rank them honestly.",
        [
            step("The priority list", "Every site, ranked by its score.",
                 "With hundreds of sites and a finite budget, this ranks them.",
                 target=".table, table", screen="Priority"),
            step("Unscored is a QUESTION, not a zero", "An unscored site is not a bad site.",
                 "A site nobody has scored yet is shown as a question, never as a zero. A zero "
                 "would quietly send it to the bottom of the list and it would never be built.",
                 target="table, .badge, .text-muted", screen="Priority"),
            nav("Score a site", "The scorecard: access, roof, load, risk.",
                "Let us score one.", href_from='a[href*="/qualify"]', screen="Priority"),
            step("100 means NO risk", "Read the direction of the scale carefully.",
                 "Mind the direction of the risk scale. One hundred means no risk, not maximum "
                 "risk.",
                 target="form, .card, input", screen="Scorecard"),
            step("Scoring is not deciding", "The scorer proposes. Another person decides.",
                 "Scoring a site does not qualify it. Somebody else decides, on the evidence of "
                 "the score. In a one-person organisation that separation relaxes -- and the "
                 "audit record says so.",
                 target="button, .btn", screen="Scorecard"),
        ],
    ),
    "enterprise_members": (
        "Members and authority", "Enterprise",
        "Invite people, grant roles, and take them back.",
        [
            # The members screen is CARDS, not a table -- verified against the rendered DOM
            # by tests/enterprise_programme/test_enterprise_tutorial_selectors.py.
            step("Who is in the organisation", "And exactly what each of them may do.",
                 "Everyone in the organisation, and what each of them is authorised to do.",
                 target=".card, .card-body", screen="Members"),
            step("Invite someone", "By username or email.",
                 "Invite a colleague by username or email.",
                 target='input[name="identifier"], input, form', screen="Members"),
            step("Grant a role", "The gates ask for the ROLE, not the permission.",
                 "Grant them a role. The stage gates ask for a named role, so this is how "
                 "somebody becomes able to sign a gate.",
                 target='select[name="role_code"], select', screen="Members"),
            step("Revoking is real", "Take a role back and the authority goes with it.",
                 "Roles can be taken back, and the authority goes with them. Re-inviting "
                 "somebody who left starts them from nothing -- their old roles do not quietly "
                 "come back.",
                 target=".btn-outline-danger, .btn, button", screen="Members"),
        ],
    ),
    "enterprise_beneficiary_new": (
        "Register a site", "Enterprise",
        "Add one school, clinic or household to the programme's register.",
        [
            step("Identify the site", "A code, a name, and what kind of site it is.",
                 "Give the site a code and a name, and say what kind of site it is.",
                 target='input[name="code"], input[name="name"], input',
                 screen="New site"),
            step("Where it is", "Community, district, region.",
                 "Say where it is. The location is what the survey team will be sent to.",
                 target='input[name="community"], input, select', screen="New site"),
            step("Registered, not yet qualified", "Being on the register is not approval.",
                 "Registering a site does not qualify it. It must still be scored, and "
                 "somebody must still decide.",
                 target='button[type="submit"], .btn-warning', screen="New site"),
        ],
    ),
    "enterprise_beneficiary_detail": (
        "One site's record", "Enterprise",
        "Everything known about a single site: its score, its status, its project.",
        [
            step("The site", "Its identity and where it sits in the programme.",
                 "Everything the programme knows about this one site.",
                 target=".card, .ent-page", screen="Site"),
            step("Its qualification", "The score, and who decided on it.",
                 "Its qualification score, and the decision somebody took on the strength of "
                 "it.",
                 target="table, .badge, .card", screen="Site"),
            step("Its status", "Registered, qualified, or built.",
                 "And its status -- registered, qualified, or built. Moving a site forward is "
                 "an authorised act, and it is recorded against a name.",
                 target=".badge, button, .btn", screen="Site"),
        ],
    ),
    "enterprise_import_detail": (
        "The staged import", "Enterprise",
        "See exactly what an upload WOULD create -- before a single row is written.",
        [
            step("Nothing has been written yet", "This is a preview, not the register.",
                 "This is the most important screen in the import. Your file has been read, but "
                 "nothing has been written to the register yet.",
                 target=".alert, .card, .ent-page", screen="Import"),
            step("What would be created", "Row by row, exactly as it would land.",
                 "Here is every row, exactly as it would land in the register.",
                 target="table, .table", screen="Import"),
            step("Duplicates are caught", "The same school listed twice, under two codes.",
                 "A school listed twice in the same file is caught here -- even under two "
                 "different codes. The register alone could not catch that, because none of "
                 "this is in the register yet.",
                 target="table, .badge, .text-danger", screen="Import"),
            step("Invalid rows are rejected", "Not silently coerced into something wrong.",
                 "A row that does not make sense is rejected and told to you, rather than "
                 "quietly turned into something plausible.",
                 target="table, .text-danger, .alert", screen="Import"),
            step("Remap a column", "If the spreadsheet's headings are not ours.",
                 "If the spreadsheet's column headings are not the ones we expect, remap them "
                 "here rather than editing the file.",
                 target="select, form", screen="Import"),
            step("Commit, or cancel", "Only a commit writes. Cancel leaves no trace.",
                 "Only committing writes to the register. Cancelling leaves nothing behind.",
                 target='button[type="submit"], .btn-warning, .btn-outline-secondary',
                 screen="Import"),
        ],
    ),
    "enterprise_answers": (
        "Lifecycle answers", "Enterprise",
        "The agent answers every lifecycle question. You correct it.",
        [
            step("The agent answers, you edit", "You never face a blank form.",
                 "The whole point of the app is that the agent answers the lifecycle "
                 "questions for you. Your job is to correct what is wrong, not to write it "
                 "from nothing.",
                 target=".alert-info", screen="Answers"),
            step("Every phase, every activity", "All sixteen phases, in one place.",
                 "Each phase opens to show every activity in it, with its answer already in "
                 "the box.",
                 target=".accordion, .accordion-item", screen="Answers"),
            step("Let the agent answer", "It writes from this programme's own records.",
                 "Press this and the agent drafts an answer to every unanswered activity, "
                 "using the programme's own description, register and design. Answers you "
                 "have already saved are never overwritten.",
                 target=".btn-warning", screen="Answers"),
            step("Edit anything that is wrong", "It is a draft until you say otherwise.",
                 "A drafted answer is marked as drafted. Edit the text however you like.",
                 target="textarea", screen="Answers"),
            step("Save, and it becomes yours", "A saved answer outranks anything the app infers.",
                 "Save, and the answer becomes yours. From then on it is used word for word "
                 "in the documents you generate.",
                 target='button[type="submit"], .btn-warning', screen="Answers"),
        ],
    ),
    "enterprise_lifecycle_documents": (
        "Lifecycle documents", "Enterprise",
        "The real activities of each phase, written up from the programme's own answers.",
        [
            step("What this phase consists of", "The actual activities, not a template.",
                 "Each of the sixteen phases has real activities. This lists the ones for the "
                 "phase the programme is in.",
                 target=".table, table, .card", screen="Documents"),
            step("Tick what applies", "You choose what the document covers.",
                 "Tick the activities this document should cover.",
                 target='input[type="checkbox"], form', screen="Documents"),
            step("Answer, or upload a source", "It is written FROM the programme, not guessed.",
                 "Answer the questions, or upload a document it can read. The write-up comes "
                 "from the programme's own answers -- it is not invented.",
                 target='textarea, input[type="file"], form', screen="Documents"),
            step("Generate it", "Downloadable, and attached to the programme.",
                 "Generate it, and it is attached to the programme and downloadable.",
                 target='button[type="submit"], .btn-warning', screen="Documents"),
            nav("Open the write-up", "Every generated document has a report page.",
                "Every document you generate has a report page. Open it from the register.",
                href_from="a.js-doc-view", screen="Report"),
            step("Read it, print it, send it", "The same report component as a project design.",
                 "Read it on the page, print it, download it as a PDF, or email it to the "
                 "people who need it -- the same report component the project design uses.",
                 target=".btn-group, .btn-warning, form", screen="Report"),
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
