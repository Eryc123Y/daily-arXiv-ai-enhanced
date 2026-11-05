import subprocess

import pytest

TEST_GIT = ["-c", "user.name=Test", "-c", "user.email=test@example.invalid", "-c", "init.defaultBranch=main"]


def git(cwd, *args):
    result = subprocess.run(
        ["git", *TEST_GIT, *args], cwd=cwd, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


@pytest.fixture
def remote_and_clone(tmp_path):
    """A bare 'origin' with a main branch, and a fresh clone of it."""
    remote = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    clone = tmp_path / "clone"
    git(tmp_path, "init", "--bare", str(remote))
    git(tmp_path, "init", str(seed))
    (seed / "README.md").write_text("main\n")
    git(seed, "add", "README.md")
    git(seed, "commit", "-m", "init")
    git(seed, "push", str(remote), "main")
    git(tmp_path, "clone", str(remote), str(clone))
    return remote, clone


def seed_data_branch(tmp_path, remote, files):
    """Push a data branch holding `files` ({path: text}) to `remote`."""
    work = tmp_path / "data-seed"
    git(tmp_path, "init", str(work))
    for path, text in files.items():
        target = work / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    git(work, "add", ".")
    git(work, "commit", "-m", "seed data")
    git(work, "push", str(remote), "HEAD:refs/heads/data")
    return work
