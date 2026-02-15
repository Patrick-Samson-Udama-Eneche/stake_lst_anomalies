# Secrets Directory

This directory contains sensitive credentials and API keys for the LST Modeling Project.

## ⚠️ SECURITY NOTICE

**All files in this directory are git-ignored and should NEVER be committed to version control.**

## Required Files

### 1. `gee_service_account.json`
Google Earth Engine service account credentials for accessing GEE API.

**Setup:**
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or use an existing one) and enable the **Earth Engine API**
3. Go to **IAM & Admin → Service Accounts** → create a new service account
4. Generate a JSON key and download it
5. Place the file here: `secrets/gee_service_account.json`
6. Register the service account at [https://signup.earthengine.google.com/#!/service_accounts](https://signup.earthengine.google.com/#!/service_accounts)

**Format:** See `gee_service_account.json.example` for the expected JSON structure.

**Example file:** `gee_service_account.json.example`

---

### 2. `eumetsat_credentials.json`
EUMETSAT Data Store credentials for accessing MSG SEVIRI LST data.

**Setup:**
1. Register at https://eoportal.eumetsat.int/
2. Obtain consumer key and consumer secret
3. Create `eumetsat_credentials.json` based on the example below

**Format:**
```json
{
  "consumer_key": "your_consumer_key_here",
  "consumer_secret": "your_consumer_secret_here"
}
```

**Example file:** See `eumetsat_credentials.json.example`

---

## File Checklist

Before running notebooks that require external data access, ensure:

- [ ] `gee_service_account.json` exists and is valid
- [ ] `eumetsat_credentials.json` exists and contains valid credentials
- [ ] All credential files are listed in `.gitignore`
- [ ] No credential files are tracked by git (run: `git ls-files | grep secrets/`)

---

## Troubleshooting

**Error: "Service account key not found"**
- Check that `gee_service_account.json` exists in this directory
- Verify file permissions (must be readable)

**Error: "EUMETSAT authentication failed"**
- Verify credentials in `eumetsat_credentials.json` are correct
- Check that your EUMETSAT account is active
- Ensure no extra whitespace in key/secret values

---

## Migration from Old Location

If you previously stored credentials in `data/inputs/`, move them here:

```bash
# From project root
mv data/inputs/gee_service_account.json secrets/
```

The `config.py` file includes fallback logic for backward compatibility.

---

**Last Updated:** January 2026
