# Contributing to Duckbot

Open a Discussion before substantial work. Bug reports should include a minimal,
reproducible case; support questions belong in Discussions rather than Issues.

All commits require Developer Certificate of Origin sign-off:

```bash
git commit -s -m "your message"
```

The sign-off certifies that you wrote the contribution or may submit it under
Apache-2.0. Duckbot uses a DCO, not a Contributor Licence Agreement.

Include tests for changed behavior. Privacy detection changes must include the measured
Hong Kong corpus result. New dependencies must state their exact version and licence;
AGPL, SSPL, BSL, Elastic/source-available, and non-commercial dependencies cannot enter
the Apache-2.0 core or installer.
