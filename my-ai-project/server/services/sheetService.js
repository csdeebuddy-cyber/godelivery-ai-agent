const fs = require('fs');
const path = require('path');

const CREDENTIALS_PATH =
  process.env.GOOGLE_APPLICATION_CREDENTIALS ||
  path.join(__dirname, '../../config/google_credentials.json');
const SHEETS_READONLY_SCOPE = 'https://www.googleapis.com/auth/spreadsheets.readonly';

/**
 * Read product rows from a Google Sheet for review.
 * Expected columns: id, name, regular price, comma-separated highlights, voice script.
 * This function never writes to the knowledge base.
 *
 * @param {string} spreadsheetId Google Sheets spreadsheet ID.
 * @param {string} range A1 notation, for example "Products!A2:E".
 * @returns {Promise<Array<object>>} Product payloads for the preview API.
 */
async function readProductsFromSheet(spreadsheetId, range) {
  if (typeof spreadsheetId !== 'string' || !spreadsheetId.trim()) {
    throw new TypeError('spreadsheetId must be a non-empty string.');
  }
  if (typeof range !== 'string' || !range.trim()) {
    throw new TypeError('range must be a non-empty A1 notation string.');
  }
  if (!fs.existsSync(CREDENTIALS_PATH)) {
    throw new Error(`Google Sheets credentials file not found: ${CREDENTIALS_PATH}`);
  }

  const { google } = require('googleapis');
  const auth = new google.auth.GoogleAuth({
    keyFile: CREDENTIALS_PATH,
    scopes: [SHEETS_READONLY_SCOPE],
  });
  const sheets = google.sheets({ version: 'v4', auth });
  const response = await sheets.spreadsheets.values.get({
    spreadsheetId: spreadsheetId.trim(),
    range: range.trim(),
  });
  const rows = response.data.values || [];

  return rows.map((row, index) => {
    const sheetRow = index + 2;
    const id = typeof row[0] === 'string' ? row[0].trim() : '';
    const name = typeof row[1] === 'string' ? row[1].trim() : '';
    if (!id || !name) {
      throw new Error(`Google Sheet row ${sheetRow} must include product ID and name.`);
    }

    const rawPrice = typeof row[2] === 'string' ? row[2].trim() : '';
    let price_regular = null;
    if (rawPrice) {
      price_regular = Number(rawPrice);
      if (!Number.isFinite(price_regular) || price_regular <= 0) {
        throw new Error(`Google Sheet row ${sheetRow} has an invalid regular price.`);
      }
    }

    return {
      id,
      name,
      price_regular,
      highlights: typeof row[3] === 'string'
        ? row[3].split(',').map((highlight) => highlight.trim()).filter(Boolean)
        : [],
      voice_script: typeof row[4] === 'string' ? row[4].trim() : '',
    };
  });
}

module.exports = { readProductsFromSheet };
