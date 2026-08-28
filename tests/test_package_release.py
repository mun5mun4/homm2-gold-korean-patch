#!/usr/bin/env python3
"""Fail-closed contracts for the GitHub release ZIP allowlist."""

from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.release import package_release


ROOT = Path(__file__).resolve().parents[1]
VERSION = "v0.9.0-beta.10"
MANIFEST_PACKAGE_PATH = "patches/HEROES2.EXE.bsdiff"
MAPPING_PACKAGE_PATH = "fonts/mapping874.fixed-interface-font.txt"
DEFAULT_FONT_PACKAGE_PATH = "fonts/IropkeBatangM.ttf"
FALLBACK_FONT_PACKAGE_PATH = "fonts/NanumGothicCoding-Regular.ttf"
UPGRADE_MANIFEST_PACKAGE_PATHS = (
    "upgrades/v0.9.0-beta.4-manifest.json",
    "upgrades/v0.9.0-beta.5-manifest.json",
    "upgrades/v0.9.0-beta.6-manifest.json",
    "upgrades/v0.9.0-beta.7-manifest.json",
    "upgrades/v0.9.0-beta.8-manifest.json",
    "upgrades/v0.9.0-beta.9-manifest.json",
)
FIXTURE_RAW = b"fixture\n"
DEFAULT_FONT_RAW = (ROOT / "packaging" / "release_assets" / DEFAULT_FONT_PACKAGE_PATH).read_bytes()
FALLBACK_FONT_RAW = (ROOT / "packaging" / "release_assets" / FALLBACK_FONT_PACKAGE_PATH).read_bytes()
FROZEN_UPGRADE_MANIFESTS = {
    relative: Path(__file__).resolve().parents[1] / "packaging" / "release_assets" / relative
    for relative in UPGRADE_MANIFEST_PACKAGE_PATHS
}

FIXED_RELEASE_FILES = frozenset(
    {
        "manifest.json",
        "homm2-ko-patcher.exe",
        "homm2_ko_patcher.py",
        "homm2_font.py",
        "README_KO.md",
        "INSTALL_KO.md",
        "CHANGELOG.md",
        "NOTICE.md",
        "THIRD_PARTY_NOTICES.md",
        "COPYING.GPL-2.0",
        "INSTALL.cmd",
        "INSTALL_CUSTOM_FONT.cmd",
        "VERIFY.cmd",
        "UNINSTALL.cmd",
        "RECOVER.cmd",
        "THIRD_PARTY_LICENSES/BSDIFF4_LICENSE.txt",
        "THIRD_PARTY_LICENSES/IROPKE_BATANG_OFL.txt",
        "THIRD_PARTY_LICENSES/NANUM_GOTHIC_CODING_OFL.txt",
        "THIRD_PARTY_LICENSES/PILLOW_LICENSE.txt",
        "THIRD_PARTY_LICENSES/PYINSTALLER_COPYING.txt",
        "THIRD_PARTY_LICENSES/PYTHON_LICENSE.txt",
    }
)


def artifact_identity(raw: bytes) -> dict[str, int | str]:
    return {"size": len(raw), "sha256": package_release.sha256(raw)}


def write_file(root: Path, relative: str, raw: bytes = FIXTURE_RAW) -> None:
    path = root / Path(relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def fixture_manifest(version: str = VERSION) -> dict[str, object]:
    files = [
        {
            "path": path,
            "method": "bsdiff40_font_agg_v1" if path in package_release.FONT_AGG_PATHS else "bsdiff40",
            "package_path": f"patches/{path}.bsdiff",
            "package": artifact_identity(FIXTURE_RAW),
        }
        for path in package_release.PATCH_GAME_PATHS
    ]
    files.append(
        {
            "path": package_release.COPY_GAME_PATH,
            "method": "copy",
            "package_path": package_release.COPY_PACKAGE_PATH,
            "package": artifact_identity(FIXTURE_RAW),
        }
    )
    return {
        "schema": "homm2-korean-release-manifest-v2",
        "version": version,
        "files": files,
        "font_generation": {
            "schema": "homm2-font-generation-v2",
            "mapping": {"package_path": MAPPING_PACKAGE_PATH, "package": artifact_identity(FIXTURE_RAW)},
            "default_font": {
                "name": "Iropke Batang Medium",
                "package_path": DEFAULT_FONT_PACKAGE_PATH,
                "package": artifact_identity(DEFAULT_FONT_RAW),
                "face_index": 0,
                "license_path": "THIRD_PARTY_LICENSES/IROPKE_BATANG_OFL.txt",
            },
            "fallback_font": {
                "name": "NanumGothicCoding Regular",
                "package_path": FALLBACK_FONT_PACKAGE_PATH,
                "package": artifact_identity(FALLBACK_FONT_RAW),
                "face_index": 0,
                "license_path": "THIRD_PARTY_LICENSES/NANUM_GOTHIC_CODING_OFL.txt",
            },
        },
        "upgrades": {
            "schema": "homm2-korean-upgrades-v1",
            "from": [
                {
                    "version": "v0.9.0-beta.4",
                    "manifest_path": UPGRADE_MANIFEST_PACKAGE_PATHS[0],
                    "manifest": dict(package_release.BETA4_MANIFEST_IDENTITY),
                },
                {
                    "version": "v0.9.0-beta.5",
                    "manifest_path": UPGRADE_MANIFEST_PACKAGE_PATHS[1],
                    "manifest": dict(package_release.BETA5_MANIFEST_IDENTITY),
                },
                {
                    "version": "v0.9.0-beta.6",
                    "manifest_path": UPGRADE_MANIFEST_PACKAGE_PATHS[2],
                    "manifest": dict(package_release.BETA6_MANIFEST_IDENTITY),
                },
                {
                    "version": "v0.9.0-beta.7",
                    "manifest_path": UPGRADE_MANIFEST_PACKAGE_PATHS[3],
                    "manifest": dict(package_release.BETA7_MANIFEST_IDENTITY),
                },
                {
                    "version": "v0.9.0-beta.8",
                    "manifest_path": UPGRADE_MANIFEST_PACKAGE_PATHS[4],
                    "manifest": dict(package_release.BETA8_MANIFEST_IDENTITY),
                },
                {
                    "version": "v0.9.0-beta.9",
                    "manifest_path": UPGRADE_MANIFEST_PACKAGE_PATHS[5],
                    "manifest": dict(package_release.BETA9_MANIFEST_IDENTITY),
                },
            ],
        },
    }


class PackageReleaseAllowlistTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.release = self.root / "release"
        self.output = self.root / "github-assets"
        self.release.mkdir()

        for relative in FIXED_RELEASE_FILES - {"manifest.json"}:
            write_file(self.release, relative)
        for relative in (
            *(f"patches/{path}.bsdiff" for path in package_release.PATCH_GAME_PATHS),
            package_release.COPY_PACKAGE_PATH,
            MAPPING_PACKAGE_PATH,
        ):
            write_file(self.release, relative)
        write_file(self.release, DEFAULT_FONT_PACKAGE_PATH, DEFAULT_FONT_RAW)
        write_file(self.release, FALLBACK_FONT_PACKAGE_PATH, FALLBACK_FONT_RAW)
        for relative, source in FROZEN_UPGRADE_MANIFESTS.items():
            write_file(self.release, relative, source.read_bytes())
        self.write_manifest()

    def write_manifest(self, *, version: str = VERSION) -> None:
        raw = (json.dumps(fixture_manifest(version), ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
        write_file(self.release, "manifest.json", raw)

    @property
    def expected_files(self) -> set[str]:
        return set(FIXED_RELEASE_FILES) | {
            *(f"patches/{path}.bsdiff" for path in package_release.PATCH_GAME_PATHS),
            package_release.COPY_PACKAGE_PATH,
            MAPPING_PACKAGE_PATH,
            DEFAULT_FONT_PACKAGE_PATH,
            FALLBACK_FONT_PACKAGE_PATH,
            *UPGRADE_MANIFEST_PACKAGE_PATHS,
        }

    def test_packages_exact_manifest_and_fixed_asset_allowlist(self) -> None:
        self.assertEqual(package_release.FIXED_ZIP_TIME, (2026, 8, 28, 0, 0, 0))
        result = package_release.package(self.release, self.output, VERSION)

        zip_path = self.output / str(result["zip"]["name"])
        with zipfile.ZipFile(zip_path) as archive:
            self.assertEqual(set(archive.namelist()), self.expected_files)
            self.assertEqual(len(archive.namelist()), len(self.expected_files))

    def test_custom_font_launcher_selects_once(self) -> None:
        launcher = (ROOT / "packaging" / "release_assets" / "INSTALL_CUSTOM_FONT.cmd").read_text(
            encoding="utf-8"
        )

        self.assertIn('homm2-ko-patcher.exe" install --choose-font %*', launcher)
        self.assertNotIn(" preflight ", launcher)
        self.assertNotRegex(launcher.casefold(), r"\.(?:ttf|otf|ttc|otc)(?:\s|\")")

    def test_rejects_unlisted_nested_file(self) -> None:
        write_file(self.release, "__pycache__/homm2_font.cpython-313.pyc", b"not-release-data")

        with self.assertRaises(package_release.PackageError):
            package_release.package(self.release, self.output, VERSION)

        self.assertFalse(self.output.exists())

    def test_rejects_extra_user_font_files(self) -> None:
        for relative in ("fonts/PrivateFont.ttf", "fonts/PrivateFont.otf"):
            with self.subTest(path=relative):
                write_file(self.release, relative, b"must not be distributed")
                try:
                    with self.assertRaisesRegex(package_release.PackageError, "unexpected"):
                        package_release.package(self.release, self.output, VERSION)
                    self.assertFalse(self.output.exists())
                finally:
                    (self.release / relative).unlink()

    def test_rejects_missing_custom_font_launcher(self) -> None:
        (self.release / "INSTALL_CUSTOM_FONT.cmd").unlink()

        with self.assertRaisesRegex(package_release.PackageError, "missing"):
            package_release.package(self.release, self.output, VERSION)

        self.assertFalse(self.output.exists())

    def test_rejects_missing_manifest_package_file(self) -> None:
        (self.release / MANIFEST_PACKAGE_PATH).unlink()

        with self.assertRaises(package_release.PackageError):
            package_release.package(self.release, self.output, VERSION)

        self.assertFalse(self.output.exists())

    def test_rejects_missing_upgrade_manifest(self) -> None:
        for relative in UPGRADE_MANIFEST_PACKAGE_PATHS:
            with self.subTest(path=relative):
                path = self.release / relative
                raw = path.read_bytes()
                path.unlink()
                try:
                    with self.assertRaises(package_release.PackageError):
                        package_release.package(self.release, self.output, VERSION)
                    self.assertFalse(self.output.exists())
                finally:
                    write_file(self.release, relative, raw)

    def test_rejects_missing_fixed_release_asset(self) -> None:
        (self.release / "NOTICE.md").unlink()

        with self.assertRaises(package_release.PackageError):
            package_release.package(self.release, self.output, VERSION)

        self.assertFalse(self.output.exists())

    def test_rejects_cli_and_manifest_version_mismatch(self) -> None:
        self.write_manifest(version="v0.9.0-beta.3")

        with self.assertRaises(package_release.PackageError):
            package_release.package(self.release, self.output, VERSION)

        self.assertFalse(self.output.exists())

    def test_rejects_beta9_as_the_current_release(self) -> None:
        manifest = fixture_manifest(version="v0.9.0-beta.9")

        with self.assertRaisesRegex(package_release.PackageError, "pinned to beta.10"):
            package_release.expected_release_files(manifest, "v0.9.0-beta.9")

    def test_rejects_legacy_manifest_schema_for_beta10(self) -> None:
        manifest = fixture_manifest()
        manifest["schema"] = "homm2-korean-release-manifest-v1"

        with self.assertRaisesRegex(package_release.PackageError, "manifest v2"):
            package_release.expected_release_files(manifest, VERSION)

    def test_rejects_legacy_font_generation_schema_for_beta10(self) -> None:
        manifest = fixture_manifest()
        manifest["font_generation"]["schema"] = "homm2-font-generation-v1"

        with self.assertRaisesRegex(package_release.PackageError, "font_generation"):
            package_release.expected_release_files(manifest, VERSION)

    def test_rejects_manifest_package_paths_outside_fixed_patch_contract(self) -> None:
        bad_paths = (
            "captures/private-data.bin",
            "../private-data.bin",
            "/private-data.bin",
            r"patches\HEROES2.EXE.bsdiff",
            "C:/private-data.bin",
            "fonts/private-data.ttf",
        )
        for bad_path in bad_paths:
            with self.subTest(path=bad_path):
                manifest = fixture_manifest()
                manifest["files"][0]["package_path"] = bad_path
                with self.assertRaises(package_release.PackageError):
                    package_release.expected_release_files(manifest, VERSION)

    def test_rejects_private_target_even_when_patch_path_matches_it(self) -> None:
        manifest = fixture_manifest()
        manifest["files"][0] = {
            "path": "captures/private-data.bin",
            "method": "bsdiff40",
            "package_path": "patches/captures/private-data.bin.bsdiff",
        }

        with self.assertRaisesRegex(package_release.PackageError, "not release-owned"):
            package_release.expected_release_files(manifest, VERSION)

    def test_rejects_font_artifact_paths_outside_fixed_contract(self) -> None:
        cases = (
            ("mapping", "package_path", "captures/mapping.txt"),
            ("default_font", "package_path", "fonts/PrivateFont.ttf"),
            ("default_font", "license_path", "captures/font-license.txt"),
            ("fallback_font", "package_path", "fonts/PrivateFallback.ttf"),
            ("fallback_font", "license_path", "captures/fallback-license.txt"),
        )
        for section, key, bad_path in cases:
            with self.subTest(section=section, key=key):
                manifest = fixture_manifest()
                manifest["font_generation"][section][key] = bad_path
                with self.assertRaises(package_release.PackageError):
                    package_release.expected_release_files(manifest, VERSION)

    def test_rejects_font_names_and_faces_outside_fixed_contract(self) -> None:
        cases = (
            ("default_font", "name", "NanumGothicCoding Regular"),
            ("default_font", "face_index", 1),
            ("default_font", "package", artifact_identity(FIXTURE_RAW)),
            ("fallback_font", "name", "Iropke Batang Medium"),
            ("fallback_font", "face_index", 1),
            ("fallback_font", "package", artifact_identity(FIXTURE_RAW)),
        )
        for section, key, value in cases:
            with self.subTest(section=section, key=key):
                manifest = fixture_manifest()
                manifest["font_generation"][section][key] = value
                with self.assertRaises(package_release.PackageError):
                    package_release.expected_release_files(manifest, VERSION)

    def test_rejects_upgrade_manifest_path_outside_versioned_contract(self) -> None:
        for bad_path in ("captures/beta4-manifest.json", "upgrades/../private.json", "upgrades/private.json"):
            with self.subTest(path=bad_path):
                manifest = fixture_manifest()
                manifest["upgrades"]["from"][0]["manifest_path"] = bad_path
                with self.assertRaises(package_release.PackageError):
                    package_release.expected_release_files(manifest, VERSION)

    def test_rejects_wrong_agg_patch_method(self) -> None:
        manifest = fixture_manifest()
        agg = next(row for row in manifest["files"] if row["path"] == "DATA/HEROES2.AGG")
        agg["method"] = "bsdiff40"

        with self.assertRaisesRegex(package_release.PackageError, "method"):
            package_release.expected_release_files(manifest, VERSION)

    def test_rejects_replaced_bytes_at_every_manifest_declared_artifact_class(self) -> None:
        artifacts = (
            MANIFEST_PACKAGE_PATH,
            package_release.COPY_PACKAGE_PATH,
            MAPPING_PACKAGE_PATH,
            DEFAULT_FONT_PACKAGE_PATH,
            FALLBACK_FONT_PACKAGE_PATH,
            *UPGRADE_MANIFEST_PACKAGE_PATHS,
        )
        for relative in artifacts:
            with self.subTest(path=relative):
                path = self.release / relative
                original = path.read_bytes()
                path.write_bytes(b"private data that must never enter a release")
                try:
                    with self.assertRaisesRegex(package_release.PackageError, "identity mismatch"):
                        package_release.package(self.release, self.output, VERSION)
                    self.assertFalse(self.output.exists())
                finally:
                    path.write_bytes(original)

    def test_rejects_unpinned_upgrade_sources_and_identities(self) -> None:
        mutations = (
            ("version", "vprivate"),
            ("manifest_path", "upgrades/vprivate-manifest.json"),
            ("manifest", {"size": 1, "sha256": "A" * 64}),
        )
        for index in range(len(UPGRADE_MANIFEST_PACKAGE_PATHS)):
            for key, value in mutations:
                with self.subTest(index=index, key=key):
                    manifest = fixture_manifest()
                    manifest["upgrades"]["from"][index][key] = value
                    with self.assertRaises(package_release.PackageError):
                        package_release.expected_release_files(manifest, VERSION)

    def test_rejects_missing_extra_or_reordered_upgrade_sources(self) -> None:
        cases = []
        manifest = fixture_manifest()
        cases.append(manifest["upgrades"]["from"][:1])
        manifest = fixture_manifest()
        cases.append(manifest["upgrades"]["from"] + [dict(manifest["upgrades"]["from"][0])])
        manifest = fixture_manifest()
        cases.append(list(reversed(manifest["upgrades"]["from"])))

        for index, sources in enumerate(cases):
            with self.subTest(case=index):
                manifest = fixture_manifest()
                manifest["upgrades"]["from"] = sources
                with self.assertRaises(package_release.PackageError):
                    package_release.expected_release_files(manifest, VERSION)


if __name__ == "__main__":
    unittest.main()
