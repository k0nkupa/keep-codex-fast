# Release Checklist

## NPM

1. Confirm package contents:

   ```bash
   npm run check
   npm test
   npm run pack:dry
   ```

2. Publish:

   ```bash
   npm publish --access public
   ```

3. Install test:

   ```bash
   npm i -g keep-codex-fast
   keep-codex-fast setup --dry-run
   ```

## Skills CLI

The skill is published from the public GitHub repo layout:

```text
skills/keep-codex-fast/SKILL.md
```

Install command after the repo is public:

```bash
npx skills add k0nkupa/keep-codex-fast --skill keep-codex-fast -g -y --copy
```

Use `--copy` because this skill includes a maintenance script that should remain available even if the source checkout moves.

## Homebrew

For development installs from the checkout:

```bash
brew install --HEAD ./Formula/keep-codex-fast.rb
```

For public stable installs, Homebrew expects a tap repo. The short command `brew tap k0nkupa/keep-codex-fast` maps to a GitHub repository named `k0nkupa/homebrew-keep-codex-fast`.

1. Create GitHub release tag `v0.1.0`.
2. Download or calculate the release tarball checksum:

   ```bash
   curl -L -o keep-codex-fast-v0.1.0.tar.gz \
     https://github.com/k0nkupa/keep-codex-fast/archive/refs/tags/v0.1.0.tar.gz
   shasum -a 256 keep-codex-fast-v0.1.0.tar.gz
   ```

3. Replace the placeholder `sha256` in `Formula/keep-codex-fast.rb`.
4. Create or update the tap repo:

   ```bash
   gh repo create k0nkupa/homebrew-keep-codex-fast --public
   ```

5. Copy `Formula/keep-codex-fast.rb` into the tap repo as `Formula/keep-codex-fast.rb`, commit, and push.
6. Users can install from the tap:

   ```bash
   brew tap k0nkupa/keep-codex-fast
   brew install keep-codex-fast
   ```
