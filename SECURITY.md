# Security Policy

## Supported Versions

| Version | Supported |
| :--- | :---: |
| 2.x | Yes |
| 1.x | No (legacy) |

## Reporting a Vulnerability

If you discover a security or privacy issue in OMRKit (for example, unsafe file handling in the API, path traversal, or metadata leakage), please open a private security advisory on GitHub or contact the maintainer directly rather than posting exploit details publicly.

## Sample Data & EXIF Privacy

All sample images shipped under `examples/` in OMRKit v2.0 have been stripped of EXIF/GPS metadata and contain non-personal test markings only. Users running OMRKit in production with student records should avoid exposing the Studio REST API on public networks without authentication and TLS termination.
