# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`mathema init --agents`: vendor the mathema-agents skills for an agent
tool. Every case runs against a LOCAL fixture repo (git clone accepts a
local path), so the feature is exercised end to end with no network."""
import os
import pathlib
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# the skills repo's own private-notes directory, which the vendor never copies
_PRIVATE_DIR = "." + "smd"


def _fixture_repo(tmp_path):
    """A stand-in mathema-agents clone: the skills, the pre-rendered
    per-tool adapters, and deliberate noise (a private-notes directory and
    a README) that must never be vendored."""
    a = tmp_path / "agentfix"
    for rel, body in [
        ("skills/design-claims/SKILL.md", "# design-claims"),
        ("skills/use-mathema-mcp/SKILL.md", "# use-mathema-mcp"),
        ("dist/AGENTS.md", "# AGENTS"),
        ("dist/GEMINI.md", "# GEMINI"),
        ("dist/.cursor/rules/design-claims.mdc", "# cursor"),
        ("dist/.github/copilot-instructions.md", "# copilot"),
        ("dist/.windsurf/rules/design-claims.md", "# windsurf"),
        ("dist/.clinerules/design-claims.md", "# cline"),
        (f"{_PRIVATE_DIR}/00-notes.md", "private process note, never vendored"),
        ("README.md", "readme, never vendored"),
    ]:
        p = a / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    env = dict(os.environ)
    subprocess.run(["git", "init", "-q"], cwd=a, env=env, check=True)
    subprocess.run(["git", "add", "-A"], cwd=a, env=env, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "init"], cwd=a, env=env, check=True)
    return str(a)


def _project(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=proj, check=True)
    return proj


def _init(proj, *args):
    return subprocess.run(
        [sys.executable, "-c",
         "import sys; from mathema.cli import main; "
         f"sys.exit(main([*{list(args)!r}, '--root', {str(proj)!r}]))"],
        cwd=str(proj), capture_output=True, text=True,
        env=dict(os.environ, PYTHONPATH=REPO))


def _files(proj):
    return sorted(
        os.path.relpath(os.path.join(dp, f), proj)
        for dp, _, fs in os.walk(proj) for f in fs if ".git/" not in dp + "/")


def test_codex_vendors_skills_and_agents_adapter(tmp_path):
    url, proj = _fixture_repo(tmp_path), _project(tmp_path)
    r = _init(proj, "init", "--agents", "codex", "--agents-url", url)
    assert r.returncode == 0, r.stdout + r.stderr
    files = _files(proj)
    assert "AGENTS.md" in files
    assert "skills/design-claims/SKILL.md" in files
    assert "skills/use-mathema-mcp/SKILL.md" in files
    # the tool's OWN adapter only, not every tool's
    assert not any(f.startswith(".cursor") or f == "GEMINI.md" for f in files)


def test_only_skills_and_adapter_are_vendored(tmp_path):
    # the exact vendored set proves the repo's private notes, README,
    # license, and history never come along: only skills/ and the one
    # adapter land (git scaffolding aside)
    url, proj = _fixture_repo(tmp_path), _project(tmp_path)
    _init(proj, "init", "--agents", "codex", "--agents-url", url)
    vendored = {f for f in _files(proj)
                if f != ".gitattributes" and not f.startswith(".mathema/")}
    assert vendored == {"AGENTS.md",
                        "skills/design-claims/SKILL.md",
                        "skills/use-mathema-mcp/SKILL.md"}
    assert not any(_PRIVATE_DIR in f for f in _files(proj))


def test_claude_vendors_into_dot_claude_skills(tmp_path):
    url, proj = _fixture_repo(tmp_path), _project(tmp_path)
    _init(proj, "init", "--agents", "claude", "--agents-url", url)
    files = _files(proj)
    assert ".claude/skills/design-claims/SKILL.md" in files
    assert not any(f == "skills/design-claims/SKILL.md" for f in files)
    assert "AGENTS.md" not in files          # claude needs no separate adapter


def test_bare_agents_autodetects_the_tool_in_use(tmp_path):
    url, proj = _fixture_repo(tmp_path), _project(tmp_path)
    (proj / ".cursor").mkdir()               # the one marker present
    r = _init(proj, "init", "--agents", "--agents-url", url)
    assert "for cursor" in r.stdout
    assert ".cursor/rules/design-claims.mdc" in _files(proj)


def test_neutral_fallback_when_no_tool_detected(tmp_path):
    url, proj = _fixture_repo(tmp_path), _project(tmp_path)
    r = _init(proj, "init", "--agents", "--agents-url", url)
    assert "tool-neutral" in r.stdout and "by hand" in r.stdout
    assert "skills/design-claims/SKILL.md" in _files(proj)


def test_idempotent_skip_and_force_overwrite(tmp_path):
    url, proj = _fixture_repo(tmp_path), _project(tmp_path)
    _init(proj, "init", "--agents", "codex", "--agents-url", url)
    skill = proj / "skills" / "design-claims" / "SKILL.md"
    skill.write_text("MY LOCAL EDIT")
    # a plain re-run leaves the local edit alone
    r = _init(proj, "init", "--agents", "codex", "--agents-url", url)
    assert "already in place" in r.stdout and "already present" in r.stdout
    assert skill.read_text() == "MY LOCAL EDIT"
    # --force refreshes it from the repo
    _init(proj, "init", "--agents", "codex", "--agents-url", url, "--force")
    assert skill.read_text() == "# design-claims"


def test_unreachable_repo_falls_back_cleanly(tmp_path):
    proj = _project(tmp_path)
    r = _init(proj, "init", "--agents", "codex",
              "--agents-url", str(tmp_path / "no-such-repo"))
    assert r.returncode == 0                 # init's own work still succeeded
    assert "could not fetch the agent skills" in r.stdout
    assert "Source:" in r.stdout             # the manual hint, no traceback
    assert "Traceback" not in r.stderr


def test_unknown_tool_is_rejected(tmp_path):
    proj = _project(tmp_path)
    r = _init(proj, "init", "--agents", "notatool")
    assert r.returncode == 2
    assert "invalid choice" in r.stderr


def test_ci_flag_scaffolds_the_github_verify_gate(tmp_path):
    import yaml
    proj = _project(tmp_path)
    r = _init(proj, "init", "--ci")
    assert r.returncode == 0, r.stdout + r.stderr
    wf = proj / ".github" / "workflows" / "mathema-verify.yml"
    assert wf.exists()
    doc = yaml.safe_load(wf.read_text())
    steps = doc["jobs"]["verify"]["steps"]
    assert any("mathema verify" in str(s.get("run", "")) for s in steps)
    # the header must not promise a green first run: strict is the
    # default and fails unverifiable claims too, which most stores have
    header = wf.read_text()
    assert "STRICT by default" in header and "--lenient" in header
    # already present means untouched: it is the adopter's file now
    wf.write_text(wf.read_text() + "# my edit\n")
    r2 = _init(proj, "init", "--ci", "github")
    assert "already in place" in r2.stdout
    assert wf.read_text().endswith("# my edit\n")


def test_ci_flag_scaffolds_the_gitlab_fragment_with_include_hint(tmp_path):
    import yaml
    proj = _project(tmp_path)
    r = _init(proj, "init", "--ci", "gitlab")
    assert r.returncode == 0, r.stdout + r.stderr
    frag = proj / ".gitlab-ci.mathema.yml"
    doc = yaml.safe_load(frag.read_text())
    assert "mathema verify" in " ".join(doc["mathema-verify"]["script"])
    assert "include" in r.stdout            # the wiring hint is printed


def _branch(repo, name, marker):
    """Add `name` to a fixture clone, carrying `marker` so a vendored file
    says which ref it came from."""
    env = dict(os.environ)
    subprocess.run(["git", "checkout", "-q", "-b", name], cwd=repo, env=env,
                   check=True)
    (pathlib.Path(repo) / "skills/design-claims/SKILL.md").write_text(marker)
    subprocess.run(["git", "add", "-A"], cwd=repo, env=env, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", name], cwd=repo, env=env, check=True)
    subprocess.run(["git", "checkout", "-q", "-"], cwd=repo, env=env,
                   check=True)


def test_the_branch_matching_this_mathema_line_is_preferred(tmp_path):
    # the skills describe a tool surface that moves on minors, so a
    # repository carrying one branch per line must serve this line's
    from mathema.cli import _agents_line_ref
    repo = _fixture_repo(tmp_path)
    line = _agents_line_ref()
    assert line, "a released version always has a major.minor"
    _branch(repo, line, "# from the line branch")

    proj = _project(tmp_path)
    r = _init(proj, "init", "--agents", "codex", "--agents-url", repo)
    assert r.returncode == 0, r.stdout + r.stderr
    got = (proj / "skills/design-claims/SKILL.md").read_text()
    assert got == "# from the line branch"
    # the resolved ref is reported, never left to be inferred
    assert line in r.stdout


def test_a_missing_line_branch_falls_back_and_says_which_it_used(tmp_path):
    # no branch for this line yet: the default branch tracks the newest
    # one, and taking it silently would hide a real version mismatch
    repo = _fixture_repo(tmp_path)          # default branch only
    proj = _project(tmp_path)
    r = _init(proj, "init", "--agents", "codex", "--agents-url", repo)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (proj / "skills/design-claims/SKILL.md").exists()
    assert "default branch" in r.stdout


def test_an_explicit_ref_is_never_substituted(tmp_path):
    # a pin that cannot be served is worth failing on: silently vendoring
    # a different line's skills is the failure the pin exists to prevent
    repo = _fixture_repo(tmp_path)
    proj = _project(tmp_path)
    r = _init(proj, "init", "--agents", "codex", "--agents-url", repo,
              "--agents-ref", "v9.9")
    assert r.returncode == 0                 # a fetch failure still exits 0
    assert not (proj / "skills").exists()    # nothing vendored
    assert "v9.9" in r.stdout                # the ref asked for is named
