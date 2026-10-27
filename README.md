# Dadi Ke Kisse: automatic YouTube uploads

This repo uploads the channel's Shorts to YouTube for free with GitHub Actions.

**How it works:** Kahani Studio makes the Shorts → they are pushed here as `shorts/<slug>/` (video.mp4, cover.png, meta.json) → the **Upload Shorts to YouTube** workflow uploads each one as a scheduled Short (it goes public at its `publish_at` time), sets the cover as the thumbnail, adds it to the character's playlist, writes the YouTube link into `meta.json` and `UPLOADS.md`, and deletes the uploaded video.mp4 to keep the repo small.

- Runs on every push to `shorts/`, every 6 hours as a safety net, and by hand (Actions tab → Upload Shorts to YouTube → Run workflow).
- Safety check: it only uploads if the Google login belongs to the Dadi Ke Kisse channel (`UCx70naO0DMEATXMUHYWaP6Q`, https://www.youtube.com/channel/UCx70naO0DMEATXMUHYWaP6Q).
- Settings used for every Short: public at the scheduled time, **not made for kids**, category Film & Animation, language Hindi, subscribers notified.
- YouTube API limits: 100 uploads per day and 10,000 quota units per day (each Short uses about 150 units including thumbnail and playlist), far above 3-9 Shorts a day.

## One-time setup (about 15 minutes)

You need three secrets from Google: a client ID, a client secret and a refresh token. Use the Google account that owns the **Dadi Ke Kisse** channel.

### 1. Google Cloud project and YouTube API
1. Open https://console.cloud.google.com/ → project picker → **New project** → name `dadi-ke-kisse-uploader` → Create, and select it.
2. **APIs & Services → Library** → search **YouTube Data API v3** → **Enable**.

### 2. OAuth consent screen (Google Auth Platform)
1. **APIs & Services → OAuth consent screen** (may be called **Google Auth Platform → Branding**) → Get started.
2. App name `Dadi Ke Kisse Uploader`, your email as support and contact email, Audience **External** → Create.
3. **Audience** → under Test users, **Add users** → your own Gmail.
4. **Publish the app** (Audience → **Publish app** → Confirm, status "In production").
   Important: while the app is in "Testing", Google expires the refresh token after 7 days and uploads stop.
   You don't need Google's verification for your own use; you'll just see an "unverified app" warning once in step 4.

### 3. OAuth client
1. **APIs & Services → Credentials → Create credentials → OAuth client ID** (or **Clients → Create client**).
2. Application type **Web application**, name `uploader`.
3. Under **Authorized redirect URIs** add exactly: `https://developers.google.com/oauthplayground`
4. Create → copy the **Client ID** and **Client secret**.

### 4. Get the refresh token (OAuth Playground)
1. Open https://developers.google.com/oauthplayground
2. Click the **gear icon** (top right) → tick **Use your own OAuth credentials** → paste the Client ID and Client secret → Close.
3. In the left box "Input your own scopes" paste `https://www.googleapis.com/auth/youtube` → **Authorize APIs**.
4. Sign in with the account that owns the channel. If it asks which channel, pick **Dadi Ke Kisse**. On "Google hasn't verified this app" click **Advanced → Go to Dadi Ke Kisse Uploader (unsafe)** → Continue/Allow.
5. Back in the Playground click **Exchange authorization code for tokens** → copy the **Refresh token**.

### 5. Add the secrets to this repo
GitHub → this repo → **Settings → Secrets and variables → Actions → New repository secret**, three times:

| Name | Value |
|---|---|
| `YT_CLIENT_ID` | the Client ID |
| `YT_CLIENT_SECRET` | the Client secret |
| `YT_REFRESH_TOKEN` | the Refresh token |

### 6. Test it
**Actions** tab → **Upload Shorts to YouTube** → **Run workflow**. A green run means the waiting Shorts were uploaded; their links are in `UPLOADS.md`. In YouTube Studio → Content they show as *Scheduled* until their publish time.

Also verify the channel's phone number (YouTube Studio → Settings → Channel → Feature eligibility) so custom thumbnails are allowed.

## Troubleshooting
- **"secrets are not set yet"** in the log: add the three secrets (step 5).
- **invalid_grant**: the refresh token expired or was revoked. Make sure the app is *In production* (step 2.4), then redo step 4 and update `YT_REFRESH_TOKEN`.
- **quotaExceeded**: the daily API quota is used up; the 6-hourly run retries after it resets (midnight Pacific time).
- **"The Google login is for channel ... not Dadi Ke Kisse"**: in step 4 you signed in to the wrong channel. Redo step 4, choose Dadi Ke Kisse, and update `YT_REFRESH_TOKEN`.
- **thumbnail skipped**: verify the channel's phone number, then set the cover by hand in YouTube Studio if needed.
- To change a publish time before upload, edit `publish_at` in that Short's `meta.json` (ISO time with offset, e.g. `2026-10-29T19:30:00+05:30`).
