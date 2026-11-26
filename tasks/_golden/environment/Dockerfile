FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git less \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
# Pin to base_commit, then drop remotes/tags/branches and unreachable objects so a solver
# cannot read upstream's future commits (which may already contain the feature).
RUN git clone https://github.com/pallets/click.git . \
    && git checkout cf19179e8e2fd54c601378cec9e0d21bb12b6fb1 \
    && git remote remove origin \
    && git for-each-ref --format='%(refname)' | xargs -r -n1 git update-ref -d \
    && git reflog expire --expire=now --all \
    && git gc --prune=now -q
RUN pip install --no-cache-dir -e . pytest pytest-json-report
