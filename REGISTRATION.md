# Signal Account Registration

Step-by-step guide to register a dedicated Signal number for the bot.

## Prerequisites

- signal-api container running: `docker compose up -d signal-api`
- Verify it's healthy: `curl http://localhost:9922/v1/about`
- A phone number that can receive SMS

## Option A — Register a New Number (dedicated bot account)

Use this when you want the bot to have its own phone number. Messages sent by the bot won't appear on any personal device.

### Step 1: Get a captcha token

1. Open https://signalcaptchas.org/registration/generate.html in your browser
2. Solve the captcha
3. When it says "Open Signal", **right-click** the link and **Copy Link Address**
4. The link looks like: `signalcaptcha://signal-hcaptcha.XXXXX...`
5. Copy everything after `signalcaptcha://` — that's your token

### Step 2: Register

```bash
curl -X POST "http://localhost:9922/v1/register/+YOUR_NUMBER" \
  -H "Content-Type: application/json" \
  -d '{"captcha": "YOUR_CAPTCHA_TOKEN", "use_voice": false}'
```

An empty response means success. You should receive an SMS with a verification code.

### Step 3: Verify

Submit the SMS code immediately (sessions expire quickly):

```bash
curl -X POST "http://localhost:9922/v1/register/+YOUR_NUMBER/verify/CODE" \
  -H "Content-Type: application/json"
```

An empty response means success. Verify the account is active:

```bash
curl http://localhost:9922/v1/accounts
# Should return: ["+YOUR_NUMBER"]
```

### Step 4: Update .env

```env
SIGNAL_NUMBER=+YOUR_NUMBER
```

## Option B — Link as Secondary Device

Use this when you want the bot to share your existing Signal account. Note: your phone will see all bot messages too.

1. Open `http://localhost:9922/v1/qrcodelink?device_name=signal-agent`
2. On your phone: Signal → Settings → Linked Devices → "+" → scan the QR code

## Troubleshooting

### "Captcha required for verification"

The initial registration call without a captcha was rejected. Follow Step 1 above to get a captcha token.

### "Rate Limited" (429)

Signal rate-limits registration attempts. Wait 1-24 hours (usually a few hours) and try again with a fresh captcha.

### "Already verified" (409) but no account shows up

The registration completed server-side but signal-cli didn't save the session. Fix:

```bash
# Stop signal-api and clear stale data
docker compose stop signal-api
rm -rf data/signal-cli/data/*
docker compose up -d signal-api

# Start the registration flow from Step 1 again
```

### Verify error: StatusCode 499

This is a known issue with older versions of signal-cli. Upgrade to the latest image:

```bash
docker compose stop signal-api
docker compose rm -f signal-api
docker pull bbernhard/signal-cli-rest-api:latest
docker compose up -d signal-api
```

Then start the registration flow from Step 1 again.

### "No registration verification session active"

The verification session expired between registration and verification. You need to register again with a fresh captcha and verify immediately when the SMS arrives.

### Voice verification

If SMS isn't working, try voice verification (phone call with the code):

```bash
curl -X POST "http://localhost:9922/v1/register/+YOUR_NUMBER" \
  -H "Content-Type: application/json" \
  -d '{"captcha": "YOUR_CAPTCHA_TOKEN", "use_voice": true}'
```
