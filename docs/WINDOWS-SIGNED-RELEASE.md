# Publishing a signed Windows preview

Public distribution is blocked until an approved, publicly trusted code-signing
identity is available. Website HTTPS, Apple development certificates, self-signed
certificates, Git commit signatures and updater signatures do not meet this need.
A signed build remains a development preview; signing is not product acceptance or
a promise that SmartScreen will never display a warning.

## Signing preparation

Use the legal publisher **IGEARS TECHNOLOGY LIMITED**, subject to the exact identity
validated by the certificate authority. Obtain a code-signing certificate with its
key held in a supported hardware token or cloud HSM. Do not export the signing key
into GitHub or the repository. No certificate purchase or account enrolment has
been performed by this change.

The prepared build path supports a Windows Current User certificate store backed
by the issuer's KSP. DigiCert KeyLocker is one documented example. Configure the
issuer's client tools, approved account and certificate synchronisation first.
The actual provider connection and iGears identity still need acceptance before use.
Providers without a Windows KSP need an issuer-specific signing adapter.

Official references, checked 26 September 2026:

- [Windows signing options and current geographical restrictions](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options)
- [DigiCert KeyLocker Windows KSP integration](https://docs.digicert.com/en/digicert-keylocker/ci-cd-integrations-and-deployment-pipelines/scripts/github/scripts-for-signing-using-ksp-library-on-github.html)
- [Tauri custom signing command](https://tauri.app/distribute/sign/windows/)

Azure Artifact Signing currently lists US/Canada/EU/UK organisations for public
trust onboarding; a Hong Kong company should not assume eligibility based on its
owner's residence. Confirm the legal entity and current vendor eligibility.

## Build and verify

On a clean, reviewed Windows checkout, prepare the same Python, PyInstaller, Rust,
Node and Windows SDK dependencies used by `.github/workflows/desktop.yml`. Sign in
to the approved hardware/cloud provider outside the repository. Set these two
**non-secret** identity values to the issued certificate, not an invented identity:

```powershell
$env:DUCKBOT_SIGNER_THUMBPRINT = 'THE_40_HEX_CHARACTERS_FROM_THE_APPROVED_CERTIFICATE'
$env:DUCKBOT_SIGNER_NAME = 'THE_EXACT_CERTIFICATE_PUBLISHER_NAME'
./packages/duckbot-shell/scripts/build-signed-windows.ps1
```

The script rebuilds and signs the sidecar before placing it in the bundle. Tauri's
custom signing command signs the shell and installer during packaging. Every
signing operation uses SHA-256 and a timestamp, verifies the certificate fingerprint
and publisher, and stops on failure. Credentials are handled by the provider;
the script never imports private keys or modifies trusted root certificates.

The release gate verifies the installer before executing it, checks the installed
shell and sidecar signatures before starting them, and runs the existing installed
privacy/task and sustained desktop startup checks. Only after all checks pass does
it write the installer, `SHA256SUMS` and `verification.json` to a new
`dist/windows-release` directory. A previous output directory is never overwritten.
Acceptance metadata records the source commit; it is not a reproducible-build
attestation. Keep the build logs and trusted source provenance with it.

`windows-release-checks` tests the native verification logic against Microsoft's
already signed executable plus wrong-publisher, wrong-certificate, unsigned and
tampered fixtures. These tests prove gate behaviour, **not** possession of an
iGears certificate or a successfully signed Duckbot build.

The older optional PFX step in `desktop.yml` signs only the outer installer. Its
output cannot qualify for public signed distribution unless the installed shell
and sidecar also pass this release gate. Normal CI artifacts remain development
artifacts, not public downloads.

## Publication sequence

1. Require all source, licence and Windows checks on the exact release commit to
   pass. Keep the current source-only release unchanged while signing is pending.
2. Verify the candidate with the approved certificate on Windows and retain its
   source provenance, signed payload evidence and checksum. Never substitute the
   earlier unsigned installer.
3. Create a new GitHub **prerelease** for the reviewed commit. Upload only the verified
   installer, checksum and verification record. Clearly describe echo mode, real
   model setup, supported Windows architecture and current product limitations.
4. Download the public asset anonymously and re-check its SHA-256 and Authenticode
   signature. Check installation from that downloaded copy.
5. Update both websites in both languages with the exact direct asset URL, version,
   Windows x64 label, checksum and release notes. Download and use require no signup.
6. Validate the live links and responsive pages, retaining deployment backups.

Do not activate a download button, mark a release as signed, or describe this
preparation as a published installer before those steps have actually succeeded.
