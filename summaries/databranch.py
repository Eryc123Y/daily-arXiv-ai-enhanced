"""Read and write the `data` branch without checking it out.

Commits are built with git plumbing on a temporary index, so the caller's
working tree and current branch are never touched, and no blob has to be
present locally (works on a shallow, blob-less clone in Actions). Every
publish regenerates `assets/file-list.txt` from all jsonl files on the
branch and retries on top of the newest remote state if a push races.
"""

import os
import subprocess
import tempfile
from dataclasses import dataclass

FILE_LIST = "assets/file-list.txt"


@dataclass(frozen=True)
class Identity:
    name: str
    email: str


BOT_IDENTITY = Identity("github-actions[bot]", "41898282+github-actions[bot]@users.noreply.github.com")


def resolve_identity(repo_dir, env):
    """Who data commits are made as.

    COMMIT_NAME and COMMIT_EMAIL (repository variables in Actions, or the
    environment locally) win; otherwise Actions commits as the
    github-actions bot and a local run as the clone's git identity.
    """
    name = (env.get("COMMIT_NAME") or "").strip()
    email = (env.get("COMMIT_EMAIL") or "").strip()
    if name and email:
        return Identity(name, email)
    if env.get("GITHUB_ACTIONS") == "true":
        return BOT_IDENTITY

    def config(key):
        result = subprocess.run(["git", "config", key], cwd=str(repo_dir), capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else ""

    name, email = config("user.name"), config("user.email")
    return Identity(name, email) if name and email else BOT_IDENTITY


class PublishError(RuntimeError):
    pass


class DataBranch:
    def __init__(self, repo_dir, remote="origin", branch="data", fetch_args=()):
        self.repo_dir = str(repo_dir)
        self.remote = remote
        self.branch = branch
        self.fetch_args = tuple(fetch_args)
        self.ref = f"refs/remotes/{remote}/{branch}"
        self._exists = None

    def _git(self, *args, env=None, input=None, check=True):
        return subprocess.run(
            ["git", *args],
            cwd=self.repo_dir,
            env=env,
            input=input,
            capture_output=True,
            check=check,
        )

    def fetch(self):
        """Update the remote-tracking ref; return whether the branch exists."""
        heads = self._git("ls-remote", "--heads", self.remote, self.branch).stdout
        self._exists = bool(heads.strip())
        if self._exists:
            refspec = f"+refs/heads/{self.branch}:{self.ref}"
            self._git("fetch", "--quiet", *self.fetch_args, self.remote, refspec)
        return self._exists

    def _branch_exists(self):
        if self._exists is None:
            self._exists = self._git("rev-parse", "--verify", "--quiet", self.ref, check=False).returncode == 0
        return self._exists

    def read(self, path):
        """Text of `path` on the fetched branch, or None if the tree has no such file.

        A file that is listed but cannot be loaded (a failed lazy blob fetch
        in a blob-less clone) raises, so callers never mistake it for an
        absent file and overwrite it.
        """
        if not self._branch_exists():
            return None
        if not self._git("ls-tree", self.ref, "--", path).stdout.strip():
            return None
        return self._git("show", f"{self.ref}:{path}").stdout.decode("utf-8")

    def list_files(self, prefix):
        if not self._branch_exists():
            return []
        out = self._git("ls-tree", "-r", "--name-only", self.ref, "--", prefix).stdout
        return sorted(out.decode("utf-8").splitlines())

    def _build_commit(self, files, message, identity):
        exists = self._branch_exists()
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "GIT_INDEX_FILE": os.path.join(tmp, "index")}
            if exists:
                self._git("read-tree", self.ref, env=env)
            for path, content in files.items():
                self._stage(path, content, env)
            listed = self._git("ls-files", "--", "data/", env=env).stdout.decode("utf-8")
            names = sorted(p.split("/")[-1] for p in listed.splitlines() if p.endswith(".jsonl"))
            self._stage(FILE_LIST, "".join(f"{n}\n" for n in names), env)
            tree = self._git("write-tree", env=env).stdout.decode().strip()

        if exists and tree == self._git("rev-parse", f"{self.ref}^{{tree}}").stdout.decode().strip():
            return None
        commit_env = {
            **os.environ,
            "GIT_AUTHOR_NAME": identity.name,
            "GIT_AUTHOR_EMAIL": identity.email,
            "GIT_COMMITTER_NAME": identity.name,
            "GIT_COMMITTER_EMAIL": identity.email,
        }
        parents = ["-p", self.ref] if exists else []
        out = self._git("commit-tree", tree, *parents, "-m", message, env=commit_env)
        return out.stdout.decode().strip()

    def _stage(self, path, content, env):
        data = content.encode("utf-8") if isinstance(content, str) else content
        blob = self._git("hash-object", "-w", "--stdin", input=data).stdout.decode().strip()
        self._git("update-index", "--add", "--cacheinfo", f"100644,{blob},{path}", env=env)

    def publish(self, files, message, identity=None, attempts=4, on_before_push=None):
        """Commit `files` on top of the remote branch and push.

        `files` is {path: text} or a callable(DataBranch) -> {path: text},
        re-evaluated on each attempt so content derived from the branch is
        rebuilt on the newest state. Returns the new commit, or None when the
        branch already had identical content. `on_before_push` is a test seam.
        """
        identity = identity or resolve_identity(self.repo_dir, os.environ)
        last_error = ""
        for _ in range(attempts):
            self.fetch()
            content = files(self) if callable(files) else files
            commit = self._build_commit(content, message, identity)
            if commit is None:
                return None
            if on_before_push:
                on_before_push()
            push = self._git(
                "push", "--quiet", self.remote, f"{commit}:refs/heads/{self.branch}", check=False
            )
            if push.returncode == 0:
                self._git("update-ref", self.ref, commit)
                self._exists = True
                return commit
            last_error = push.stderr.decode("utf-8", "replace").strip()
        raise PublishError(f"Could not push to {self.branch} after {attempts} attempts: {last_error}")
