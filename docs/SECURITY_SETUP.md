# Security Setup Guide

## 🔒 Protecting Sensitive Data

This document outlines how sensitive credentials in this project are securely managed.

### Initial Setup for New Users

1. **Obtain your Google Earth Engine service account JSON file**
   - Contact the project administrator
   - Download from Google Cloud Console
   - Save it securely outside this repository

2. **Place the credentials file:**
   ```bash
   # Option A: Use default location (ensure it's in .gitignore)
   mkdir -p data/inputs
   cp /path/to/your/gee_service_account.json data/inputs/
   
   # Option B: Store outside repository (recommended)
   # Place it anywhere secure, e.g., ~/.config/gee/service_account.json
   ```

3. **Configure environment variable (Option B):**
   ```bash
   # Linux/Mac - Add to ~/.bashrc or ~/.zshrc
   export GEE_SERVICE_JSON="/path/to/your/gee_service_account.json"
   export GEE_PROJECT_ID="your-project-id"
   
   # Windows PowerShell - Add to $PROFILE
   $env:GEE_SERVICE_JSON="C:\path\to\your\gee_service_account.json"
   $env:GEE_PROJECT_ID="your-project-id"
   ```

4. **Or create `.env` file (never commit this!):**
   ```bash
   cp .env.example .env
   # Edit .env and add:
   # GEE_SERVICE_JSON=/absolute/path/to/gee_service_account.json
   # GEE_PROJECT_ID=your-project-id
   ```


### Verification

Check that sensitive files are not tracked:
```bash
git status --ignored
git ls-files | grep -i "service_account\|credentials\|secret"
```

The `gee_service_account.json` should appear in the "ignored" list, not in tracked files.

---
**Last Updated:** January 2026
