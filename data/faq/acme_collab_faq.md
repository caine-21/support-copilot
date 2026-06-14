# Acme Collab FAQ Knowledge Base

## FAQ-billing-01 — How do I view and download my invoices?

**Category:** billing

**Answer:** Go to Settings → Billing → Invoice History. All invoices from the past 24 months are listed. Click any invoice to download it as a PDF. Invoices are also emailed to the billing contact automatically on each renewal date.

## FAQ-billing-02 — How do I update my payment method?

**Category:** billing

**Answer:** Go to Settings → Billing → Payment Methods. Click 'Add Payment Method' to add a new credit card or ACH bank account. To set a new default, click the three-dot menu next to the payment method and select 'Set as default'. Changes take effect on your next billing cycle.

## FAQ-billing-03 — What is Acme Collab's refund policy?

**Category:** billing

**Answer:** Acme Collab does not offer refunds for monthly plans. For annual plans, refunds are available within 14 days of purchase if the workspace has had fewer than 5 active sessions. After 14 days, no refunds are issued. Downgrading mid-cycle credits the unused portion to your next invoice — it is not refunded to your payment method.

## FAQ-billing-04 — Can I get a VAT invoice or tax receipt for my subscription?

**Category:** billing

**Answer:** Yes. For Personal and Team plans (up to 25 seats), VAT invoices are generated automatically when a billing address in a VAT-applicable region is set. Go to Settings → Billing → Tax Information to add your VAT number. NOTE: Enterprise plan tax invoice customization (cost center codes, purchase order numbers) requires contacting your dedicated Customer Success Manager — this is NOT available through the self-serve billing portal.

## FAQ-billing-05 — How do I add or remove seats from my subscription?

**Category:** billing

**Answer:** Team plan seats can be adjusted anytime. Go to Settings → Team → Manage Seats. Adding seats is prorated for the remainder of the billing cycle. Removing seats takes effect at the next renewal — you will not be refunded for unused seat-days. Minimum seat count is 3 for the Team plan.

## FAQ-feature-01 — How do I invite collaborators to a document?

**Category:** feature

**Answer:** Open the document and click the 'Share' button in the top-right corner. Enter the collaborator's email address and select their permission level: Viewer (read-only), Commenter, or Editor. They will receive an email invitation. If they do not have an Acme Collab account, they can join via the invitation link — no credit card required for invited collaborators on a paid workspace.

## FAQ-feature-02 — What permission levels are available and what can each role do?

**Category:** feature

**Answer:** Acme Collab has four permission levels: Owner (full control including billing), Admin (manage members, create/delete spaces, configure integrations), Editor (create and edit documents, cannot manage members), Viewer (read-only, cannot comment unless explicitly granted). Permissions are set at the Workspace level and can be overridden per Space or per Document.

## FAQ-feature-03 — How do I import documents from Notion or Confluence?

**Category:** feature

**Answer:** Go to Settings → Import. Supported formats: Notion (via Notion API token), Confluence (via space export ZIP), Google Docs (via Google OAuth), and Markdown (.md files). For Notion: connect your Notion workspace via OAuth, select pages to import. For Confluence: export your space as HTML archive and upload. Import preserves headings, tables, and code blocks. Images must be hosted externally — embedded images are not supported.

## FAQ-feature-04 — How do I export documents?

**Category:** feature

**Answer:** Open a document and click the three-dot menu (⋯) → Export. Available formats: PDF, Markdown, HTML, and DOCX. For bulk export of an entire Space, go to the Space settings → Export Space. Bulk exports are delivered as a ZIP file to your registered email within 10 minutes. Note: real-time collaborative fields (polls, vote blocks) are exported as static content.

## FAQ-feature-05 — How do I connect Slack to Acme Collab?

**Category:** feature

**Answer:** Go to Settings → Integrations → Slack → Connect. Authorize the Acme Collab Slack app in your Slack workspace. Once connected, you can: (1) get notifications in Slack when documents are edited or commented, (2) create Acme Collab tasks directly from Slack messages via /acme command, (3) share document previews by pasting an Acme link in Slack. Disconnect at any time from Settings → Integrations.

## FAQ-feature-06 — How do I set up webhooks for automation?

**Category:** feature

**Answer:** Go to Settings → Integrations → Webhooks → Add Webhook. Enter the endpoint URL and select the events to subscribe to (document.created, document.updated, comment.added, member.invited, etc.). Acme Collab sends a POST request with a JSON payload for each event. Webhook deliveries include a signature header (X-Acme-Signature) using HMAC-SHA256 for verification. Failed deliveries are retried 3 times with exponential backoff.

## FAQ-feature-07 — How do I use version history to restore a previous version of a document?

**Category:** feature

**Answer:** Open the document → click the clock icon (⏱) in the toolbar → Version History panel opens on the right. Each save or major edit creates a named version. Click any version to preview it. To restore, click 'Restore this version' — the current document becomes version N+1 and the selected version becomes the new current. Version history is retained for 90 days on Team plans and indefinitely on Enterprise plans.

## FAQ-feature-08 — Does Acme Collab have an API?

**Category:** feature

**Answer:** Yes. Acme Collab provides a REST API for programmatic access. API documentation is at docs.acmecollab.io/api. Authentication uses API tokens generated at Settings → API Tokens. Rate limit: 100 requests/minute for Team plans, 1000/minute for Enterprise. The API supports reading/writing documents, managing members, and querying audit logs. Webhooks are the recommended approach for real-time event streams; the API is best for batch operations.

## FAQ-troubleshoot-01 — I can't log in to my account. What should I do?

**Category:** troubleshoot

**Answer:** First, try resetting your password: go to the login page and click 'Forgot password'. Check your spam folder for the reset email. If using SSO, contact your IT admin — Acme Collab cannot bypass SSO configuration. If you see 'Account suspended', your workspace admin has deactivated your account. If the issue persists after password reset, clear your browser cache or try an incognito window, then contact support@acmecollab.io with your email address.

## FAQ-troubleshoot-02 — My document is not syncing / changes are not saving.

**Category:** troubleshoot

**Answer:** Sync issues are usually caused by (1) poor network connection — check your internet, (2) browser extension conflict — disable extensions and reload, (3) cached stale session — log out and log back in. If you see a red 'Unsaved changes' banner, do NOT close the tab — copy your content first. Check status.acmecollab.io for ongoing incidents. If the issue is isolated to one document, try opening it in another browser. If sync fails for over 5 minutes, contact support with the document ID.

## FAQ-troubleshoot-03 — I accidentally deleted a document. Can it be recovered?

**Category:** troubleshoot

**Answer:** Yes. Deleted documents go to the Trash (left sidebar → Trash) and are retained for 30 days. Click the document in Trash → 'Restore'. If the Trash has been emptied or 30 days have passed, recovery is not possible through the UI. Enterprise customers can request a data recovery backup restore via their CSM within 7 days of the Trash empty event. Personal and Team plan users cannot recover documents after Trash is emptied.

## FAQ-troubleshoot-04 — Acme Collab is slow or pages take a long time to load.

**Category:** troubleshoot

**Answer:** Performance issues can have several causes: (1) Large documents over 500 blocks may load slowly — use linked sub-pages to break them up; (2) Many embedded media files — consider linking instead of embedding; (3) Browser memory — try closing other tabs or use Chrome/Edge for best performance; (4) Geographic latency — check status.acmecollab.io for your region. If you are on a corporate VPN, try disabling it temporarily. For persistent issues, report via Settings → Feedback with your document URL.

## FAQ-troubleshoot-05 — I'm getting an error when trying to upload a file.

**Category:** troubleshoot

**Answer:** File upload limits: 25 MB per file for Team plans, 100 MB for Enterprise. Supported file types: images (PNG, JPG, GIF, WebP), PDFs, Office documents (DOCX, XLSX, PPTX), and video (MP4, up to 50 MB). If your file is within limits but upload fails, try: (1) a different browser, (2) check if your workspace storage quota is full (Settings → Billing → Storage), (3) disable VPN or proxy. Files with special characters in filenames may fail — rename and retry.

## FAQ-troubleshoot-06 — Team members are not receiving invitation emails.

**Category:** troubleshoot

**Answer:** Check: (1) the invited email address is spelled correctly, (2) ask invitees to check spam/junk folder — invitations come from noreply@acmecollab.io, (3) if your company uses an email allowlist, add acmecollab.io to it. You can resend an invitation: go to Settings → Team → Pending Invitations → Resend. Invitations expire after 7 days. If the email domain is blocked by corporate IT, the invitee can also join via a workspace join link (Settings → Team → Invite Link).

## FAQ-security-01 — Does Acme Collab support SSO (Single Sign-On)?

**Category:** security

**Answer:** Yes. SSO is available on Enterprise plans only. Supported protocols: SAML 2.0 and OIDC. Configuration requires Admin access. Go to Settings → Security → SSO → Configure. You will need your Identity Provider metadata URL or XML. Supported IdPs: Okta, Azure AD, Google Workspace, OneLogin, and any SAML 2.0-compliant IdP. SSO enforcement (block non-SSO logins) can be toggled after configuration. Personal and Team plan users must use email/password or Google OAuth — SSO is not available.

## FAQ-security-02 — Is my data encrypted? Where is it stored?

**Category:** security

**Answer:** All data is encrypted at rest (AES-256) and in transit (TLS 1.2+). Data is stored on AWS (US-East-1 by default). Enterprise customers can request EU data residency (Frankfurt, eu-central-1) at contract time. Acme Collab is SOC 2 Type II certified and GDPR compliant. Encryption keys are managed by Acme Collab — customer-managed keys (BYOK) are on the roadmap for H2 2026.

## FAQ-security-03 — How do I access audit logs?

**Category:** security

**Answer:** Audit logs are available on Enterprise plans. Go to Settings → Security → Audit Logs. Logs include: member login/logout, document access, permission changes, and admin actions. Logs are retained for 1 year. You can export logs as CSV or stream them to a SIEM via the Audit Log API. Team plan workspaces do not have audit log access — this is an Enterprise-only feature.

## FAQ-policy-01 — What is Acme Collab's SLA for uptime?

**Category:** policy

**Answer:** Acme Collab guarantees 99.9% monthly uptime for Team plans and 99.95% for Enterprise plans. Uptime is measured excluding scheduled maintenance windows (announced 48 hours in advance). If uptime falls below the SLA in a given month, customers may request a service credit: 10% of monthly fee for each percentage point below the SLA, up to 30% of the monthly fee. Credits must be requested within 30 days of the incident. Credits are applied to future invoices — no cash refunds.

## FAQ-policy-02 — Who owns the data I store in Acme Collab?

**Category:** policy

**Answer:** You retain full ownership of all content you create in Acme Collab. Acme Collab does not use customer content to train AI models. Upon account deletion, all data is deleted within 30 days from production systems and within 90 days from backups. You can export all your data at any time (Settings → Export All Data). Acme Collab's right to use your content is limited to providing the service as described in the Terms of Service.

## FAQ-policy-03 — Can I use Acme Collab for clients or customers outside my organization?

**Category:** policy

**Answer:** Yes, with conditions. Guest access is available: Workspace Admins can invite external users as Guests (Viewer or Commenter role only — Guests cannot be Editors). Guest seats are included at a ratio of 5:1 (5 guests per paid seat). Exceeding this ratio requires purchasing additional Guest Packs. Guests cannot create Spaces or invite other members. Using Acme Collab to resell access to end-customers (i.e., white-labeling) requires an OEM agreement — contact sales@acmecollab.io.
