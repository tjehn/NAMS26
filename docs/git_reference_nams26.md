# Git Reference Guide — NAMS26
## Personal Reference and Supplemental Documentation

---

> **Scope:** This document covers Git concepts and workflows as they apply
> to the NAMS26 project specifically. It is written as both a personal
> reference and a teachable supplement for the project documentation.
> Examples use real NAMS26 paths and remote names throughout.

---

## 1. Core Concepts

### What Git Is

Git is a **distributed version control system**. Every copy of the repository
contains the full history — there is no single master copy that must always
be available. The Gitea server and GitHub are simply convenient shared
locations, not the authoritative source.

### The Three States of a File

Every file in a Git repository exists in one of three states:

```
Working Directory  →  Staging Area  →  Repository (committed history)
   (modified)           (staged)            (committed)
```

| State | What It Means |
|-------|---------------|
| **Modified** | You changed the file but haven't told Git about it yet |
| **Staged** | You've marked the change to go into the next commit |
| **Committed** | The change is safely recorded in Git history |

### Key Terminology

| Term | Definition |
|------|------------|
| **Repository (repo)** | The project directory tracked by Git, including all history |
| **Commit** | A snapshot of staged changes saved to history with a message |
| **Branch** | An independent line of development — NAMS26 uses `main` |
| **Remote** | A named reference to a repo hosted elsewhere (Gitea, GitHub) |
| **Push** | Send local commits up to a remote |
| **Pull** | Fetch commits from a remote and merge them locally |
| **Clone** | Copy a remote repo down to your local machine |
| **Stage** | Mark specific changes to include in the next commit |
| **Track** | Tell Git to watch a file for changes |
| **Untracked** | A file Git is aware of but not watching |

---

## 2. NAMS26 Repository Configuration

### Remotes

NAMS26 uses two remotes — one for development, one for production:

```
origin  →  http://192.168.1.12:8418/netauto/NAMS26.git  (Gitea — development)
github  →  https://github.com/tjehn/NAMS26.git          (GitHub — production)
```

View configured remotes at any time:

```bash
git remote -v
```

### Branches

NAMS26 uses a single branch:

```
main  →  primary and only branch
```

### Identity

Git identity configured on the NAMS workstation:

```bash
git config --global user.name "netauto"
git config --global user.email "tomjehn+netauto@gmail.com"
```

View current identity:

```bash
git config --global user.name
git config --global user.email
```

### Credential Storage

Credentials are stored after first use — no repeated prompts:

```bash
git config --global credential.helper store
```

Stored credentials live in `~/.git-credentials`.

---

## 3. Standard NAMS26 Workflow

### Day-to-Day Development

This is the sequence used after every working session:

```bash
# 1. Check what changed
git status

# 2. Review specific file changes (optional)
git diff <filename>

# 3. Stage all changes
git add -A

# 4. Review what is staged before committing
git status

# 5. Commit with a descriptive message
git commit -m "Module 02 — describe what changed and why"

# 6. Push to Gitea (development)
git push origin main
```

### Publishing to GitHub

Push to GitHub when the work is polished and ready for public consumption:

```bash
git push github main
```

### Commit Message Convention

Good commit messages follow this pattern for NAMS26:

```
Module 02 — short description of what changed

# Examples:
"Module 02 — add verify_eigrp_classic.py route validation"
"Module 02 — fix ios_abbrev() false positive on Et0/0"
"Module 02 — update verbal script Section 4 configure walkthrough"
"Root — update README.md module status table"
"Gitignore — exclude module logs and rendered configs"
```

---

## 4. Common Operations

### Check Status

```bash
git status
```

Shows:
- Files staged for the next commit
- Files modified but not staged
- Untracked files Git doesn't know about yet

### See What Changed

```bash
# Changes in working directory (not yet staged)
git diff

# Changes that are staged (about to be committed)
git diff --staged

# Changes in a specific file
git diff modules/02_eigrp_netmiko/scripts/verify_eigrp_classic.py
```

### Stage Files

```bash
# Stage everything (most common)
git add -A

# Stage a specific file
git add modules/02_eigrp_netmiko/scripts/configure_eigrp_classic.py

# Stage a specific directory
git add modules/02_eigrp_netmiko/

# Stage all Python files
git add "*.py"
```

### Unstage a File

```bash
# Remove from staging area without discarding changes
git restore --staged <filename>

# Unstage everything
git reset HEAD
```

### View Commit History

```bash
# Full history
git log

# Compact one-line format
git log --oneline

# Last 5 commits
git log --oneline -5

# History for a specific file
git log --oneline modules/02_eigrp_netmiko/scripts/verify_eigrp_classic.py
```

### View a Specific Commit

```bash
# Show what changed in a specific commit (use hash from git log)
git show 99f0144
```

---

## 5. Managing What Gets Committed — `.gitignore`

### NAMS26 `.gitignore` Principles

Three categories of files are excluded from the NAMS26 repository:

**1. Generated output — never commit these:**
```
modules/*/configs/*.cfg     # Rendered per-device configs
modules/*/configs/*.conf
modules/logs/               # Verify script session logs
logs/                       # Configure script session logs
```

**2. Development environment — not part of the project:**
```
.idea/                      # PyCharm project files
.venv/                      # Python virtual environment
__pycache__/                # Python bytecode cache
*.pyc                       # Compiled Python files
```

**3. Security — never commit credentials:**
```
ansible/vault/*.yml         # Ansible vault files
*.vault                     # Any vault files
vault_password.txt          # Vault password files
```

### Checking What `.gitignore` Is Excluding

```bash
# See all ignored files
git status --ignored

# Check if a specific file is ignored and why
git check-ignore -v modules/02_eigrp_netmiko/configs/R1_eigrp_classic.cfg
```

### Tracking Empty Directories — `.gitkeep`

Git does not track empty directories. NAMS26 uses `.gitkeep` placeholder
files to preserve directory structure in the repo:

```bash
# Create a placeholder to track an empty directory
touch modules/02_eigrp_netmiko/configs/.gitkeep
git add modules/02_eigrp_netmiko/configs/.gitkeep
```

---

## 6. Working with Remotes

### Push to a Specific Remote

```bash
# Push to Gitea (development — use frequently)
git push origin main

# Push to GitHub (production — use when publish-ready)
git push github main
```

### Pull from a Remote

```bash
# Pull latest changes from Gitea
git pull origin main

# Pull with rebase (cleaner history — preferred)
git pull origin main --rebase
```

### Add a New Remote

```bash
git remote add <name> <url>

# Example — adding GitHub
git remote add github https://github.com/tjehn/NAMS26.git
```

### Change a Remote URL

```bash
git remote set-url origin http://192.168.1.12:8418/netauto/NAMS26.git
```

### Remove a Remote

```bash
git remote remove <name>
```

---

## 7. Undoing Things

### Undo Changes in a File (not yet staged)

```bash
# Discard working directory changes — restores file to last commit
git restore <filename>
```

### Undo a Staged Change

```bash
# Unstage without losing changes
git restore --staged <filename>
```

### Amend the Last Commit

```bash
# Change the commit message of the most recent commit
git commit --amend -m "corrected commit message"

# Add a forgotten file to the last commit
git add forgotten_file.py
git commit --amend --no-edit
```

> **Note:** Only amend commits that have not been pushed to a remote yet.
> Amending a pushed commit requires a force push.

### Force Push (use with caution)

```bash
# Overwrite remote with local state — safe on private development repos
git push origin main --force
```

> Force push is safe on the NAMS26 Gitea repo because it is a private
> single-user development repository. Never force push to a shared repo
> without team coordination.

---

## 8. Module Development Workflow

When starting a new module, follow this sequence:

```bash
# 1. Confirm clean state before starting
git status

# 2. Create the module directory structure
mkdir -p modules/03_ospf1_napalm/{configs,data,diagrams,docs,scripts,templates,utils,verbal_script}

# 3. Add .gitkeep to configs/ so the directory is tracked
touch modules/03_ospf1_napalm/configs/.gitkeep

# 4. Work on the module files...

# 5. Stage and commit at logical checkpoints — not just at the end
git add modules/03_ospf1_napalm/
git commit -m "Module 03 — add OSPF Classic Mode YAML and Jinja2 template"

# 6. Continue working, committing at each meaningful milestone
git commit -m "Module 03 — add configure_ospf_classic.py with dry-run support"
git commit -m "Module 03 — add verify_ospf_classic.py check_neighbors function"

# 7. Push to Gitea after each session
git push origin main

# 8. Push to GitHub when module is complete and validated
git push github main
```

### Recommended Commit Points for Each Module

| Milestone | Suggested Commit Message |
|-----------|--------------------------|
| YAML complete | `Module XX — add <protocol> YAML inventory` |
| Template complete | `Module XX — add Jinja2 template` |
| Configure script complete | `Module XX — add configure script` |
| Verify script complete | `Module XX — add verify script` |
| Troubleshoot script complete | `Module XX — add troubleshoot script` |
| Lab validated | `Module XX — lab validation complete, all checks passing` |
| Documentation complete | `Module XX — add README, verbal script, and docs` |
| Module complete | `Module XX — <Protocol>/<Tool> complete` |

---

## 9. Quick Reference Card

### Most Used Commands

```bash
git status                          # What is the current state?
git diff                            # What changed (unstaged)?
git diff --staged                   # What is about to be committed?
git add -A                          # Stage everything
git commit -m "message"             # Commit staged changes
git push origin main                # Push to Gitea
git push github main                # Push to GitHub
git log --oneline -10               # Last 10 commits
git pull origin main --rebase       # Pull latest from Gitea
```

### NAMS26 Remote URLs

```
Gitea:  http://192.168.1.12:8418/netauto/NAMS26.git
GitHub: https://github.com/tjehn/NAMS26.git
```

### File Color Coding in PyCharm

| Color | Meaning |
|-------|---------|
| **Red** | Untracked — Git does not know about this file |
| **Green** | Staged — included in the next commit |
| **Blue** | Modified and tracked — changed since last commit |
| **White/Grey** | Committed and unchanged |

---

## 10. Troubleshooting

### "Updates were rejected because the remote contains work you do not have"

```bash
# Pull first, then push
git pull origin main --rebase
git push origin main
```

### "CONFLICT" during rebase or pull

```bash
# Accept our local version (most common for NAMS26)
git add <conflicted-file>
git rebase --continue

# Or abort and start over
git rebase --abort
```

### "pathspec did not match any files"

The file path is wrong or the file doesn't exist at that path. Verify with:

```bash
ls <directory>
```

### Accidentally committed the wrong files

```bash
# Remove a file from the last commit without deleting it
git rm --cached <filename>
git commit --amend --no-edit
```

### Check if a file is being ignored

```bash
git check-ignore -v <filename>
```

---

*NAMS26 — Network Automation Management Station 2026*
*Git Reference Guide — netauto / tjehn*
