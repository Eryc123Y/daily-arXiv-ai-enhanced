from conftest import git, seed_data_branch

from summaries.databranch import DataBranch, Identity

BOT = Identity("Eryc123Y", "145822832+Eryc123Y@users.noreply.github.com")


def show(remote, path):
    return git(remote, "show", f"data:{path}")


def test_publish_creates_the_branch_with_files_and_file_list(remote_and_clone):
    remote, clone = remote_and_clone
    branch = DataBranch(clone)

    commit = branch.publish({"data/2026-10-30.jsonl": '{"id": "1"}\n'}, "update: 2026-10-30", BOT)

    assert commit
    assert show(remote, "data/2026-10-30.jsonl") == '{"id": "1"}'
    assert show(remote, "assets/file-list.txt") == "2026-10-30.jsonl"
    author = git(remote, "log", "-1", "--format=%an <%ae>|%cn <%ce>", "data")
    assert author == f"{BOT.name} <{BOT.email}>|{BOT.name} <{BOT.email}>"


def test_publish_keeps_existing_files_and_lists_every_jsonl(tmp_path, remote_and_clone):
    """Upstream rewrote file-list.txt with only the newest day, breaking date ranges."""
    remote, clone = remote_and_clone
    seed_data_branch(
        tmp_path,
        remote,
        {
            "README.md": "# Data Branch\n",
            "data/2026-10-28.jsonl": "{}\n",
            "data/2026-10-28.md": "old markdown\n",
            "data/2026-10-28_AI_enhanced_Chinese.jsonl": "{}\n",
            "assets/file-list.txt": "2026-10-28.jsonl\n",
        },
    )
    parent = git(remote, "rev-parse", "data")

    DataBranch(clone).publish({"data/2026-10-30.jsonl": "{}\n"}, "update", BOT)

    assert git(remote, "rev-parse", "data~1") == parent
    assert show(remote, "data/2026-10-28.md") == "old markdown"
    assert show(remote, "assets/file-list.txt").splitlines() == [
        "2026-10-28.jsonl",
        "2026-10-28_AI_enhanced_Chinese.jsonl",
        "2026-10-30.jsonl",
    ]


def test_publish_without_changes_makes_no_commit(tmp_path, remote_and_clone):
    remote, clone = remote_and_clone
    branch = DataBranch(clone)
    branch.publish({"data/2026-10-30.jsonl": "{}\n"}, "first", BOT)
    head = git(remote, "rev-parse", "data")

    assert branch.publish({"data/2026-10-30.jsonl": "{}\n"}, "again", BOT) is None
    assert git(remote, "rev-parse", "data") == head


def test_publish_retries_on_top_of_a_concurrent_push(tmp_path, remote_and_clone):
    """The local summary task and the Actions crawl can push at the same time."""
    remote, clone = remote_and_clone
    other = seed_data_branch(tmp_path, remote, {"data/2026-10-29.jsonl": "{}\n"})
    raced = []

    def concurrent_push():
        if raced:
            return
        raced.append(True)
        (other / "data" / "2026-10-30_AI_enhanced_Chinese.jsonl").write_text("{}\n")
        git(other, "add", ".")
        git(other, "commit", "-m", "concurrent")
        git(other, "push", str(remote), "HEAD:refs/heads/data")

    DataBranch(clone).publish(
        {"data/2026-10-30.jsonl": "{}\n"}, "update", BOT, on_before_push=concurrent_push
    )

    assert git(remote, "log", "-1", "--format=%s", "data~1") == "concurrent"
    assert "2026-10-30_AI_enhanced_Chinese.jsonl" in show(remote, "assets/file-list.txt")


def test_publish_rebuilds_files_from_fresh_state_on_retry(tmp_path, remote_and_clone):
    remote, clone = remote_and_clone
    other = seed_data_branch(tmp_path, remote, {"data/counter.txt": "1\n"})
    raced = []

    def concurrent_push():
        if not raced:
            raced.append(True)
            (other / "data" / "counter.txt").write_text("5\n")
            git(other, "commit", "-am", "bump")
            git(other, "push", str(remote), "HEAD:refs/heads/data")

    def build(branch):
        return {"data/counter.txt": str(int(branch.read("data/counter.txt")) + 1) + "\n"}

    DataBranch(clone).publish(build, "increment", BOT, on_before_push=concurrent_push)

    assert show(remote, "data/counter.txt") == "6"


def test_read_returns_none_for_missing_files_and_branch(tmp_path, remote_and_clone):
    remote, clone = remote_and_clone
    branch = DataBranch(clone)
    assert branch.fetch() is False
    assert branch.read("data/x.jsonl") is None

    seed_data_branch(tmp_path, remote, {"data/2026-10-30.jsonl": "中文\n"})
    assert branch.fetch() is True
    assert branch.read("data/2026-10-30.jsonl") == "中文\n"
    assert branch.read("data/missing.jsonl") is None
    assert branch.list_files("data/") == ["data/2026-10-30.jsonl"]


def test_read_raises_when_a_listed_file_cannot_be_loaded(tmp_path, remote_and_clone):
    """A transient fetch failure must not look like a missing file (it would be overwritten)."""
    import pytest

    remote, clone = remote_and_clone
    seed_data_branch(tmp_path, remote, {"data/2026-10-30.jsonl": "keep me\n"})
    branch = DataBranch(clone)
    branch.fetch()
    blob = git(clone, "rev-parse", "refs/remotes/origin/data:data/2026-10-30.jsonl")
    (clone / ".git" / "objects" / blob[:2] / blob[2:]).unlink()
    git(clone, "remote", "set-url", "origin", str(tmp_path / "unreachable.git"))

    with pytest.raises(Exception):
        branch.read("data/2026-10-30.jsonl")
    assert branch.read("data/absent.jsonl") is None
