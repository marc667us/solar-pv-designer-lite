# beta_outreach/

Curated outreach material used by `.github/workflows/send-beta-invites.yml`.

- `ghana_beta_invitees.json` — Ghana solar installer + supplier directory.
  All emails and phone numbers were collected from each business's public
  website, Google Business listing, or government registry. No private
  contact information.

- `SolarPro_Sales_Pitch.pdf` — public-facing product brochure.

The send-beta-invites workflow ships this brochure as an attachment with
the v0.9.0-beta.1 invitation email. The same workflow renders a copy of
the exact email body sent to disk in the workflow artifacts for audit.
