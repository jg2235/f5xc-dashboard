# Security Policy

## Reporting a Vulnerability

If you've discovered a security vulnerability, please report it via GitHub's
private vulnerability reporting:

**[Report a vulnerability →](../../security/advisories/new)**

Or navigate manually:
1. Open the repository's **Security** tab on GitHub
2. Click **Report a vulnerability**
3. Fill in the advisory form

### What to include

- A clear description of the vulnerability
- Steps to reproduce, or a proof-of-concept
- The version (commit SHA or tag) where you observed it
- Logs / stack traces with credentials and tokens redacted
- Your assessment of impact (data exposure, RCE, auth bypass, etc.)

### What to expect

- Acknowledgement within 5 business days
- A coordinated disclosure timeline if confirmed
- Public credit in the resulting advisory unless you prefer anonymity

### Out of scope

- Vulnerabilities in F5 Distributed Cloud itself — report to F5 SIRT directly
- Issues requiring physical access to a developer machine
- Social engineering attacks against project maintainers

## Supported versions

Only the most recent minor release receives security fixes. See `CHANGELOG.md`.
