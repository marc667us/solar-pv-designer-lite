from ddgs import DDGS

TENDER_SITES = (
    "site:ungm.org OR site:devex.com OR site:tendersontime.com "
    "OR site:globaltenders.com OR site:tendersinfo.com "
    "OR site:dgmarket.com OR site:africatenders.com "
    "OR site:worldbank.org OR site:afdb.org OR site:reliefweb.int"
)

loc = "Ghana"
sector = "Commercial"

rfp_terms  = "RFP OR tender OR bid OR solicitation OR EOI"
queries = [
    "(" + TENDER_SITES + ") solar " + loc + " " + rfp_terms,
    loc + " solar PV request for proposal OR tender notice OR bidding document " + sector + " 2025 2026",
    loc + " solar energy expression of interest OR EOI OR prequalification 2025",
    "site:worldbank.org OR site:afdb.org solar " + loc + " procurement notice 2025 2026",
    "site:ungm.org solar " + loc + " 2025",
    "site:devex.com solar " + loc + " request for proposals OR call for bids 2025",
]

skip_domains = ["pv-magazine","pvtech","reuters.com","bloomberg.com","wikipedia.org",
               "youtube.com","linkedin.com/posts","twitter.com","facebook.com","instagram.com",
               "solarpowerworldonline","greentechmedia","renewableenergyworld"]

listing_patterns = ["-tenders/","-tenders$","/ghana-tenders","/solar-tenders",
    "/renewable-energy-tenders","/tenders.php","/global-ghana","/country/ghana",
    "?country=","/en/projects-operations/procurement","/Public/Notice$"]

rfp_keywords = ["rfp","tender","bid","proposal","solicitation","procurement",
               "expression of interest","eoi","invitation","prequalif","contract notice","call for"]

energy_keywords = ["solar","pv ","photovoltaic","renewable energy","wind","energy",
                  "power plant","mini grid","minigrid","electrification","off-grid","grid","kw","mw"]

results = []
with DDGS() as d:
    for q in queries:
        print("QUERY:", q[:90])
        try:
            batch = list(d.text(q, max_results=8, safesearch="off"))
            passed = 0
            for r in batch:
                url   = r.get("href","")
                body  = r.get("body","").lower()
                title = r.get("title","").lower()
                url_lower = url.lower()
                if any(s in url for s in skip_domains): continue
                if any(p in url_lower for p in listing_patterns): continue
                if not any(k in title or k in body for k in rfp_keywords): continue
                if not any(k in title or k in body for k in energy_keywords): continue
                if url and not any(x.get("href")==url for x in results):
                    results.append(r)
                    passed += 1
            print("  -> raw:", len(batch), "| passed:", passed)
        except Exception as e:
            print("  -> ERR:", e)

print()
print("=" * 70)
print("TOTAL SPECIFIC TENDERS/RFPS:", len(results))
print("=" * 70)
print()
for i, r in enumerate(results, 1):
    title = r.get("title","")
    url   = r.get("href","")
    snip  = r.get("body","")[:250]
    print(str(i) + ". " + title)
    print("   SOURCE : " + url)
    print("   EXCERPT: " + snip)
    print()
