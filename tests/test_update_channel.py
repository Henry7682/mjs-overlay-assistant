import copy
import pytest
from tools.check_update_channel import REPOSITORY, validate


def fixture():
    roles = ("portable", "standalone", "source", "models", "wheels", "downloader")
    assets = {r: {"name": r + ".zip", "bytes": 100, "sha256": "a" * 64,
                  "urls": [f"https://github.com/{REPOSITORY}/releases/download/v1.0.2/{r}.zip"]}
              for r in roles}
    release = {"tag_name": "v1.0.2", "draft": False, "prerelease": True,
               "published_at": "2026-10-31T00:00:00Z", "assets": [
                   {"name": a["name"], "size": a["bytes"], "digest": "sha256:" + a["sha256"],
                    "browser_download_url": a["urls"][0]} for a in assets.values()]}
    return {"schema_version": 1, "version": "1.0.2", "channel": "stable",
            "minimum_launcher": 1, "assets": assets}, [release]


def test_test_release_also_requires_old_launcher_channel():
    manifest, releases = fixture()
    assert validate(manifest, releases)["published_test_release"]
    manifest["version"] = "1.0.1"
    with pytest.raises(ValueError, match="newest"):
        validate(manifest, releases)


@pytest.mark.parametrize("problem", ["missing", "digest", "size", "name", "unpublished"])
def test_reject_unavailable_or_wrong_payload(problem):
    manifest, releases = fixture()
    if problem == "missing":
        releases[0]["assets"].pop(0)
    elif problem == "unpublished":
        releases[0]["draft"] = True
    else:
        releases[0]["assets"][0][problem] = "wrong"
    with pytest.raises(ValueError):
        validate(manifest, releases)


def test_numeric_version_order_and_unpublished_draft():
    manifest, releases = fixture()
    draft = copy.deepcopy(releases[0]); draft.update(tag_name="v1.0.10", draft=True)
    releases.append(draft)
    assert validate(manifest, releases)["version"] == "1.0.2"
    draft["draft"] = False
    with pytest.raises(ValueError, match="newest"):
        validate(manifest, releases)


def test_reject_protocol_that_strands_existing_installations():
    manifest, releases = fixture()
    manifest["minimum_launcher"] = 2
    with pytest.raises(ValueError, match="1.0.0"):
        validate(manifest, releases)
