# Task: Dev Requirements for Hot Reload

- Objective: Separate dev-only tools from production dependencies.
- Owner: Dev
- Dependencies: pip
- Success Criteria:
  - Dev tools installed only for development builds or local runs.

## Steps

1) Create `requirements-dev.txt`
```
-r requirements.txt
watchfiles
# or watchdog if preferred/required
# watchdog
python-dotenv
```

2) Local install (optional)
```powershell
python -m pip install -r requirements-dev.txt
```

3) Docker (optional)
- For a dev image, add a build arg or stage that installs `requirements-dev.txt`.
- Keep production images on `requirements.txt` only.

## Validation
- Confirm `watchfiles`/`watchdog` and `python-dotenv` are available locally without polluting production builds.
