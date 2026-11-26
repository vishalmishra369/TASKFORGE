# GitHub setup (Vinayak does 1-4, everyone does 5)

## 1. Create the repo
1. github.com -> New repository -> owner: a GitHub **Organization** (e.g. `hedgeforge`) or Vinayak's account.
   Name `taskforge`. Public is simplest for judges; if private, add the organisers' accounts later.
   Do NOT tick "add README" (we already have one).
2. Settings -> Collaborators -> add Vishal, Nikhil, Yamini with **Write** role.

## 2. Push the code (from the unzipped project folder)
```bash
cd taskforge
git init -b main
git add .
git status                      # CHECK: no .env, no runs/, no work/ listed
git commit -m "chore: initial TaskForge skeleton"
git remote add origin https://github.com/<owner>/taskforge.git
git push -u origin main
```

## 3. Protect main
Settings -> Branches -> Add rule for `main`: require a pull request, 1 approval, status check `unit` must pass
(the CI in `.github/workflows/ci.yml` runs pytest + a secret scan). Edit `.github/CODEOWNERS` with real handles.

## 4. Plan the work
Issues -> create 8 issues, one per build step (titles from the guide), assign owners, milestone "Dec 20 finals".
Add a Project board (Todo / Doing / Review / Done).

## 5. Daily workflow for everyone
```bash
git clone https://github.com/<owner>/taskforge.git && cd taskforge
python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev,dashboard]"
cp .env.example .env            # put YOUR key; .env is git-ignored
git switch -c step5/critic-prompts       # one branch per task: stepN/short-name
# ...work, run: pytest -q
git add -p && git commit -m "feat(critic): reject untested-behaviour specs"
git push -u origin HEAD         # open a Pull Request, ask one teammate to review, squash-merge
git switch main && git pull     # start the next task from fresh main
```
Rules: small PRs, never push to main, never commit `.env`, `runs/`, `work/`.
Windows: use WSL2 + Docker Desktop (WSL integration on); the pipeline uses bash and git.

## 6. If a key is ever committed
Revoke/rotate it in Google AI Studio immediately. Deleting the file is NOT enough (git history keeps it).
Then purge history (`git filter-repo --path .env --invert-paths`) and force-push, or recreate the repo.
The submission checklist requires clean history.

## 7. Before the deadline
```bash
git grep -nE "AIza|sk-ant-|sk-[A-Za-z0-9]{20,}" $(git rev-list --all) | head   # must print nothing
taskforge export --out dist && git tag v1.0-submission && git push --tags
```
Then clone fresh on another machine and run the README exactly (a checklist item).
Keep click's license: tasks derive from BSD-3-Clause code; add a NOTICE file crediting Pallets.
