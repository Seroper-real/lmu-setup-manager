# Display-only release marker (shown in the sidebar). The CI release workflow
# overwrites this file with the git tag's version at build time (see
# .github/workflows/release.yml), so it never needs to be bumped by hand.
# "9.9.9" is a fixed local-dev placeholder - always sorts above any real
# release, which keeps it out of the way. It does NOT drive the DB
# schema-migration gate: that converges to the highest version in
# domain.migrations.catalog.CATALOG instead, so adding a migration during
# development never requires touching this file.
APP_VERSION = "9.9.9"
