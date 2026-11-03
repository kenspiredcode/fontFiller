# Font Filler

A small, personal prototype for filling missing characters in a static TrueType or CFF OpenType font, one at a time or in reviewed batches. It shows missing or empty characters, creates a replacement, and previews and downloads a modified copy. For ä, ë, ï, ö, and ü it reuses the font’s diaeresis, letter dots, or punctuation when available, or can generate an accent with AI while preserving the original base letter. It also supports selected lowercase and uppercase letters with acute, grave, circumflex, tilde, ring, macron, breve, caron, dot above, double acute, cedilla, ogonek, dot below, and comma below marks. It reuses available font outlines or can generate a mark with AI; acute marks can also use a suitable mirrored grave or rotated quote.

## Run locally

Requires Python 3.10+ and a fal API key with image generation access.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export FAL_KEY="your-fal-api-key"
export RATE_GATE_SECRET="your-rate-gate-secret"
python app.py
```

Open http://127.0.0.1:5050. The keys stay on the server and are not sent to the browser. The current font and candidate stay in the browser session and are sent to the backend for processing; a rendered specimen is sent to fal when you generate. API use may incur charges. The default model is GPT Image 1.5 Edit on fal, using low output quality and low input fidelity. A Cloudflare Worker and D1 database enforce a shared limit of 100 generation attempts per Pacific calendar day across preview and production; failures count and the app fails closed if the counter is unavailable. The local server also needs the rate gate secret.

Static `.ttf` fonts with TrueType outlines and `.otf` fonts with CFF outlines are supported. Variable fonts, CFF2, and CID-keyed CFF fonts are not supported yet. Generated shapes are automatically traced and are best suited to display text; inspect the resulting spacing and shape. The user must have permission to modify the font and send its specimen to the provider. The modified font preserves existing metadata and is given a distinct family name. The hosted version requires Vercel Authentication. GitHub Pages alone cannot run the Python backend. Font uploads are limited to 2.5 MB.

The experiment is in `experiment/`. Font files are excluded from the repository; supply your own test fonts in `testFonts/` when needed.

The page maintains an in-browser workspace. After reviewing an individual preview, choose **Use this character in workspace** to add it to the current font; select any character in the map to make another replacement. Bulk preparation and accepted bulk candidates update the same workspace. Download the workspace font to keep the changes; reloading the page discards the in-progress workspace.

Accent previews include size and position controls. New letters inherit the base letter’s advance and available pair kerning; an overhang warning flags marks extending beyond the advance. When an i or j dot cannot be separated safely, letters that replace that dot cannot be built. Floating accents are checked for possible collisions, and attached accents for possible disconnection. When the default placement triggers a check, the app tries a small automatic position adjustment; approximate outline checks and adjusted results are flagged for review in individual and bulk previews. Manual position adjustments are applied relative to the corrected default and are checked without overriding them. AI accent generation uses the same daily limit and requires review of the resulting mark.

## Bulk workflow

After uploading a font and confirming permission, choose **Prepare missing characters**. The app builds supported missing inverted marks and accents when it can reuse the font’s outlines. For buildable accented letters still missing a mark, the app generates one reusable mark per family in 3×3 grids (with separate side carons and the inverted mark for ģ). Review and select the marks to build all eligible lowercase and uppercase letters from their original bases, sharing each mark between cases when possible. Other remaining characters are limited to the character map shown in the app; choose a 3×3 or 4×4 grid for those candidates; each image request counts against the shared daily limit and may incur charges. The browser sends requests sequentially, so keep the page open. Completed candidates remain available if a later request fails.

Review each image for identity, clipping, shape, and style, select the ones to add, and inspect the resulting letters and placement before downloading the font. Regenerate or discard an individual candidate without resetting the workspace. A rejected or unusable mark leaves its letters missing. Content-aware separators warn when they cross ink; they cannot verify character identity and there is no OCR. Bulk characters use automatic size and spacing estimates, so inspect the font carefully. Reloading the page discards the browser’s in-progress candidates.
