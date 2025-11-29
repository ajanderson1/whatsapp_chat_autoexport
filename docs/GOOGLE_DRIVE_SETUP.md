# Google Drive API Setup Guide

This guide will help you set up Google Drive API access for the WhatsApp Chat Auto-Export tool.

## Overview

The tool needs OAuth 2.0 credentials to access your Google Drive. This is a one-time setup process.

## Step-by-Step Setup

### 1. Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Sign in with your Google account
3. Click **Select a Project** → **New Project**
4. Enter a project name (e.g., "WhatsApp Chat Export")
5. Click **Create**

### 2. Enable Google Drive API

1. In your project, go to **APIs & Services** → **Library**
2. Search for "Google Drive API"
3. Click on **Google Drive API**
4. Click **Enable**

### 3. Create OAuth 2.0 Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **+ CREATE CREDENTIALS** → **OAuth client ID**
3. If prompted, configure the OAuth consent screen:
   - User Type: **External**
   - App name: "WhatsApp Chat Export"
   - User support email: Your email
   - Developer contact: Your email
   - Click **Save and Continue**
   - Skip Scopes (click **Save and Continue**)
   - Add your email as a test user
   - Click **Save and Continue**
4. Back on Create OAuth client ID:
   - Application type: **Desktop app**
   - Name: "WhatsApp Chat Export Desktop"
   - Click **Create**
5. Click **Download JSON** (the download icon)

### 4. Save Credentials File

1. Rename the downloaded file to `client_secrets.json`
2. Create the credentials directory:
   ```bash
   mkdir -p ~/.whatsapp_export
   ```
3. Move the file to the credentials directory:
   ```bash
   mv ~/Downloads/client_secrets.json ~/.whatsapp_export/
   ```

### 5. Verify Setup

Check that the file exists:
```bash
ls -la ~/.whatsapp_export/client_secrets.json
```

You should see the file listed.

## First Authentication

Run the authentication command:

```bash
poetry run whatsapp-drive auth
```

This will:
1. Open your default browser
2. Ask you to log in to Google
3. Ask you to authorize the application
4. Save the access token to `~/.whatsapp_export/google_credentials.json`

**Important**: The first time you authenticate, you may see a warning that the app is not verified. This is normal for personal projects. Click **Advanced** → **Go to [Your App Name] (unsafe)** to continue.

## Testing the Setup

### List WhatsApp Exports

```bash
poetry run whatsapp-drive list
```

### Download Exports

```bash
poetry run whatsapp-drive download ~/Downloads/WhatsApp
```

### Download and Delete from Google Drive

```bash
poetry run whatsapp-drive download ~/Downloads/WhatsApp --delete-after
```

## Troubleshooting

### "client_secrets.json not found"

Make sure you:
1. Downloaded the OAuth 2.0 credentials JSON file
2. Renamed it to `client_secrets.json`
3. Placed it in `~/.whatsapp_export/`

### "App is not verified" warning

This is normal for personal projects. Click **Advanced** → **Go to [Your App Name] (unsafe)** to proceed.

### "Access blocked: This app's request is invalid"

Make sure you:
1. Enabled the Google Drive API in your project
2. Downloaded credentials for a **Desktop app** (not Web application)

### Token expired or invalid

Revoke and re-authenticate:
```bash
poetry run whatsapp-drive revoke
poetry run whatsapp-drive auth
```

## File Locations

- **OAuth client secrets**: `~/.whatsapp_export/client_secrets.json`
- **Access token** (auto-generated): `~/.whatsapp_export/google_credentials.json`

## Security Notes

1. **Keep `client_secrets.json` private** - Don't commit it to git
2. **Keep `google_credentials.json` private** - This contains your access token
3. The `.whatsapp_export` directory is already in `.gitignore`
4. These credentials only have access to your Google Drive (read/write)

## Revoking Access

To revoke the application's access to your Google Drive:

1. Using the CLI:
   ```bash
   poetry run whatsapp-drive revoke
   ```

2. In Google Account settings:
   - Go to [Google Account Security](https://myaccount.google.com/security)
   - Click **Third-party apps with account access**
   - Find "WhatsApp Chat Export"
   - Click **Remove Access**

## Next Steps

Once setup is complete, you can use the Google Drive integration in the pipeline:

```bash
# The full pipeline will eventually:
# 1. Export chats to Google Drive (existing functionality)
# 2. Download from Google Drive (Phase 2 - new!)
# 3. Delete from Google Drive (Phase 2 - new!)
# 4. Process locally
# 5. Transcribe audio/video
# 6. Organize output
```
