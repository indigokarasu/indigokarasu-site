# indigokarasu.com

Source for [indigokarasu.com](https://indigokarasu.com).

Static HTML/CSS site. No build step, no dependencies, no frameworks.

## Structure

```
index.html          # Homepage
style.css           # All styles
essays/
  invisible-infrastructure.html
  tools-should-disappear.html
  owning-your-stack.html
```

## Deploy

```bash
bash deploy.sh
```

Deploys to DreamHost via SFTP. Credentials stored in `/root/.dreamhost_credentials`.

## Content Rules

- No em dashes
- No AI-tell patterns (run through Vibes + Humanizer before publishing)
- No claims that can't be verified
- No references to private projects or people
