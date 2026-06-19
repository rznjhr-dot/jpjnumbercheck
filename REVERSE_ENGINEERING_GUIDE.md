# JPJ mySIKAP API Reverse-Engineering Guide

## The Goal

Find the actual data source/API that returns number plate availability on the
real JPJ mySIKAP portal, so we can either:
1. Call it directly (bypassing the ZK UI complexity)
2. Or at least automate the UI reliably

## How ZK Framework Works

The JPJ site uses ZK Framework (Java-based AJAX). Instead of standard HTML
forms, ZK uses:

1. **ZK AU (Asynchronous Update) requests** — POST requests to `/public/zkau`
   that send widget state changes and receive back instructions to update the UI
2. **Desktop updates** — The server sends back JSON with widget UUIDs,
   attributes to change, and content to render
3. **Combo boxes** — Not native `<select>` elements but ZK combo widgets with
   a hidden input + custom popup

## The Capture Scripts

### `capture_jpj_api.py` — Primary (RECOMMENDED)

Uses Playwright's built-in request/response listeners to capture ALL decrypted
HTTPS traffic. This is the most effective because:
- No proxy setup needed
- Sees all HTTPS request/response bodies (Playwright already decrypts them)
- Saves everything to organized files

**Usage:**
```bash
# Run with browser visible (so you can login & interact)
python3 capture_jpj_api.py --number 888

# Or headless (will wait for you to login)
python3 capture_jpj_api.py --number 1234 --headless
```

### `mitm_proxy.py` — Alternative (HTTP only)

Standalone forward proxy that logs and saves all traffic. HTTPS traffic is
tunneled (can't inspect bodies).

**Usage:**
```bash
python3 mitm_proxy.py
# Then configure Playwright to use it
```

## What to Look For

### 1. ZK AU Requests (the main event)

Look for POST requests to `https://public.jpj.gov.my/public/zkau` with these
parameters in the request body:

- `dtid` — desktop ID (session identifier)
- `uuid` — widget UUID being interacted with
- `cmd` — command being sent (e.g., `onSelect`, `onChange`, `onClick`)
- `data` — widget state data

The response will be JSON with structure like:
```json
[
  {"uuid": "widget-uuid", "attr": "value", "content": "..."},
  ...
]
```

### 2. ZUL Page Loads

Look for requests to `*.zul` files — these are ZK page definitions that
describe the UI component tree. They may contain embedded data.

### 3. What Specifically To Find

When you run the capture and interact with the site:

1. **State selection** → what's the request/response when selecting a state?
   - Does it fetch the list of available prefixes (Awalan) from an API?
   - Or are they pre-loaded in the page?

2. **Cari button** → what's sent when clicking "Cari"?
   - This is the KEY request — it should contain the search parameters
   - The response should contain number availability data
   - If it's a ZK AU request, the response will be encoded

3. **Direct API endpoints** — look for any non-ZK requests:
   - REST-like API calls
   - JSON endpoints
   - Direct data fetches

## Next Steps After Capture

1. **Identify the Cari request** — find the request made when clicking "Cari"
2. **Extract parameters** — what exactly is sent (state, awalan, number, etc.)
3. **Analyze response format** — how does the server return availability?
4. **Test direct calls** — once identified, try calling the endpoint directly
   with `urllib` or `requests` (with proper session cookies)

## Expected Findings

Based on typical ZK applications, the most likely scenario is:

- The search is submitted as a ZK AU request
- The server returns a JSON response with widget updates
- The number data is embedded in the response content
- OR: there might be a REST API behind the scenes that ZK calls server-side

If the data comes through ZK AU, we may need to:
- Maintain a session (cookies)
- Send properly formatted ZK AU requests
- Or use Playwright's `page.evaluate()` to directly call ZK widgets

If there's a REST API, we can call it directly with any HTTP client.
