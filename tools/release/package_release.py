#!/usr/bin/env python3
"""Create deterministic GitHub release assets from a built release directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any


FIXED_ZIP_TIME = (2026, 8, 27, 0, 0, 0)

COMMON_RELEASE_FILES = {
    "CHANGELOG.md",
    "COPYING.GPL-2.0",
    "homm2-ko-patcher.exe",
    "homm2_ko_patcher.py",
    "INSTALL_KO.md",
    "INSTALL.cmd",
    "INSTALL_CUSTOM_FONT.cmd",
    "manifest.json",
    "NOTICE.md",
    "README_KO.md",
    "RECOVER.cmd",
    "THIRD_PARTY_NOTICES.md",
    "UNINSTALL.cmd",
    "VERIFY.cmd",
    "THIRD_PARTY_LICENSES/BSDIFF4_LICENSE.txt",
    "THIRD_PARTY_LICENSES/PYINSTALLER_COPYING.txt",
    "THIRD_PARTY_LICENSES/PYTHON_LICENSE.txt",
}

V2_RELEASE_FILES = {
    "homm2_font.py",
    "THIRD_PARTY_LICENSES/NANUM_GOTHIC_CODING_OFL.txt",
    "THIRD_PARTY_LICENSES/PILLOW_LICENSE.txt",
}

PATCH_GAME_PATHS = (
    "HEROES2.EXE",
    "DATA/HEROES2.AGG",
    "DATA/HEROES2X.AGG",
    "MAPS/CAMPE01.H2C",
    "MAPS/CAMPE02.H2C",
    "MAPS/CAMPE03.H2C",
    "MAPS/CAMPE04.H2C",
    "MAPS/CAMPE05.H2C",
    "MAPS/CAMPE05B.H2C",
    "MAPS/CAMPE06.H2C",
    "MAPS/CAMPE07.H2C",
    "MAPS/CAMPE08.H2C",
    "MAPS/CAMPE09.H2C",
    "MAPS/CAMPE10.H2C",
    "MAPS/CAMPE11.H2C",
    "MAPS/CAMPG01.H2C",
    "MAPS/CAMPG02.H2C",
    "MAPS/CAMPG03.H2C",
    "MAPS/CAMPG04.H2C",
    "MAPS/CAMPG05.H2C",
    "MAPS/CAMPG05B.H2C",
    "MAPS/CAMPG06.H2C",
    "MAPS/CAMPG07.H2C",
    "MAPS/CAMPG08.H2C",
    "MAPS/CAMPG09.H2C",
    "MAPS/CAMPG10.H2C",
    "MAPS/CAMP1_01.HXC",
    "MAPS/CAMP1_02.HXC",
    "MAPS/CAMP1_03.HXC",
    "MAPS/CAMP1_04.HXC",
    "MAPS/CAMP1_05.HXC",
    "MAPS/CAMP1_06.HXC",
    "MAPS/CAMP1_07.HXC",
    "MAPS/CAMP1_08.HXC",
    "MAPS/CAMP2_01.HXC",
    "MAPS/CAMP2_02.HXC",
    "MAPS/CAMP2_03.HXC",
    "MAPS/CAMP2_04.HXC",
    "MAPS/CAMP2_05.HXC",
    "MAPS/CAMP2_06.HXC",
    "MAPS/CAMP2_07.HXC",
    "MAPS/CAMP2_08.HXC",
    "MAPS/CAMP3_01.HXC",
    "MAPS/CAMP3_02.HXC",
    "MAPS/CAMP3_03.HXC",
    "MAPS/CAMP3_04.HXC",
    "MAPS/CAMP4_01.HXC",
    "MAPS/CAMP4_02.HXC",
    "MAPS/CAMP4_03.HXC",
    "MAPS/CAMP4_04.HXC",
)
PATCH_GAME_PATH_SET = frozenset(PATCH_GAME_PATHS)
FONT_AGG_PATHS = frozenset({"DATA/HEROES2.AGG", "DATA/HEROES2X.AGG"})
COPY_GAME_PATH = "KOREAN.BIN"
COPY_PACKAGE_PATH = "payload/KOREAN.BIN"
MAPPING_PACKAGE_PATH = "fonts/mapping874.fixed-interface-font.txt"
DEFAULT_FONT_PACKAGE_PATH = "fonts/NanumGothicCoding-Regular.ttf"
DEFAULT_FONT_LICENSE_PATH = "THIRD_PARTY_LICENSES/NANUM_GOTHIC_CODING_OFL.txt"
BETA4_VERSION = "v0.9.0-beta.4"
BETA5_VERSION = "v0.9.0-beta.5"
BETA6_VERSION = "v0.9.0-beta.6"
BETA7_VERSION = "v0.9.0-beta.7"
BETA8_VERSION = "v0.9.0-beta.8"
BETA4_MANIFEST_PATH = "upgrades/v0.9.0-beta.4-manifest.json"
BETA5_MANIFEST_PATH = "upgrades/v0.9.0-beta.5-manifest.json"
BETA6_MANIFEST_PATH = "upgrades/v0.9.0-beta.6-manifest.json"
BETA7_MANIFEST_PATH = "upgrades/v0.9.0-beta.7-manifest.json"
BETA4_MANIFEST_IDENTITY = {
    "size": 31_988,
    "sha256": "D623C611962CE7F94CC3806DA81B00EDAD7809FB87E489001FE9F0ADF39BAC60",
}
BETA5_MANIFEST_IDENTITY = {
    "size": 32_845,
    "sha256": "A9A402E1BD5A8ECD856EABA70BA2F88A828D42F68D37E6F2B82BF7659991B05F",
}
BETA6_MANIFEST_IDENTITY = {
    "size": 33_107,
    "sha256": "32E731E43E6D00773867AF89A1BB0C0415099B69359B39C98153CE025279537C",
}
BETA7_MANIFEST_IDENTITY = {
    "size": 33_369,
    "sha256": "F71C83895BDC3581F1C8BA4BC7919153E14F0500831D941DAE9B34D17519E2CE",
}
PINNED_UPGRADE_SOURCES = (
    (BETA4_VERSION, BETA4_MANIFEST_PATH, BETA4_MANIFEST_IDENTITY),
    (BETA5_VERSION, BETA5_MANIFEST_PATH, BETA5_MANIFEST_IDENTITY),
    (BETA6_VERSION, BETA6_MANIFEST_PATH, BETA6_MANIFEST_IDENTITY),
    (BETA7_VERSION, BETA7_MANIFEST_PATH, BETA7_MANIFEST_IDENTITY),
)


class PackageError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PackageError(message)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def identity(raw: bytes) -> dict[str, int | str]:
    return {"size": len(raw), "sha256": sha256(raw)}


def validate_identity(value: Any, label: str) -> dict[str, int | str]:
    require(isinstance(value, dict) and set(value) == {"size", "sha256"}, f"{label} identity is invalid")
    require(isinstance(value["size"], int) and value["size"] >= 0, f"{label} size is invalid")
    require(
        isinstance(value["sha256"], str) and re.fullmatch(r"[0-9A-F]{64}", value["sha256"]) is not None,
        f"{label} SHA-256 is invalid",
    )
    return {"size": value["size"], "sha256": value["sha256"]}


def write_new(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    require(path.read_bytes() == raw, f"write readback mismatch: {path}")


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def normalized_archive_path(value: Any, label: str) -> str:
    require(isinstance(value, str) and value, f"{label} path is missing")
    require("\\" not in value and not value.startswith("/"), f"{label} path is not normalized: {value!r}")
    parts = value.split("/")
    require(all(part not in {"", ".", ".."} for part in parts), f"{label} path is unsafe: {value!r}")
    path = PurePosixPath(value)
    require(not path.is_absolute() and path.as_posix() == value, f"{label} path is not normalized: {value!r}")
    return value


def expected_release_files(manifest: Any, version: str) -> set[str]:
    require(isinstance(manifest, dict), "release manifest root is invalid")
    schema = manifest.get("schema")
    require(
        schema in {"homm2-korean-release-manifest-v1", "homm2-korean-release-manifest-v2"},
        f"unsupported release manifest schema: {schema!r}",
    )
    require(
        isinstance(version, str) and re.fullmatch(r"v[0-9A-Za-z][0-9A-Za-z._+-]{0,63}", version) is not None,
        "release version is unsafe",
    )
    require(manifest.get("version") == version, "release version does not match manifest")
    require(version == BETA8_VERSION, "this packager is pinned to beta.8")
    require(schema == "homm2-korean-release-manifest-v2", "beta.8 requires release manifest v2")
    rows = manifest.get("files")
    require(isinstance(rows, list) and rows, "release manifest file list is empty")

    expected = set(COMMON_RELEASE_FILES)
    installed_paths: list[str] = []
    for index, row in enumerate(rows):
        require(isinstance(row, dict), f"manifest file row is invalid: {index}")
        installed_path = normalized_archive_path(row.get("path"), f"manifest target {index}")
        package_path = normalized_archive_path(row.get("package_path"), f"manifest file {index}")
        method = row.get("method")
        if installed_path == COPY_GAME_PATH:
            require(method == "copy", "KOREAN.BIN must use the copy method")
            required_package_path = COPY_PACKAGE_PATH
        else:
            require(installed_path in PATCH_GAME_PATH_SET, f"manifest target is not release-owned: {installed_path!r}")
            required_method = (
                "bsdiff40_font_agg_v1"
                if schema == "homm2-korean-release-manifest-v2" and installed_path in FONT_AGG_PATHS
                else "bsdiff40"
            )
            require(method == required_method, f"manifest method does not match target contract: {installed_path}")
            required_package_path = f"patches/{installed_path}.bsdiff"
        require(
            package_path == required_package_path,
            f"manifest package path does not match target contract: {installed_path!r}",
        )
        installed_paths.append(installed_path)
        expected.add(package_path)

    required_installed_paths = PATCH_GAME_PATH_SET | {COPY_GAME_PATH}
    require(len(installed_paths) == len(required_installed_paths), "release manifest must contain exactly 51 files")
    require(len(installed_paths) == len(set(installed_paths)), "release manifest contains duplicate target paths")
    require(set(installed_paths) == required_installed_paths, "release manifest target allowlist is incomplete")

    if schema == "homm2-korean-release-manifest-v2":
        expected.update(V2_RELEASE_FILES)
        generation = manifest.get("font_generation")
        require(
            isinstance(generation, dict) and generation.get("schema") == "homm2-font-generation-v1",
            "font_generation is missing or invalid",
        )
        mapping = generation.get("mapping")
        default_font = generation.get("default_font")
        require(isinstance(mapping, dict), "font mapping declaration is invalid")
        require(isinstance(default_font, dict), "default font declaration is invalid")
        mapping_path = normalized_archive_path(mapping.get("package_path"), "font mapping")
        font_path = normalized_archive_path(default_font.get("package_path"), "default font")
        font_license_path = normalized_archive_path(default_font.get("license_path"), "default font license")
        require(mapping_path == MAPPING_PACKAGE_PATH, "font mapping path is outside the fixed release contract")
        require(font_path == DEFAULT_FONT_PACKAGE_PATH, "default font path is outside the fixed release contract")
        require(font_license_path == DEFAULT_FONT_LICENSE_PATH, "default font license path is outside the fixed release contract")
        expected.update({mapping_path, font_path, font_license_path})

        upgrades = manifest.get("upgrades")
        require(
            isinstance(upgrades, dict) and set(upgrades) == {"schema", "from"},
            "upgrade declaration is invalid",
        )
        require(upgrades.get("schema") == "homm2-korean-upgrades-v1", "upgrade schema is invalid")
        sources = upgrades.get("from")
        require(
            isinstance(sources, list) and len(sources) == len(PINNED_UPGRADE_SOURCES),
            "beta.8 must declare exactly the pinned beta.4, beta.5, beta.6 and beta.7 upgrade sources",
        )
        for index, (descriptor, pinned) in enumerate(zip(sources, PINNED_UPGRADE_SOURCES)):
            require(
                isinstance(descriptor, dict)
                and set(descriptor) == {"version", "manifest_path", "manifest"},
                f"upgrade descriptor is invalid: {index}",
            )
            pinned_version, pinned_path, pinned_identity = pinned
            require(
                descriptor.get("version") == pinned_version,
                f"upgrade source {index} version is not pinned",
            )
            manifest_path = normalized_archive_path(descriptor.get("manifest_path"), f"upgrade manifest {index}")
            require(manifest_path == pinned_path, f"upgrade source {index} manifest path is not pinned")
            require(
                validate_identity(descriptor.get("manifest"), f"upgrade manifest {index}")
                == pinned_identity,
                f"upgrade source {index} manifest identity is not pinned",
            )
            expected.add(manifest_path)

    folded = [path.casefold() for path in expected]
    require(len(folded) == len(set(folded)), "release allowlist contains duplicate paths")
    return expected


def verify_manifest_artifacts(release_dir: Path, manifest: dict[str, Any]) -> None:
    artifacts: list[tuple[str, dict[str, int | str], str]] = []
    for index, row in enumerate(manifest["files"]):
        package_path = str(row["package_path"])
        artifacts.append((package_path, validate_identity(row.get("package"), f"manifest file {index}"), package_path))

    if manifest["schema"] == "homm2-korean-release-manifest-v2":
        generation = manifest["font_generation"]
        mapping = generation["mapping"]
        default_font = generation["default_font"]
        artifacts.append(
            (
                str(mapping["package_path"]),
                validate_identity(mapping.get("package"), "font mapping"),
                "font mapping",
            )
        )
        artifacts.append(
            (
                str(default_font["package_path"]),
                validate_identity(default_font.get("package"), "default font"),
                "default font",
            )
        )
        upgrades = manifest.get("upgrades")
        if upgrades is not None:
            for index, descriptor in enumerate(upgrades["from"]):
                artifacts.append(
                    (
                        str(descriptor["manifest_path"]),
                        validate_identity(descriptor.get("manifest"), f"upgrade manifest {index}"),
                        f"upgrade manifest {index}",
                    )
                )

    for relative, declared, label in artifacts:
        path = release_dir / PurePosixPath(relative)
        require(path.is_file(), f"declared package artifact is missing: {relative}")
        require(identity(path.read_bytes()) == declared, f"declared package artifact identity mismatch: {label}")


def package(release_dir: Path, output_dir: Path, version: str) -> dict[str, Any]:
    release_dir = release_dir.resolve(strict=True)
    output_dir = output_dir.resolve(strict=False)
    require(release_dir.is_dir(), f"release directory missing: {release_dir}")
    require(not output_dir.exists(), f"output already exists: {output_dir}")
    require((release_dir / "manifest.json").is_file(), "release manifest missing")
    require((release_dir / "homm2-ko-patcher.exe").is_file(), "Windows patcher missing")

    try:
        manifest = json.loads((release_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackageError(f"release manifest cannot be read: {exc}") from exc
    expected = expected_release_files(manifest, version)

    files = sorted(
        (path for path in release_dir.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(release_dir).as_posix().casefold(),
    )
    require(files, "release directory is empty")
    actual = {path.relative_to(release_dir).as_posix() for path in files}
    missing = sorted(expected - actual, key=str.casefold)
    unexpected = sorted(actual - expected, key=str.casefold)
    require(not missing, f"release directory is missing allowlisted files: {missing}")
    require(not unexpected, f"release directory has unexpected files: {unexpected}")
    require(len(actual) == len(files), "release directory contains duplicate paths")
    for path in files:
        require(not path.is_symlink(), f"release file must not be a symlink: {path.relative_to(release_dir)}")
        require(path.resolve(strict=True).is_relative_to(release_dir), f"release file escapes directory: {path}")
    verify_manifest_artifacts(release_dir, manifest)
    stage = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.stage-", dir=output_dir.parent))
    try:
        zip_name = f"homm2-ko-{version}-win-gog.zip"
        manifest_name = f"homm2-ko-{version}-manifest.json"
        zip_path = stage / zip_name
        with zipfile.ZipFile(
            zip_path,
            mode="x",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
            strict_timestamps=True,
        ) as archive:
            for path in files:
                relative = path.relative_to(release_dir).as_posix()
                info = zipfile.ZipInfo(relative, FIXED_ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)

        manifest_raw = (release_dir / "manifest.json").read_bytes()
        write_new(stage / manifest_name, manifest_raw)
        zip_raw = zip_path.read_bytes()
        sums = (
            f"{sha256(zip_raw)}  {zip_name}\n"
            f"{sha256(manifest_raw)}  {manifest_name}\n"
        ).encode("ascii")
        write_new(stage / "SHA256SUMS.txt", sums)

        with zipfile.ZipFile(zip_path) as archive:
            names = archive.namelist()
            require(names == [path.relative_to(release_dir).as_posix() for path in files], "ZIP entry order changed")
            for path, name in zip(files, names):
                require(archive.read(name) == path.read_bytes(), f"ZIP entry mismatch: {name}")

        stage.replace(output_dir)
    finally:
        if stage.exists():
            shutil.rmtree(stage)

    return {
        "status": "github_assets_built",
        "version": version,
        "output": str(output_dir),
        "zip": {
            "name": zip_name,
            "size": (output_dir / zip_name).stat().st_size,
            "sha256": sha256((output_dir / zip_name).read_bytes()),
            "entries": len(files),
        },
        "manifest": {
            "name": manifest_name,
            "size": (output_dir / manifest_name).stat().st_size,
            "sha256": sha256((output_dir / manifest_name).read_bytes()),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--version", default=BETA8_VERSION)
    args = parser.parse_args()
    print(
        json.dumps(
            package(args.release_dir, args.output_dir, args.version),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
