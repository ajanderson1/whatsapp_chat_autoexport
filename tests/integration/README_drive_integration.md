# Real-Drive Integration Test

This directory contains a thread-safety test that exercises `GoogleDriveClient`
against real Google Drive, not mocks. It is gated behind the pytest marker
`requires_drive` and is **not run in CI**. You run it manually before merging
changes to `GoogleDriveClient`.

## One-time setup

1. Authenticate the Drive client as you normally would
   (`poetry run whatsapp` → settings → Google Drive connect).
2. Create a folder on Google Drive named `whatsapp-drive-integration-test`
   (or any name). Upload ~10 small binary files to it — any files will do;
   100 KB – 1 MB each is fine. Note the folder ID from the Drive URL
   (`https://drive.google.com/drive/folders/<THIS_PART>`).
3. Set the env var before running the test:

   ```bash
   export DRIVE_INTEGRATION_FIXTURE_FOLDER_ID=<the folder id>
   ```

## Running

```bash
poetry run pytest tests/integration/test_drive_client_concurrency.py -m requires_drive -v
```

The test will:
- Connect to Drive using your local credentials.
- List files in the fixture folder.
- Download all fixture files concurrently (4 worker threads, multiple rounds)
  and assert every download succeeded with no SSL or HTTP errors.

Expected runtime: 30s – 2min depending on file sizes and network.

## When to run

- Before merging any change to `whatsapp_chat_autoexport/google_drive/drive_client.py`.
- After any dependency bump of `google-api-python-client`, `httplib2`, or OpenSSL
  (including Python upgrades).
