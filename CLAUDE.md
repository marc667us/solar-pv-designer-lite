# CLAUDE.md — Intelligent Global PV Solar System Design Platform

## Project Overview
An intelligent, globally accessible photovoltaic (PV) solar platform that performs complete
solar energy system design, electrical engineering analysis, financial engineering, and
project feasibility assessment for residential, commercial, and industrial applications.

This supersedes the original Ghana-focused tkinter desktop MVP. The project is now a
globally deployable web platform and is **not** restricted to any country or region.

Full functional requirements: see `SPEC.md`.

## Scope
Supported system types:
- Grid-connected
- Standalone / off-grid
- Hybrid

Automated workflows:
- Electrical load analysis
- Solar PV, battery, inverter, and charge controller sizing
- Electrical distribution design and cable sizing
- Protection coordination
- Financial modeling, energy savings, loan feasibility, bankability
- Technical documentation generation and automated report emailing

## Standards & Compliance
- **UK:** BS 7671, MCS
- **Europe:** IEC, EN
- **USA:** NEC, IEEE
- International electrical engineering best practices

## Core Functional Modules
1. User Management (roles: Administrator, Engineer, Client, Consultant, Financial Institution)
2. Project Management (multi-project, history, dashboard)
3. Load Analysis (load collection form + calculations)
4. Load Type Library (expandable appliance database)
5. PV Solar System Design (panel / battery / inverter / charge controller sizing)
6. Voltage Configuration (12/24/48/96V DC, single & three-phase AC)
7. Electrical Distribution Design (cable sizing, distribution, routing)
8. Protection Systems (breakers, fuses, SPD, earthing, lightning protection)
9. Installation Methodology (rooftop & ground-mounted)
10. System Type (grid / off-grid / hybrid)
11. Energy Impact Analysis (utility savings, CO2 reduction)
12. Financial Engineering (ROI, NPV, IRR, payback, DSCR, loan modeling)
13. Bankability Assessment (Bankable / Marginal / Not Bankable)
14. Reporting (technical, financial, BOM, BOQ, schedules — PDF/Excel)
15. Emailing & Communication (multi-recipient, CC/BCC, delivery tracking, logs)

## Recommended Technology Stack
- **Frontend:** React (preferred) / Angular / Vue.js
- **Backend:** Node.js (preferred) / Django / Laravel
- **Database:** PostgreSQL (preferred) / MySQL
- **Cloud:** AWS / Azure / Google Cloud

## Non-Functional Requirements
- Performance: fast calculations, real-time updates
- Security: authentication, data encryption, secure email
- Scalability: expandable appliance DB, multi-country deployment
- Reliability: accurate engineering calculations, standards compliance

## Future Expansion
AI energy forecasting, IoT & smart meter integration, GIS mapping, real-time monitoring,
mobile apps, utility API integration.

## General Rules
- Keep all engineering calculations transparent and traceable to inputs.
- Always include units in outputs.
- Keep code modular — one module per functional area.
- BOQ/BOM: major components only, realistic engineering assumptions, quantities traceable
  to calculations.
- Specifications: structured headings, professional tone; cover modules, inverter,
  batteries, cabling, protection, earthing, testing.

## Status
Spec consolidated and finalized 2026-05-14 from `Documents/for pv solar app.docx`.
Ready for final provisioning. Legacy desktop MVP code (ui.py, main.py, calculation/,
auth/, config/, dist2/) remains in this folder as reference until the web build begins.
