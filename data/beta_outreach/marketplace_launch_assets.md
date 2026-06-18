# Marketplace soft launch — channel copy

URL: **https://solarpro.aiappinvent.com/marketplace**

---

## 1. Email (Brevo blast to 43 beta readers)

**Subject:** Electrical pricing live on SolarPro — free to browse

**Body (text):**

```
Hi [first name],

Quick update from SolarPro Global.

We just launched a free Electrical Pricing Marketplace as part of the
platform. You can browse live supplier prices for transformers, cables,
distribution boards, sockets, switchgear, earthing, ICT/ELV — and pull
those products straight into a BOM with labour + overhead + profit + VAT
markups baked in. Excel and PDF export of the finished BOQ are one click.

  Browse free: https://solarpro.aiappinvent.com/marketplace
  Build a BOQ: https://solarpro.aiappinvent.com/register

Why we built it: cost engineers and electricians were telling us the
hardest part of a tender wasn't the engineering — it was getting current
supplier prices fast. So we made one.

Supplier? List your products free and reach buyers globally:
  https://solarpro.aiappinvent.com/supplier/register

No credit card, no trial timer. Reply to this email if anything is
unclear or if there's a product category we're missing.

Thanks for being an early supporter.

Marc Owusu
SolarPro Global
```

**Brevo send command (dry-run first, then --send):**
```bash
cd Desktop/solar-pv-designer-lite
python scripts/send_marketplace_launch.py --dry-run
# review the planned recipient list
python scripts/send_marketplace_launch.py --send
```

(Send script not yet built — say "ship it" and I scaffold a send_marketplace_launch.py based on the existing send_reader_followup.py pattern.)

---

## 2. WhatsApp / SMS (short, for Ghana + Africa contacts)

```
SolarPro Global update — we just launched a free Electrical Pricing
Marketplace. Browse live supplier prices for transformers, cables,
switchgear, sockets, etc. + build BOQs with labour markups + export
Excel/PDF.

Free to browse: solarpro.aiappinvent.com/marketplace

Suppliers: list your products at /supplier/register
```

(232 characters — fits a single WhatsApp message + 1 SMS.)

---

## 3. LinkedIn post

```
SolarPro Global just launched a free Electrical Pricing Marketplace.

Browse live supplier prices for the full electrical scope —
transformers, HV/LV cables, distribution boards, switchgear, sockets,
earthing, ICT/ELV — and pull products straight into a BOM with labour,
overhead, profit, and VAT markups baked in. Excel and PDF export are
one click.

For cost engineers and electricians who've been wrestling with
spreadsheets and chasing supplier price lists: this is for you.
For suppliers in Ghana, Nigeria, Kenya, UK, US: list your products
free and reach buyers globally.

🔗 https://solarpro.aiappinvent.com/marketplace
🔗 Suppliers: https://solarpro.aiappinvent.com/supplier/register

#solarenergy #electricalengineering #procurement #BOQ #Ghana
```

---

## 4. Twitter / X thread (4 tweets)

**T1:** Just launched a free Electrical Pricing Marketplace on SolarPro Global. Live supplier prices across 20 electrical categories. Browse without signing up. https://solarpro.aiappinvent.com/marketplace

**T2:** Add products to a BOM, set labour / overhead / profit / VAT markup rates once, and the BOQ recalculates instantly. Export Excel or PDF in one click. No spreadsheets, no chasing supplier price lists.

**T3:** Suppliers can register free, upload a CSV/XLSX price list, and start receiving RFQs from buyers globally. Verified suppliers appear publicly. https://solarpro.aiappinvent.com/supplier/register

**T4:** Built specifically for cost engineers, estimators, electricians, and contractors in Ghana, Nigeria, Kenya, UK, US. Reply or DM if there's a category we're missing.

---

## 5. Footer line for solar app emails

(Add to existing solar transactional emails so every signed-in user sees it.)

```
PS — Browse the new Electrical Pricing Marketplace, free:
     https://solarpro.aiappinvent.com/marketplace
```
