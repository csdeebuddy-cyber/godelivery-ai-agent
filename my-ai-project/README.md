# AI Agent Voice Allday

FastAPI chat application with a Gemini Live real-time voice session and browser UI.

## Run locally

1. Copy `.env.example` to `.env` and set `GEMINI_API_KEY`.
2. Install dependencies with `pip install -r requirements.txt`.
3. Start the server from this folder:

   ```powershell
   uvicorn app.main:app --reload
   ```

4. Open `http://127.0.0.1:8000`.
5. Press the microphone button and allow microphone access for real-time voice, or send a text message to receive a spoken Live response.

## Admin dashboard and Google SSO

- Public service domain: `https://711shopping.com` (after DNS and Cloud Run domain mapping are configured).
- Customer homepage: `https://711shopping.com/` (GoDelivery landing page).
- Customer voice page: `https://711shopping.com/chatandshop` (AI Voice Allday; linked from the homepage).
- Admin login/dashboard: `https://711shopping.com/dashboard/admin`; the admin link is also available on the voice page.
- Before publishing, map `711shopping.com` to the Cloud Run service, configure its DNS and HTTPS certificate, and set `ADMIN_OAUTH_REDIRECT_URI=https://711shopping.com/admin/auth/google/callback` in the production service. Register that same callback URL in the Google OAuth client.
- Google sign-in is restricted server-side to the verified account `smpmfast@gmail.com`.
- OAuth configuration is not included. Set `ADMIN_GOOGLE_CLIENT_ID`, `ADMIN_GOOGLE_CLIENT_SECRET`, `ADMIN_OAUTH_REDIRECT_URI`, and a strong random `ADMIN_SESSION_SECRET` (at least 32 characters) using Secret Manager in production. Never commit these values.
- Set the Gemini key as a Secret Manager secret named `GEMINI_API_KEY`, then bind it to the Cloud Run service as the `GEMINI_API_KEY` environment variable. The admin page shows only whether the variable is present; it never accepts or returns the key. After changing a secret, deploy a new Cloud Run revision so the running app loads it.
- Register the exact redirect URI `https://711shopping.com/admin/auth/google/callback` in the Google OAuth client, and use the matching deployed domain. For local testing, register a separate localhost redirect URI and set it in `.env`.
- The OAuth authorization-code flow uses signed state, PKCE, verified Google ID tokens, an exact email allowlist, and an HttpOnly session cookie.
- `GET /api/v1/admin/status` reports whether SSO is configured. `GET /api/v1/admin/overview` is protected by the signed admin session.
- The dashboard stores one Google Sheets Spreadsheet ID and separate ranges/mappings in Firestore through `PUT /api/v1/admin/settings/google-sheets`. Defaults: `product!A2:E` maps ID, name, regular price, sale price, and stock quantity; `promotion!A2:C` maps promotion ID, name, and conditions; `orders!A:O` and `MEMBER!A:F` are private customer-data append ranges. The admin-only `GET /api/v1/admin/settings/google-sheets/preview` reads only the product and promotion ranges from that same Spreadsheet ID and returns a non-persisting preview. It never reads orders or MEMBER and does not publish to the knowledge base. Ensure the Cloud Run runtime service account can access Firestore and Google Sheets, and share the spreadsheet with that identity first.
- The admin dashboard at `/dashboard/admin` edits the public homepage content, company information, terms, Privacy Policy, shipping, returns, FAQs, products, and promotions through `GET/PUT /api/v1/admin/settings/site-content`. Updates are stored in the `admin_settings/homepage_content` Firestore document and are publicly served by `GET /api/v1/site/content` with inactive products and promotions excluded. A successful save is immediately available on the homepage. Admin writes require the authenticated admin session and CSRF token.
- The public product storefront is available at `/product` (for example `https://711shopping.com/product`). The homepage product menu and product section link to this page. Both views read the same active products from `/api/v1/site/content`, maintained in the admin website-content module; product image, regular/sale price, stock, and active state are shared. The storefront supports name/ID search and sorting by price or discount, and its “ซื้อเลย” action adds the product to the same browser basket then opens `/#basket`. The homepage shows the first four active products in the order saved by admin; use the product “เลื่อนขึ้น/เลื่อนลง” controls to set that order before saving.
- Firebase project integration uses the project ID `gen-lang-client-0845508747` by default (`FIRESTORE_PROJECT_ID` can override it). Shared ADC-backed Firestore and Storage clients live in `app/services/firebase/`; feature services use these helpers so later Firebase-backed capabilities can follow the same server-side pattern. No Firebase credentials or admin SDK keys are sent to the browser. Firestore collections are logical collections, and Storage prefixes such as `catalog/` are object-name prefixes rather than real folders.
- To enable the Firebase image library, enable the Cloud Firestore and Cloud Storage for Firebase APIs in Google Cloud, create/initialize Firestore in the project, and create a Storage bucket in Firebase Console → Storage. In Cloud Run, open the `allday-voice-agent` service → **Edit and deploy new revision** → **Containers, Networking, Security** → **Variables & Secrets** → **Add a variable**. Enter the variable name `FIREBASE_STORAGE_BUCKET` and its value as the exact bucket name shown in Firebase Console → Storage (for example, `project-id.firebasestorage.app` only if that is exactly what the console displays). This setting is the bucket name, not an API key or secret. Save and deploy the revision. The bucket name is intentionally not guessed. The equivalent local `.env` entry is `FIREBASE_STORAGE_BUCKET=`. Set `FIRESTORE_PROJECT_ID=gen-lang-client-0845508747` on Cloud Run as well, so the deployed service identity and application target the same project.
- Grant the Cloud Run **runtime service account** access to Firestore (the predefined `roles/datastore.user` role is a practical starting point) and grant it `roles/storage.objectAdmin` on the selected bucket for server-side image upload/read. Keep the existing Google Sheets Editor access for order/member writes. Cloud Run uses Application Default Credentials; do not create or upload service-account JSON keys. These IAM grants are separate from Firebase client Security Rules.
- The product image library is admin-only and CSRF-protected (`GET /api/v1/admin/assets`, `POST /api/v1/admin/assets/images`). It accepts JPEG, PNG, or WebP up to 5 MB, stores objects under `catalog/`, and saves visibility metadata in the `site_assets` Firestore collection. A public image endpoint serves only records explicitly marked `public_catalog`; customer/order/member records are not placed in Firebase Storage. Select the uploaded image in the product editor and save the homepage content to publish it.
- `firebase.json`, `firestore.rules`, and `storage.rules` provide deny-by-default rules for direct browser/client SDK access. From `my-ai-project`, deploy them to the intended Firebase project with `firebase deploy --project gen-lang-client-0845508747 --only firestore:rules,storage`. The Cloud Run server uses Google Cloud IAM/ADC, so these client Security Rules do not replace the required service-account IAM grants. Do not enable public bucket access; public catalog images are returned through the application endpoint.
- Setting environment variables does not automatically enable Google Cloud APIs, create a Firestore database/bucket, deploy Security Rules, or grant IAM roles. Those one-time project setup steps must be completed in Google Cloud/Firebase Console. Once complete, the application reuses the same project and credentials for its registered Firestore/Storage features. The admin dashboard reports configured project/bucket values; an upload/read request is the actual permission/connectivity check.
- Customer orders are guest checkout with cash on delivery only; there is no online payment processing. The server verifies active product IDs, prices, and stock from Firestore before appending an order to `orders!A:O`. Columns A:O are, in order: `Orders date`, `ordernumber`, `Agent`, `customer`, `address`, `address1`, `Postcode`, `Phone_number`, `Product`, `Price`, `Remark`, `ประเภทชำระเงิน`, `COD`, `Track`, `status`. The server generates the date/order number, uses `เว็บไซต์` for Agent, stores a Privacy Policy consent timestamp in Remark, uses `เก็บเงินปลายทาง` as payment type, sets COD to the verified total, leaves Track blank, and sets status to `รับรายการแล้ว`.
- Optional guest member registration writes only `Registered date`, `membernumber`, `customer`, `Phone_number`, `Email`, and `privacy_consent` to `MEMBER!A:F`. Customer-provided personal data is never included in the public content API. Keep both tabs private. The website requires an explicit Privacy Policy consent checkbox before writing customer data.
- Google Sheets writes use the Cloud Run service account. Enable the Google Sheets API and share the spreadsheet with that identity as **Editor**; read-only access is insufficient. Product and promotion publication remains in Firestore and is intentionally separate from customer data stored in Sheets.
- The admin dashboard can create, edit, and deactivate embeddable chat widget profiles at `/api/v1/admin/widget-sites`. Each profile stores its allowed website hostnames and display settings in the same Firestore project, then generates a copyable install snippet. Share the snippet with the site owner to install on the advertising or landing page. The widget talks to the central `/api/v1/widget/chat` endpoint and uses the existing central knowledge base. Firestore must be configured; widget chat and preflight requests are restricted to the exact registered hostname in the browser `Origin` header. Add each hostname separately (for example `example.com` and `www.example.com`); do not enter a URL path.
- For Google Sheets, use the Cloud Run service account identity (Application Default Credentials), enable the Google Sheets API, and share the spreadsheet with that service account with Viewer access. Do not upload a service-account JSON key through the admin page.
- In Google Cloud, create the Firestore database, grant the Cloud Run runtime service account Firestore access, and share the sheet with it as described above. The default Firebase project ID is `gen-lang-client-0845508747`; configure `FIREBASE_STORAGE_BUCKET` with the exact bucket name from Firebase Console to enable image uploads.
- This initial scaffold does not configure Google Cloud domain mapping, OAuth consent-screen settings, Firestore, or Cloud Run secrets. Complete those deployment settings before enabling admin sign-in.

## Automatic Cloud Run deployment from GitHub

The repository root contains `cloudbuild.yaml`. Configure a Cloud Build trigger for the connected GitHub repository `csdeebuddy-cyber/godelivery-ai-agent` with event **Push to a branch**, branch regex `^main$`, and build configuration file `cloudbuild.yaml` at the repository root. The build uses `my-ai-project/Dockerfile`, pushes a commit-tagged image to Artifact Registry, then deploys that image to the existing Cloud Run service. Each successful push to `main` creates a new revision and sends traffic to it.

Before creating the trigger:

1. Enable Cloud Build, Artifact Registry, and Cloud Run APIs.
2. Create a Docker Artifact Registry repository in the same region as the Cloud Run service. `_REGION` is used for both the Artifact Registry image host and the Cloud Run deploy region.
3. Give the trigger's build service account `roles/artifactregistry.writer` on that repository and `roles/run.admin` on the project (or narrower equivalent permissions).
4. Grant the build service account `roles/iam.serviceAccountUser` on the existing Cloud Run runtime service account so it can deploy using that identity.
5. Connect the GitHub repository in Cloud Build Repositories/Triggers and create the trigger with substitutions:
   - `_REGION`: Artifact Registry repository region (for example `asia-southeast1`).
   - `_AR_REPO`: Artifact Registry Docker repository name.
   - `_SERVICE`: existing Cloud Run service name.

The deploy step changes the container image only; keep production secrets and environment configuration on the Cloud Run service or in Secret Manager, not in this file. Test the first deployment in Cloud Build History and Cloud Run Revisions. If the build fails, check the trigger's build service-account permissions and the substitution values.

## Search indexing

The customer and admin pages, as well as API responses, send `noindex` directives using HTML metadata and the `X-Robots-Tag` response header. `robots.txt` allows crawlers to fetch the pages so they can read and honor the `noindex` directive; blocking crawling alone can leave URLs visible in search results. This is not access control—the admin dashboard still requires server-side authentication. After deployment, verify the live URLs in Google Search Console; if a URL was already indexed, request temporary removal there while Google recrawls the `noindex` response.

## Gemini Live settings

The defaults match the requested AI Studio settings:

- Model: `gemini-3.8-live`
- Voice: `Zephyr`
- Media resolution: `MEDIA_RESOLUTION_MEDIUM`
- Context compression trigger: `104857` tokens
- Context compression target: `52428` tokens
- System instructions: set by `GEMINI_LIVE_SYSTEM_INSTRUCTION`
- Function calling and Google Search grounding: disabled for the voice session so Live audio responses remain continuous

Each setting can be overridden with the corresponding `GEMINI_LIVE_*` environment variable. The browser streams 16 kHz PCM microphone audio to the FastAPI WebSocket endpoint at `/api/v1/live`; Gemini Live audio is played back from 24 kHz PCM response chunks. Microphone access requires localhost or HTTPS.

The standard `/api/v1/chat` endpoint remains available for non-live text generation.

## Embeddable chat widget

Sign in to `/dashboard/admin`, create a widget profile with the website's exact hostname(s), and copy the generated snippet to send to its owner. The owner installs both script tags in the page HTML, preferably near the closing `</body>` tag. The site-specific appearance and `siteId` are included in the snippet; the JavaScript SDK is served centrally from `/static/widget.js`, and messages are handled by `/api/v1/widget/chat`. No Gemini key or other secret is exposed to the website.

The widget needs a public HTTPS deployment and a reachable Firestore-backed site profile. The API validates the browser origin against that profile and returns CORS permission only for an allowed origin. This browser-origin check is an integration control, not strong client authentication: site IDs and install snippets are public, and non-browser callers can forge an `Origin` header. Add server-side rate limiting and abuse monitoring before using the endpoint for high-volume public advertising traffic.

The Live microphone session stays connected across multiple user turns. Use the microphone button to pause/resume audio, and close the browser connection to end the Live session.

## Product knowledge base

The local knowledge files are in `knowledge_base/`. Their current product and promotion data is loaded into Gemini Live's system context when a session starts. A local search endpoint is available to test and inspect product, promotion, fulfillment, and policy data without sending it to the model. Test the files without starting or restarting the server:

```powershell
python -c "from app.services.knowledge_base import get_knowledge_base_status, search_knowledge_base; print(get_knowledge_base_status()); print(search_knowledge_base('ราคาและโปรโมชันน้ำมันงาดำ'))"
```

The knowledge API also exposes `GET /api/v1/knowledge/status` and `GET /api/v1/knowledge/search?q=...`. Refresh public Product structured data with `python scripts/refresh_godelivery_catalog.py`. The refresh intentionally excludes aggregate price ranges and does not infer active promotions. Review and verify any scraped claims with the business before marking a product or promotion as verified.

The API also exposes:

- `GET /api/v1/knowledge/products` — the current local product catalog.
- `POST /api/v1/knowledge/products/preview` — validates a future import payload as a JSON array, but does not save it. Until product facts are verified, only the product ID and name are echoed; category, price, unit, highlights, and voice script are excluded from the preview.
- `GET /api/v1/knowledge/promotions` — promotions marked active in the local knowledge base.
- `POST /api/v1/knowledge/promotions/preview` — validates a future promotion import payload as a JSON array, but does not save or activate promotions. Only the promotion ID and title are echoed; applicability, price, details, shipping, and status are excluded until verified.
- `GET /api/v1/integrations/status` — reports configured external integrations.
- `POST /api/v1/integrations/google-sheets/sync` — reserved for future use; currently returns `501 integration_not_configured` and does not sync or change data.

Google Sheets is not connected, and Google service-account credentials are not included. Do not commit `config/google_credentials.json`; use an approved secret store if a Google Sheets connection is added.

The optional Node.js readers in `server/services/sheetService.js` map 1-based column positions for product and promotion tabs; they remain read-only and are not used by the FastAPI preview endpoint. The connected admin preview uses Google Application Default Credentials and the Python Google Auth dependency to read only the public product and promotion ranges. Neither path writes `catalog.json` or activates promotions.

Run the local knowledge-base tests with `python -m unittest discover -s tests`.
