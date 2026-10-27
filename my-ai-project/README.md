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

An isolated future connector stub is available at `server/services/sheetService.js`. Its `readProductsFromSheet(spreadsheetId, range)` function is read-only and returns rows for review; it does not write `catalog.json` and is not connected to the API. To use it later, install the Node.js `googleapis` package and provide credentials through `GOOGLE_APPLICATION_CREDENTIALS` or the ignored `config/google_credentials.json` file. Review the data through the preview endpoint before any approved import.

Run the local knowledge-base tests with `python -m unittest discover -s tests`.
