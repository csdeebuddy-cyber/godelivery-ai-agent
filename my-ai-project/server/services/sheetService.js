const fs = require('fs');
const path = require('path');

const CREDENTIALS_PATH =
  process.env.GOOGLE_APPLICATION_CREDENTIALS ||
  path.join(__dirname, '../../config/google_credentials.json');
const SHEETS_READONLY_SCOPE = 'https://www.googleapis.com/auth/spreadsheets.readonly';

/**
 * Read product rows from a Google Sheet for review.
 * Maps configured column positions to id, name, regular/sale prices, and stock.
 * This function never writes to the knowledge base.
 *
 * @param {string} spreadsheetId Google Sheets spreadsheet ID.
 * @param {string} range A1 notation, for example "Products!A2:E".
 * @param {{product_id:number, product_name:number, regular_price:number, selling_price:number, stock_quantity:number}} columnMapping
 *   1-based positions within the requested range.
 * @returns {Promise<Array<object>>} Product payloads for the preview API.
 */
async function readProductsFromSheet(spreadsheetId, range, columnMapping = {
  product_id: 1,
  product_name: 2,
  regular_price: 3,
  selling_price: 4,
  stock_quantity: 5,
}) {
  if (typeof spreadsheetId !== 'string' || !spreadsheetId.trim()) {
    throw new TypeError('spreadsheetId must be a non-empty string.');
  }
  if (typeof range !== 'string' || !range.trim()) {
    throw new TypeError('range must be a non-empty A1 notation string.');
  }
  const mappingFields = [
    'product_id',
    'product_name',
    'regular_price',
    'selling_price',
    'stock_quantity',
  ];
  if (
    !columnMapping ||
    mappingFields.some((field) => !Number.isInteger(columnMapping[field]) || columnMapping[field] < 1) ||
    new Set(mappingFields.map((field) => columnMapping[field])).size !== mappingFields.length
  ) {
    throw new TypeError('columnMapping must contain distinct positive 1-based column positions.');
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
    const readCell = (field) => row[columnMapping[field] - 1];
    const id = String(readCell('product_id') ?? '').trim();
    const name = String(readCell('product_name') ?? '').trim();
    if (!id || !name) {
      throw new Error(`Google Sheet row ${sheetRow} must include product ID and name.`);
    }

    const readOptionalNumber = (field, label, { integer = false, min = 0 } = {}) => {
      const rawValue = String(readCell(field) ?? '').trim();
      if (!rawValue) return null;
      const value = Number(rawValue);
      if (!Number.isFinite(value) || value < min || (integer && !Number.isInteger(value))) {
        throw new Error(`Google Sheet row ${sheetRow} has an invalid ${label}.`);
      }
      return value;
    }

    return {
      id,
      name,
      price_regular: readOptionalNumber('regular_price', 'regular price', { min: Number.EPSILON }),
      price_sale: readOptionalNumber('selling_price', 'selling price', { min: Number.EPSILON }),
      stock_quantity: readOptionalNumber('stock_quantity', 'stock quantity', { integer: true }),
    };
  });
}

/**
 * Read promotion rows from Google Sheets for review. This function never
 * activates promotions or writes to the knowledge base.
 *
 * @param {string} spreadsheetId Google Sheets spreadsheet ID.
 * @param {string} range A1 notation, for example "Promotions!A2:C".
 * @param {{promotion_id:number, promotion_name:number, conditions:number}} columnMapping
 *   1-based positions within the requested range.
 * @returns {Promise<Array<object>>} Promotion payloads for the preview API.
 */
async function readPromotionsFromSheet(spreadsheetId, range, columnMapping = {
  promotion_id: 1,
  promotion_name: 2,
  conditions: 3,
}) {
  if (typeof spreadsheetId !== 'string' || !spreadsheetId.trim()) {
    throw new TypeError('spreadsheetId must be a non-empty string.');
  }
  if (typeof range !== 'string' || !range.trim()) {
    throw new TypeError('range must be a non-empty A1 notation string.');
  }
  const mappingFields = ['promotion_id', 'promotion_name', 'conditions'];
  if (
    !columnMapping ||
    mappingFields.some((field) => !Number.isInteger(columnMapping[field]) || columnMapping[field] < 1) ||
    new Set(mappingFields.map((field) => columnMapping[field])).size !== mappingFields.length
  ) {
    throw new TypeError('columnMapping must contain distinct positive 1-based column positions.');
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
    const readCell = (field) => String(row[columnMapping[field] - 1] ?? '').trim();
    const promo_id = readCell('promotion_id');
    const title = readCell('promotion_name');
    if (!promo_id || !title) {
      throw new Error(`Google Sheet row ${sheetRow} must include promotion ID and name.`);
    }
    return {
      promo_id,
      title,
      details: readCell('conditions'),
    };
  });
}

module.exports = { readProductsFromSheet, readPromotionsFromSheet };
