#!/usr/bin/env python3
"""Transactional installer, verifier, and uninstaller for the HoMM2 Korean patch."""

from __future__ import annotations

import argparse
import bz2
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

try:
    from . import homm2_font
except ImportError:
    import homm2_font


GAME_ID = "1207658785"
BUILD_ID = "52745329670822422"
INFO_NAME = f"goggame-{GAME_ID}.info"
DEFAULT_GOG_DIR = Path(r"C:\Program Files (x86)\GOG Galaxy\Games\HoMM 2 Gold")
STATE_DIR_NAME = "_homm2_ko_install"
RECEIPT_NAME = "receipt.json"
JOURNAL_NAME = "journal.json"
RUN_ID_PATTERN = re.compile(r"^[0-9]{8}T[0-9]{6}_[0-9a-f]{8}$")
BLOCKED_PROCESSES = {
    "dosbox.exe",
    "dosbox-x.exe",
    "heroes2.exe",
    "galaxyclient.exe",
    "galaxyclientservice.exe",
    "galaxycommunication.exe",
}
DYNAMIC_FONT_AGG_METHOD = "bsdiff40_font_agg_v1"
STATIC_METHODS = {"bsdiff40", "copy"}
SUPPORTED_METHODS = STATIC_METHODS | {DYNAMIC_FONT_AGG_METHOD}
HISTORICAL_V2_RENDERER = {
    "id": "pillow-freetype-monochrome-v2-fixed-baseline",
    "normal_pixel_size": 14,
    "small_pixel_size": 12,
    "normal_cell": {"width": 13, "height": 14},
    "small_cell": {"width": 11, "height": 12},
    "shadow_offset": [1, 1],
    "baseline_policy": "logical-cell-ink-bottom-common-v2",
    "fit_policy": "largest-common-integer-pixel-size-foreground-fit-v2",
    "crop_policy": "tight-mask-preserve-logical-cell-offset-v1",
    "shadow_policy": "clip-at-logical-cell-edge-v1",
    "foreground_palette_index": 10,
    "shadow_palette_index": 21,
}


class PatchError(RuntimeError):
    pass


def require(value: bool, message: str) -> None:
    if not value:
        raise PatchError(message)


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def file_identity(path: Path) -> dict[str, int | str]:
    require(path.is_file(), f"파일이 없습니다: {path}")
    return {"size": path.stat().st_size, "sha256": sha256_file(path)}


def identity_matches(actual: dict[str, int | str], expected: dict[str, Any]) -> bool:
    """Compare the fields enforced by the installer.

    Source entries may also carry an informational MD5 copied from GOG's hash
    database.  The runtime verifier intentionally uses size and SHA-256 only.
    """
    return actual == {"size": expected.get("size"), "sha256": expected.get("sha256")}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        require(Path(temp_name).read_bytes() == raw, f"임시 파일 검증 실패: {path}")
        os.replace(temp_name, path)
    finally:
        temp = Path(temp_name)
        if temp.exists():
            temp.unlink()


def package_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def validate_identity(value: Any, label: str, *, allow_md5: bool = False) -> None:
    require(isinstance(value, dict), f"{label} 해시 정보가 잘못됐습니다")
    allowed = {"size", "sha256"} | ({"md5"} if allow_md5 else set())
    require(set(value) <= allowed and {"size", "sha256"} <= set(value), f"{label} 해시 필드가 잘못됐습니다")
    require(isinstance(value["size"], int) and value["size"] >= 0, f"{label} 크기가 잘못됐습니다")
    require(isinstance(value["sha256"], str) and re.fullmatch(r"[0-9A-F]{64}", value["sha256"]), f"{label} SHA-256이 잘못됐습니다")
    if "md5" in value:
        require(isinstance(value["md5"], str) and re.fullmatch(r"[0-9A-F]{32}", value["md5"]), f"{label} MD5가 잘못됐습니다")


def validate_font_generation(value: Any, *, frozen_legacy: bool = False) -> list[str]:
    require(isinstance(value, dict), "font_generation 형식이 잘못됐습니다")
    require(value.get("schema") == "homm2-font-generation-v1", "지원하지 않는 font_generation 형식입니다")
    mapping = value.get("mapping")
    require(isinstance(mapping, dict) and set(mapping) == {"package_path", "package"}, "폰트 매핑 선언이 잘못됐습니다")
    require(isinstance(mapping["package_path"], str), "폰트 매핑 패키지 경로가 잘못됐습니다")
    validate_identity(mapping["package"], "font mapping package")

    default_font = value.get("default_font")
    require(
        isinstance(default_font, dict)
        and set(default_font) == {"name", "package_path", "package", "face_index", "license_path"},
        "기본 글꼴 선언이 잘못됐습니다",
    )
    require(isinstance(default_font["name"], str) and default_font["name"], "기본 글꼴 이름이 잘못됐습니다")
    require(isinstance(default_font["package_path"], str), "기본 글꼴 패키지 경로가 잘못됐습니다")
    require(isinstance(default_font["license_path"], str), "기본 글꼴 라이선스 경로가 잘못됐습니다")
    normalize_relative(default_font["license_path"])
    require(default_font["face_index"] == 0, "기본 글꼴 face 번호가 잘못됐습니다")
    validate_identity(default_font["package"], "default font package")

    expected_renderer = {
        "id": homm2_font.RENDERER_ID,
        "normal_pixel_size": homm2_font.NORMAL_PIXEL_SIZE,
        "small_pixel_size": homm2_font.SMALL_PIXEL_SIZE,
        "normal_cell": {"width": homm2_font.NORMAL_CELL_WIDTH, "height": homm2_font.NORMAL_CELL_HEIGHT},
        "small_cell": {"width": homm2_font.SMALL_CELL_WIDTH, "height": homm2_font.SMALL_CELL_HEIGHT},
        "shadow_offset": [homm2_font.SHADOW_OFFSET_X, homm2_font.SHADOW_OFFSET_Y],
        "baseline_policy": homm2_font.BASELINE_POLICY,
        "fit_policy": homm2_font.FIT_POLICY,
        "crop_policy": homm2_font.CROP_POLICY,
        "shadow_policy": homm2_font.SHADOW_POLICY,
        "foreground_palette_index": homm2_font.FOREGROUND_PALETTE_INDEX,
        "shadow_palette_index": homm2_font.SHADOW_PALETTE_INDEX,
    }
    legacy_v1_renderer = {
        "id": "pillow-freetype-monochrome-v1",
        "normal_pixel_size": 14,
        "small_pixel_size": 12,
        "foreground_palette_index": 10,
        "shadow_palette_index": 21,
    }
    renderer = value.get("renderer")
    require(
        renderer == expected_renderer
        or (frozen_legacy and renderer in (legacy_v1_renderer, HISTORICAL_V2_RENDERER)),
        "폰트 renderer 규칙이 설치기와 다릅니다",
    )
    expected_layout = {
        "legacy_sprite_count": homm2_font.LEGACY_SPRITE_COUNT,
        "filler_sprite_count": homm2_font.FILLER_SPRITE_COUNT,
        "first_index": homm2_font.KOREAN_FIRST_INDEX,
        "last_index": homm2_font.KOREAN_LAST_INDEX,
        "glyph_count": homm2_font.KOREAN_GLYPH_COUNT,
        "final_sprite_count": homm2_font.FINAL_SPRITE_COUNT,
        "blank_legacy_sprite_index": homm2_font.AT_SIGN_SPRITE_INDEX,
    }
    require(value.get("layout") == expected_layout, "폰트 sprite 배치 규칙이 설치기와 다릅니다")
    return [mapping["package_path"], default_font["package_path"]]


def validate_upgrades(value: Any, current_version: str) -> list[str]:
    if value is None:
        return []
    require(isinstance(value, dict) and set(value) == {"schema", "from"}, "upgrades 선언이 잘못됐습니다")
    require(value.get("schema") == "homm2-korean-upgrades-v1", "지원하지 않는 upgrades 형식입니다")
    sources = value.get("from")
    require(isinstance(sources, list), "upgrades from 목록이 잘못됐습니다")
    versions: list[str] = []
    package_paths: list[str] = []
    for index, descriptor in enumerate(sources):
        require(
            isinstance(descriptor, dict)
            and set(descriptor) == {"version", "manifest_path", "manifest"},
            f"upgrade 항목이 잘못됐습니다: {index}",
        )
        version = descriptor["version"]
        require(
            isinstance(version, str)
            and re.fullmatch(r"v[0-9A-Za-z][0-9A-Za-z._+-]{0,63}", version) is not None
            and version != current_version,
            f"upgrade 이전 버전이 잘못됐습니다: {index}",
        )
        manifest_path = descriptor["manifest_path"]
        require(isinstance(manifest_path, str), f"upgrade manifest 경로가 잘못됐습니다: {index}")
        normalized = normalize_relative(manifest_path).as_posix()
        require(normalized.casefold() != "manifest.json", "upgrade manifest는 현재 manifest와 다른 경로여야 합니다")
        validate_identity(descriptor["manifest"], f"upgrade manifest {version}")
        versions.append(version.casefold())
        package_paths.append(normalized)
    require(len(versions) == len(set(versions)), "upgrade 이전 버전이 중복됐습니다")
    folded_paths = [path.casefold() for path in package_paths]
    require(len(folded_paths) == len(set(folded_paths)), "upgrade manifest 경로가 중복됐습니다")
    return package_paths


def validate_manifest_document(manifest: Any, *, frozen_legacy: bool = False) -> list[str]:
    require(isinstance(manifest, dict), "manifest 최상위 형식이 잘못됐습니다")
    require(manifest.get("schema") == "homm2-korean-release-manifest-v2", "지원하지 않는 manifest 형식입니다")
    version = manifest.get("version")
    require(
        isinstance(version, str) and re.fullmatch(r"v[0-9A-Za-z][0-9A-Za-z._+-]{0,63}", version) is not None,
        "manifest 버전이 잘못됐습니다",
    )
    game = manifest.get("game")
    require(isinstance(game, dict), "manifest 게임 정보가 잘못됐습니다")
    require(game.get("game_id") == GAME_ID, "게임 ID가 맞지 않습니다")
    require(game.get("build_id") == BUILD_ID, "GOG 빌드 ID가 맞지 않습니다")
    require(game.get("language") == "English", "manifest 언어 정보가 잘못됐습니다")
    files = manifest.get("files")
    require(isinstance(files, list) and files, "manifest 파일 목록이 비었습니다")
    paths: list[str] = []
    package_paths: list[str] = []
    for index, row in enumerate(files):
        require(isinstance(row, dict), f"manifest 파일 항목이 잘못됐습니다: {index}")
        require(isinstance(row.get("path"), str), f"manifest 설치 경로가 잘못됐습니다: {index}")
        require(isinstance(row.get("package_path"), str), f"manifest 패키지 경로가 잘못됐습니다: {index}")
        installed_path = normalize_relative(row["path"]).as_posix().casefold()
        package_path = normalize_relative(row["package_path"]).as_posix().casefold()
        paths.append(installed_path)
        package_paths.append(package_path)
        method = row.get("method")
        require(method in SUPPORTED_METHODS, f"manifest 설치 방식이 잘못됐습니다: {row['path']}")
        validate_identity(row.get("package"), f"package {row['path']}")
        if method == "bsdiff40":
            validate_identity(row.get("source"), f"source {row['path']}", allow_md5=True)
            validate_identity(row.get("target"), f"target {row['path']}")
            require(row.get("base_target") is None, f"정적 패치에 base_target이 있으면 안 됩니다: {row['path']}")
            require(row.get("keep_localized_resources") is None, f"정적 패치에 AGG 리소스 목록이 있으면 안 됩니다: {row['path']}")
        elif method == "copy":
            require(row.get("source") is None, f"copy source는 null이어야 합니다: {row['path']}")
            validate_identity(row.get("target"), f"target {row['path']}")
            require(row.get("base_target") is None, f"copy에 base_target이 있으면 안 됩니다: {row['path']}")
            require(row.get("keep_localized_resources") is None, f"copy에 AGG 리소스 목록이 있으면 안 됩니다: {row['path']}")
        else:
            validate_identity(row.get("source"), f"source {row['path']}", allow_md5=True)
            validate_identity(row.get("base_target"), f"base target {row['path']}")
            require(row.get("target") is None, f"동적 AGG target은 null이어야 합니다: {row['path']}")
            resources = row.get("keep_localized_resources")
            require(isinstance(resources, list), f"AGG 유지 리소스 목록이 잘못됐습니다: {row['path']}")
            folded_resources: list[str] = []
            for resource in resources:
                require(
                    isinstance(resource, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,15}", resource),
                    f"AGG 리소스 이름이 잘못됐습니다: {row['path']}",
                )
                folded_resources.append(resource.casefold())
            require(len(folded_resources) == len(set(folded_resources)), f"AGG 유지 리소스가 중복됐습니다: {row['path']}")
    require(len(paths) == len(set(paths)), "manifest 설치 경로가 중복됐습니다")
    font_package_paths = [
        normalize_relative(path).as_posix().casefold()
        for path in validate_font_generation(manifest.get("font_generation"), frozen_legacy=frozen_legacy)
    ]
    upgrade_package_paths = [path.casefold() for path in validate_upgrades(manifest.get("upgrades"), version)]
    all_package_paths = package_paths + font_package_paths + upgrade_package_paths
    require(len(all_package_paths) == len(set(all_package_paths)), "manifest 패키지 경로가 중복됐습니다")
    dynamic_paths = {
        str(row["path"]).replace("\\", "/").casefold()
        for row in files
        if row["method"] == DYNAMIC_FONT_AGG_METHOD
    }
    require(
        dynamic_paths == {"data/heroes2.agg", "data/heroes2x.agg"},
        "동적 폰트 AGG 대상은 HEROES2.AGG와 HEROES2X.AGG여야 합니다",
    )
    require(len(files) == 51, "설치 파일 목록은 51개여야 합니다")
    return upgrade_package_paths


def load_manifest() -> tuple[Path, dict[str, Any], str]:
    root = package_root()
    path = root / "manifest.json"
    require(path.is_file(), f"배포 manifest가 없습니다: {path}")
    manifest_raw = path.read_bytes()
    manifest = json.loads(manifest_raw.decode("utf-8"))
    validate_manifest_document(manifest)
    return root, manifest, sha256_bytes(manifest_raw)


def normalize_relative(value: str) -> Path:
    value = value.replace("\\", "/")
    candidate = Path(value)
    require(not candidate.is_absolute(), f"절대경로는 허용되지 않습니다: {value}")
    require(value not in {"", "."} and ".." not in candidate.parts, f"안전하지 않은 상대경로입니다: {value}")
    return candidate


def within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=True))
        return True
    except (OSError, ValueError):
        return False


def checked_target(root: Path, relative: str) -> Path:
    rel = normalize_relative(relative)
    target = root / rel
    require(within(target, root), f"대상 경로가 게임 폴더 밖입니다: {relative}")
    return target


def detect_game_dir(explicit: str | None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    candidates.append(DEFAULT_GOG_DIR)
    if os.name == "nt" and os.environ.get("ProgramFiles(x86)"):
        candidates.append(Path(os.environ["ProgramFiles(x86)"]) / "GOG Galaxy" / "Games" / "HoMM 2 Gold")
    candidates.extend((Path.cwd(), package_root().parent))
    if os.name == "nt":
        try:
            import winreg

            keys = (
                (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\GOG.com\Games\{GAME_ID}"),
                (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\GOG.com\Games\{GAME_ID}"),
                (winreg.HKEY_CURRENT_USER, rf"SOFTWARE\GOG.com\Games\{GAME_ID}"),
            )
            for hive, key_name in keys:
                try:
                    with winreg.OpenKey(hive, key_name) as key:
                        value, _ = winreg.QueryValueEx(key, "path")
                        candidates.append(Path(value))
                except OSError:
                    pass
        except ImportError:
            pass
    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve(strict=True)
        except OSError:
            continue
        key = str(resolved).casefold()
        if key in seen:
            continue
        seen.add(key)
        if (resolved / INFO_NAME).is_file() and (resolved / "HEROES2.EXE").is_file():
            return resolved
    if explicit:
        raise PatchError(f"지정한 폴더가 지원되는 GOG 설치본이 아닙니다: {explicit}")
    raise PatchError("게임 설치 폴더를 찾지 못했습니다. --game-dir 옵션으로 지정해 주세요.")


def validate_game_info(game: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    path = game / INFO_NAME
    info = json.loads(path.read_text(encoding="utf-8-sig"))
    expected = manifest["game"]
    require(str(info.get("gameId")) == expected["game_id"], "GOG gameId가 맞지 않습니다")
    require(str(info.get("buildId")) == expected["build_id"], "지원하지 않는 GOG 빌드입니다")
    require(str(info.get("language", "")).casefold() == expected["language"].casefold(), "영문 GOG 설치본만 지원합니다")
    return info


def running_blockers() -> list[dict[str, str]]:
    if os.name != "nt":
        return []
    completed = subprocess.run(
        ["tasklist.exe", "/FO", "CSV", "/NH"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    require(completed.returncode == 0, "실행 중인 프로그램을 확인하지 못했습니다")
    found: list[dict[str, str]] = []
    for row in csv.reader(completed.stdout.splitlines()):
        if len(row) >= 2 and row[0].casefold() in BLOCKED_PROCESSES:
            found.append({"image": row[0], "pid": row[1]})
    return found


def require_no_blockers() -> None:
    blockers = running_blockers()
    require(not blockers, f"게임·DOSBox·GOG Galaxy를 먼저 종료해 주세요: {blockers}")


def decode_offt(raw: bytes) -> int:
    require(len(raw) == 8, "BSDIFF 정수 길이가 잘못됐습니다")
    value = raw[7] & 0x7F
    for index in range(6, -1, -1):
        value = value * 256 + raw[index]
    return -value if raw[7] & 0x80 else value


def apply_bsdiff(old: bytes, patch: bytes) -> bytes:
    require(len(patch) >= 32 and patch[:8] == b"BSDIFF40", "BSDIFF40 패치가 아닙니다")
    control_length = decode_offt(patch[8:16])
    diff_length = decode_offt(patch[16:24])
    new_size = decode_offt(patch[24:32])
    require(control_length >= 0 and diff_length >= 0 and new_size >= 0, "BSDIFF 헤더가 잘못됐습니다")
    diff_start = 32 + control_length
    extra_start = diff_start + diff_length
    require(extra_start <= len(patch), "BSDIFF 블록 경계가 잘못됐습니다")
    try:
        control = bz2.decompress(patch[32:diff_start])
        diff = bz2.decompress(patch[diff_start:extra_start])
        extra = bz2.decompress(patch[extra_start:])
    except OSError as exc:
        raise PatchError(f"BSDIFF 압축 해제 실패: {exc}") from exc
    output = bytearray(new_size)
    old_pos = new_pos = control_pos = diff_pos = extra_pos = 0
    while new_pos < new_size:
        require(control_pos + 24 <= len(control), "BSDIFF control 블록이 짧습니다")
        add_length = decode_offt(control[control_pos : control_pos + 8])
        copy_length = decode_offt(control[control_pos + 8 : control_pos + 16])
        seek_length = decode_offt(control[control_pos + 16 : control_pos + 24])
        control_pos += 24
        require(add_length >= 0 and copy_length >= 0, "BSDIFF control 값이 잘못됐습니다")
        require(new_pos + add_length <= new_size and diff_pos + add_length <= len(diff), "BSDIFF diff 범위를 벗어났습니다")
        output[new_pos : new_pos + add_length] = diff[diff_pos : diff_pos + add_length]
        for index in range(add_length):
            source_index = old_pos + index
            if 0 <= source_index < len(old):
                output[new_pos + index] = (output[new_pos + index] + old[source_index]) & 0xFF
        new_pos += add_length
        old_pos += add_length
        diff_pos += add_length
        require(new_pos + copy_length <= new_size and extra_pos + copy_length <= len(extra), "BSDIFF extra 범위를 벗어났습니다")
        output[new_pos : new_pos + copy_length] = extra[extra_pos : extra_pos + copy_length]
        new_pos += copy_length
        extra_pos += copy_length
        old_pos += seek_length
    require(new_pos == new_size, "BSDIFF 출력 길이가 맞지 않습니다")
    return bytes(output)


def verify_package_file(package: Path, row: dict[str, Any]) -> Path:
    relative = normalize_relative(str(row["package_path"]))
    path = package / relative
    require(within(path, package), f"패키지 경로가 배포 폴더 밖입니다: {relative}")
    expected = row["package"]
    require(file_identity(path) == expected, f"패키지 파일이 손상됐습니다: {relative}")
    return path


def verify_package_artifact(package: Path, descriptor: dict[str, Any], label: str) -> Path:
    relative = normalize_relative(str(descriptor["package_path"]))
    path = package / relative
    require(within(path, package), f"{label} 경로가 배포 폴더 밖입니다: {relative}")
    require(file_identity(path) == descriptor["package"], f"{label} 파일이 손상됐습니다: {relative}")
    return path


def prepare_font_plan(
    package: Path,
    manifest: dict[str, Any],
    font_file: str | None = None,
    font_index: int = 0,
) -> homm2_font.FontPlan:
    generation = manifest["font_generation"]
    mapping_path = verify_package_artifact(package, generation["mapping"], "글자 매핑")
    default_path = verify_package_artifact(package, generation["default_font"], "기본 나눔고딕코딩")
    require(font_index >= 0, "글꼴 face 번호는 0 이상이어야 합니다")
    if font_file is None:
        require(
            font_index == generation["default_font"]["face_index"],
            "기본 글꼴 face 번호는 0입니다",
        )
        plan = homm2_font.make_font_plan(
            mapping_path,
            default_path,
            primary_face_index=font_index,
            mode="default",
        )
    else:
        selected = Path(font_file)
        print("사용자 글꼴 모드: 선택한 파일은 이 PC에서만 읽으며 복사·수집·배포하지 않습니다.")
        print("선택한 글꼴의 이용 조건을 확인할 책임은 사용자에게 있으며 설치기는 라이선스로 차단하지 않습니다.")
        plan = homm2_font.make_font_plan(
            mapping_path,
            selected,
            primary_face_index=font_index,
            fallback_path=default_path,
            fallback_face_index=generation["default_font"]["face_index"],
            mode="custom",
        )
    metadata = plan.metadata()
    print(
        f"글꼴 준비: {metadata['primary']['family'] or metadata['primary']['file_name']} "
        f"(선택 {metadata['primary_glyph_count']}자, "
        f"나눔고딕코딩 대체 {metadata['fallback_glyph_count']}자)"
    )
    return plan


def choose_font_file() -> str:
    require(os.name == "nt", "--choose-font는 Windows에서만 사용할 수 있습니다. --font-file로 지정해 주세요.")
    import ctypes
    from ctypes import wintypes

    class OpenFileNameW(ctypes.Structure):
        _fields_ = [
            ("lStructSize", wintypes.DWORD),
            ("hwndOwner", wintypes.HWND),
            ("hInstance", wintypes.HINSTANCE),
            ("lpstrFilter", wintypes.LPCWSTR),
            ("lpstrCustomFilter", wintypes.LPWSTR),
            ("nMaxCustFilter", wintypes.DWORD),
            ("nFilterIndex", wintypes.DWORD),
            ("lpstrFile", wintypes.LPWSTR),
            ("nMaxFile", wintypes.DWORD),
            ("lpstrFileTitle", wintypes.LPWSTR),
            ("nMaxFileTitle", wintypes.DWORD),
            ("lpstrInitialDir", wintypes.LPCWSTR),
            ("lpstrTitle", wintypes.LPCWSTR),
            ("Flags", wintypes.DWORD),
            ("nFileOffset", wintypes.WORD),
            ("nFileExtension", wintypes.WORD),
            ("lpstrDefExt", wintypes.LPCWSTR),
            ("lCustData", wintypes.LPARAM),
            ("lpfnHook", ctypes.c_void_p),
            ("lpTemplateName", wintypes.LPCWSTR),
            ("pvReserved", ctypes.c_void_p),
            ("dwReserved", wintypes.DWORD),
            ("FlagsEx", wintypes.DWORD),
        ]

    buffer = ctypes.create_unicode_buffer(32768)
    dialog = OpenFileNameW()
    dialog.lStructSize = ctypes.sizeof(OpenFileNameW)
    dialog.lpstrFilter = "글꼴 파일 (*.ttf;*.otf;*.ttc;*.otc)\0*.ttf;*.otf;*.ttc;*.otc\0모든 파일 (*.*)\0*.*\0\0"
    dialog.nFilterIndex = 1
    dialog.lpstrFile = ctypes.cast(buffer, wintypes.LPWSTR)
    dialog.nMaxFile = len(buffer)
    dialog.lpstrTitle = "Heroes II 한국어 패치에 사용할 글꼴 선택"
    dialog.Flags = 0x00080000 | 0x00001000 | 0x00000800 | 0x00000008
    if ctypes.windll.comdlg32.GetOpenFileNameW(ctypes.byref(dialog)):
        return buffer.value
    extended_error = ctypes.windll.comdlg32.CommDlgExtendedError()
    if extended_error == 0:
        raise PatchError("글꼴 선택을 취소했습니다")
    raise PatchError(f"글꼴 선택 창 오류: 0x{extended_error:08X}")


def verify_originals(game: Path, files: Iterable[dict[str, Any]]) -> dict[str, dict[str, int | str]]:
    identities: dict[str, dict[str, int | str]] = {}
    for row in files:
        relative = str(row["path"])
        source = checked_target(game, relative)
        actual = file_identity(source)
        require(identity_matches(actual, row["source"]), f"원본 해시가 맞지 않습니다: {relative}")
        identities[relative] = actual
    return identities


def stage_outputs(
    package: Path,
    game: Path,
    manifest: dict[str, Any],
    stage: Path,
    font_plan: homm2_font.FontPlan,
    source_paths: dict[str, Path] | None = None,
) -> tuple[dict[str, dict[str, int | str]], dict[str, Any]]:
    print(f"한글 글리프 {homm2_font.KOREAN_GLYPH_COUNT}자를 일반/작은 글꼴로 생성합니다...")
    rendered = homm2_font.render_font(font_plan)
    identities: dict[str, dict[str, int | str]] = {}
    for index, row in enumerate(manifest["files"], 1):
        relative = str(row["path"])
        source = source_paths[relative] if source_paths is not None and row["method"] != "copy" else checked_target(game, relative)
        if source_paths is not None and row["method"] != "copy":
            require(source.is_file(), f"upgrade 원본 백업이 없습니다: {relative}")
        package_file = verify_package_file(package, row)
        print(f"[{index:02d}/{len(manifest['files']):02d}] 생성: {relative}")
        source_raw = source.read_bytes() if row["method"] != "copy" else b""
        if row["method"] == "bsdiff40":
            output = apply_bsdiff(source_raw, package_file.read_bytes())
        elif row["method"] == DYNAMIC_FONT_AGG_METHOD:
            base = apply_bsdiff(source_raw, package_file.read_bytes())
            require(
                {"size": len(base), "sha256": sha256_bytes(base)} == row["base_target"],
                f"font/raster-free AGG 기반 검증 실패: {relative}",
            )
            changed = {name.casefold() for name in homm2_font.changed_agg_resources(source_raw, base, label=relative)}
            expected = {str(name).casefold() for name in row["keep_localized_resources"]}
            require(changed == expected, f"AGG 기반의 변경 리소스 집합이 잘못됐습니다: {relative}: {sorted(changed)}")
            output = homm2_font.rebuild_agg_fonts(
                base,
                rendered,
                label=relative,
            )
        elif row["method"] == "copy":
            output = package_file.read_bytes()
        else:
            raise PatchError(f"지원하지 않는 설치 방식입니다: {row['method']}")
        actual = {"size": len(output), "sha256": sha256_bytes(output)}
        if row["method"] in STATIC_METHODS:
            require(actual == row["target"], f"생성 결과 검증 실패: {relative}")
        target = checked_target(stage, relative)
        atomic_write(target, output)
        identities[relative] = actual
    return identities, rendered.metadata


def receipt_paths(game: Path, version: str) -> tuple[Path, Path, Path]:
    state = checked_target(game, STATE_DIR_NAME)
    if state.exists():
        require(state.is_dir(), f"상태 경로가 폴더가 아닙니다: {state}")
    return state, state / RECEIPT_NAME, state / JOURNAL_NAME


@contextmanager
def operation_lock(game: Path) -> Iterable[None]:
    state, _, _ = receipt_paths(game, "")
    state.mkdir(parents=True, exist_ok=True)
    require(within(state, game), "상태 폴더가 게임 폴더 밖입니다")
    lock_path = checked_target(game, f"{STATE_DIR_NAME}/operation.lock")
    require(within(lock_path, state), "잠금 파일 경로가 상태 폴더 밖입니다")
    with lock_path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
            os.fsync(stream.fileno())
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise PatchError("다른 패치 작업이 이미 실행 중입니다") from exc
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise PatchError("다른 패치 작업이 이미 실행 중입니다") from exc
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def read_json(path: Path) -> dict[str, Any]:
    require(path.is_file(), f"상태 파일이 없습니다: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"상태 파일 형식이 잘못됐습니다: {path}")
    return value


def load_upgrade_manifest(
    package: Path,
    current_manifest: dict[str, Any],
    previous_version: str,
    previous_manifest_sha256: str,
) -> tuple[dict[str, Any], str]:
    upgrades = current_manifest.get("upgrades")
    require(isinstance(upgrades, dict), f"{previous_version}에서 직접 upgrade하는 정보가 없습니다")
    descriptors = upgrades.get("from")
    require(isinstance(descriptors, list), "upgrade 이전 버전 목록이 잘못됐습니다")
    matches = [item for item in descriptors if isinstance(item, dict) and item.get("version") == previous_version]
    require(len(matches) == 1, f"지원하지 않는 직접 upgrade 버전입니다: {previous_version}")
    descriptor = matches[0]
    relative = normalize_relative(str(descriptor["manifest_path"]))
    path = package / relative
    require(within(path, package), f"upgrade manifest 경로가 배포 폴더 밖입니다: {relative}")
    expected = descriptor["manifest"]
    require(file_identity(path) == expected, f"upgrade manifest가 손상됐습니다: {relative}")
    raw = path.read_bytes()
    actual_sha256 = sha256_bytes(raw)
    require(actual_sha256 == previous_manifest_sha256, "설치 기록과 upgrade manifest가 일치하지 않습니다")
    previous = json.loads(raw.decode("utf-8"))
    validate_manifest_document(previous, frozen_legacy=True)
    require(previous.get("version") == previous_version, "upgrade manifest 버전이 설치 기록과 다릅니다")
    require(previous.get("game") == current_manifest.get("game"), "upgrade manifest의 게임 대상이 현재 배포판과 다릅니다")
    return previous, actual_sha256


def expected_before(row: dict[str, Any]) -> dict[str, int | str] | None:
    if row["method"] == "copy":
        return None
    source = row["source"]
    return {"size": source["size"], "sha256": source["sha256"]}


def validate_font_face_receipt(value: Any, label: str) -> dict[str, int | str]:
    require(isinstance(value, dict), f"{label} 글꼴 정보가 잘못됐습니다")
    expected_keys = {
        "file_name",
        "size",
        "sha256",
        "face_index",
        "face_count",
        "family",
        "subfamily",
        "full_name",
        "postscript_name",
    }
    require(set(value) == expected_keys, f"{label} 글꼴 정보 필드가 잘못됐습니다")
    name = value["file_name"]
    require(
        isinstance(name, str) and name and Path(name).name == name and "/" not in name and "\\" not in name,
        f"{label} 글꼴 파일명이 잘못됐습니다",
    )
    identity = {"size": value["size"], "sha256": value["sha256"]}
    validate_identity(identity, f"{label} font")
    require(
        isinstance(value["face_index"], int)
        and isinstance(value["face_count"], int)
        and 0 <= value["face_index"] < value["face_count"],
        f"{label} 글꼴 face 정보가 잘못됐습니다",
    )
    for key in ("family", "subfamily", "full_name", "postscript_name"):
        require(isinstance(value[key], str), f"{label} 글꼴 이름 정보가 잘못됐습니다: {key}")
    return identity


def validate_resolved_font_face(
    value: Any,
    label: str,
    *,
    requested: int,
    width: int,
    height: int,
    bearing_baseline: bool,
) -> int:
    keys = {
        "requested_pixel_size",
        "resolved_pixel_size",
        "cell_width",
        "cell_height",
        "origin_x",
        "baseline_y",
        "ink_union",
        "glyph_count",
        "foreground_clip_count",
        "shadow_edge_clip_count",
    }
    require(isinstance(value, dict) and set(value) == keys, f"{label} 글꼴 layout 정보가 잘못됐습니다")
    require(
        type(value["requested_pixel_size"]) is int and value["requested_pixel_size"] == requested,
        f"{label} 요청 pixel 크기가 다릅니다",
    )
    require(
        type(value["resolved_pixel_size"]) is int
        and homm2_font.MINIMUM_PIXEL_SIZE <= value["resolved_pixel_size"] <= requested,
        f"{label} 확정 pixel 크기가 잘못됐습니다",
    )
    require(
        type(value["cell_width"]) is int
        and type(value["cell_height"]) is int
        and value["cell_width"] == width
        and value["cell_height"] == height,
        f"{label} cell 크기가 다릅니다",
    )
    ink = value["ink_union"]
    require(
        isinstance(ink, list)
        and len(ink) == 4
        and all(type(item) is int for item in ink)
        and ink[0] < ink[2]
        and ink[1] < ink[3],
        f"{label} ink 범위가 잘못됐습니다",
    )
    require(
        -width <= ink[0]
        and ink[2] <= width * 2
        and ink[2] - ink[0] <= width * 2
        and -height <= ink[1]
        and ink[3] <= height,
        f"{label} ink 범위가 논리 cell을 벗어났습니다",
    )
    baseline_y = value["baseline_y"]
    require(
        type(value["origin_x"]) is int
        and type(baseline_y) is int
        and value["origin_x"] == width // 2,
        f"{label} 글꼴 원점이 잘못됐습니다",
    )
    if bearing_baseline:
        require(
            ink[3] - ink[1] <= height
            and baseline_y == -ink[1]
            and baseline_y + ink[1] == 0
            and baseline_y + ink[3] <= height,
            f"{label} 글꼴 bearing 기준선 원점이 잘못됐습니다",
        )
    else:
        require(baseline_y == height, f"{label} 글꼴 원점이 잘못됐습니다")
    require(
        type(value["glyph_count"]) is int and 0 < value["glyph_count"] <= homm2_font.KOREAN_GLYPH_COUNT,
        f"{label} 글립 수가 잘못됐습니다",
    )
    require(
        type(value["foreground_clip_count"]) is int and value["foreground_clip_count"] == 0,
        f"{label} 전경 글립이 잘렸습니다",
    )
    maximum_shadow_clips = value["glyph_count"] * width * height
    require(
        type(value["shadow_edge_clip_count"]) is int
        and 0 <= value["shadow_edge_clip_count"] <= maximum_shadow_clips,
        f"{label} 그림자 clip 수가 잘못됐습니다",
    )
    return value["glyph_count"]


def validate_font_receipt(value: Any, manifest: dict[str, Any]) -> None:
    require(isinstance(value, dict), "설치 기록의 글꼴 생성 정보가 잘못됐습니다")
    require(value.get("schema") == "homm2-generated-font-receipt-v1", "설치 기록의 글꼴 schema가 잘못됐습니다")
    require(value.get("mode") in {"default", "custom"}, "설치 기록의 글꼴 모드가 잘못됐습니다")
    generation = manifest["font_generation"]
    renderer = generation["renderer"]
    layout = generation["layout"]
    base_keys = {
        "schema",
        "mode",
        "renderer",
        "normal_pixel_size",
        "small_pixel_size",
        "mapping_glyph_count",
        "first_index",
        "last_index",
        "blank_legacy_sprite_index",
        "primary_glyph_count",
        "fallback_glyph_count",
        "primary",
        "fallback",
    }
    structured_keys = {
        "normal_cell",
        "small_cell",
        "shadow_offset",
        "baseline_policy",
        "fit_policy",
        "crop_policy",
        "shadow_policy",
        "resolved_faces",
    }
    renderer_id = renderer.get("id")
    current_renderer = renderer_id == homm2_font.RENDERER_ID
    historical_v2_renderer = renderer == HISTORICAL_V2_RENDERER
    structured_renderer = current_renderer or historical_v2_renderer
    resolved_glyph_counts: dict[str, int] = {}
    if structured_renderer:
        require(set(value) == base_keys | structured_keys, "설치 기록의 구조화 글꼴 필드가 잘못됐습니다")
        normal_cell = value.get("normal_cell")
        require(
            isinstance(normal_cell, dict)
            and set(normal_cell) == {"width", "height"}
            and type(normal_cell["width"]) is int
            and type(normal_cell["height"]) is int
            and normal_cell
            == renderer["normal_cell"],
            "설치 기록의 일반 글꼴 cell이 다릅니다",
        )
        small_cell = value.get("small_cell")
        require(
            isinstance(small_cell, dict)
            and set(small_cell) == {"width", "height"}
            and type(small_cell["width"]) is int
            and type(small_cell["height"]) is int
            and small_cell
            == renderer["small_cell"],
            "설치 기록의 작은 글꼴 cell이 다릅니다",
        )
        shadow_offset = value.get("shadow_offset")
        require(
            isinstance(shadow_offset, list)
            and len(shadow_offset) == 2
            and all(type(item) is int for item in shadow_offset)
            and shadow_offset == renderer["shadow_offset"],
            "설치 기록의 글꼴 그림자 규칙이 다릅니다",
        )
        require(value.get("baseline_policy") == renderer["baseline_policy"], "설치 기록의 baseline 규칙이 다릅니다")
        require(value.get("fit_policy") == renderer["fit_policy"], "설치 기록의 글꼴 fit 규칙이 다릅니다")
        require(value.get("crop_policy") == renderer["crop_policy"], "설치 기록의 글꼴 crop 규칙이 다릅니다")
        require(value.get("shadow_policy") == renderer["shadow_policy"], "설치 기록의 글꼴 shadow 규칙이 다릅니다")
        resolved_faces = value.get("resolved_faces")
        require(isinstance(resolved_faces, dict) and set(resolved_faces) == {"primary", "fallback"}, "설치 기록의 확정 face 정보가 잘못됐습니다")
        require(resolved_faces["primary"] is not None, "설치 기록의 선택 글꼴 layout이 없습니다")
        for face_label in ("primary", "fallback"):
            resolved = resolved_faces[face_label]
            if resolved is None:
                resolved_glyph_counts[face_label] = 0
                continue
            require(isinstance(resolved, dict) and set(resolved) == {"normal", "small"}, f"{face_label} 확정 face 형식이 잘못됐습니다")
            if resolved["normal"] is None or resolved["small"] is None:
                require(
                    resolved["normal"] is None and resolved["small"] is None,
                    f"{face_label} 일반/작은 글꼴 layout 유무가 다릅니다",
                )
                resolved_glyph_counts[face_label] = 0
                continue
            normal_count = validate_resolved_font_face(
                resolved["normal"],
                f"{face_label} 일반",
                requested=renderer["normal_pixel_size"],
                width=renderer["normal_cell"]["width"],
                height=renderer["normal_cell"]["height"],
                bearing_baseline=current_renderer,
            )
            small_count = validate_resolved_font_face(
                resolved["small"],
                f"{face_label} 작은",
                requested=renderer["small_pixel_size"],
                width=renderer["small_cell"]["width"],
                height=renderer["small_cell"]["height"],
                bearing_baseline=current_renderer,
            )
            require(normal_count == small_count, f"{face_label} 일반/작은 글꼴의 글립 수가 다릅니다")
            resolved_glyph_counts[face_label] = normal_count
    else:
        require(renderer["id"] == "pillow-freetype-monochrome-v1", "설치 기록의 legacy renderer가 잘못됐습니다")
        require(set(value) == base_keys, "설치 기록의 legacy 글꼴 필드가 잘못됐습니다")
    require(isinstance(value.get("renderer"), str) and value["renderer"] == renderer["id"], "설치 기록의 renderer가 manifest와 다릅니다")
    require(
        type(value.get("normal_pixel_size")) is int and value["normal_pixel_size"] == renderer["normal_pixel_size"],
        "설치 기록의 일반 글꼴 크기가 다릅니다",
    )
    require(
        type(value.get("small_pixel_size")) is int and value["small_pixel_size"] == renderer["small_pixel_size"],
        "설치 기록의 작은 글꼴 크기가 다릅니다",
    )
    require(
        type(value.get("mapping_glyph_count")) is int and value["mapping_glyph_count"] == layout["glyph_count"],
        "설치 기록의 매핑 글자 수가 다릅니다",
    )
    require(
        type(value.get("first_index")) is int and value["first_index"] == layout["first_index"],
        "설치 기록의 첫 글리프 인덱스가 다릅니다",
    )
    require(
        type(value.get("last_index")) is int and value["last_index"] == layout["last_index"],
        "설치 기록의 마지막 글리프 인덱스가 다릅니다",
    )
    require(
        type(value.get("blank_legacy_sprite_index")) is int
        and value["blank_legacy_sprite_index"] == layout["blank_legacy_sprite_index"],
        "설치 기록의 @ 글리프 규칙이 다릅니다",
    )
    primary_count = value.get("primary_glyph_count")
    fallback_count = value.get("fallback_glyph_count")
    require(
        type(primary_count) is int
        and type(fallback_count) is int
        and primary_count >= 0
        and fallback_count >= 0
        and primary_count + fallback_count == layout["glyph_count"],
        "설치 기록의 선택/대체 글리프 수가 잘못됐습니다",
    )
    if structured_renderer:
        require(resolved_glyph_counts.get("primary") == primary_count, "선택 글꼴 layout의 글립 수가 다릅니다")
        require(resolved_glyph_counts.get("fallback", 0) == fallback_count, "대체 글꼴 layout의 글립 수가 다릅니다")
    primary_identity = validate_font_face_receipt(value.get("primary"), "선택")
    fallback_value = value.get("fallback")
    fallback_identity = validate_font_face_receipt(fallback_value, "대체") if fallback_value is not None else None
    if structured_renderer:
        require(
            (value["resolved_faces"]["fallback"] is None) == (fallback_value is None),
            "설치 기록의 대체 글꼴 layout과 face 정보가 다릅니다",
        )
    default_identity = generation["default_font"]["package"]
    if value["mode"] == "default":
        require(primary_identity == default_identity, "기본 설치 기록의 글꼴이 나눔고딕코딩이 아닙니다")
        require(fallback_identity is None and fallback_count == 0, "기본 설치 기록에 불필요한 대체 글꼴이 있습니다")
    else:
        if fallback_count:
            require(fallback_identity == default_identity, "사용자 글꼴의 대체 글꼴이 나눔고딕코딩이 아닙니다")
        else:
            require(fallback_identity is None, "사용자 글꼴 설치 기록에 불필요한 대체 글꼴이 있습니다")


def backup_root_for(game: Path, run_id: str) -> Path:
    require(bool(RUN_ID_PATTERN.fullmatch(run_id)), "상태 run_id가 잘못됐습니다")
    state = checked_target(game, STATE_DIR_NAME)
    root = state / "backups" / run_id
    require(within(root, game), "백업 경로가 게임 폴더 밖입니다")
    require(within(root, state), "백업 경로가 상태 폴더 밖입니다")
    return root


def backup_file_for(game: Path, run_id: str, kind: str, relative: str) -> Path:
    require(kind in {"root", "cloud_saves", "upgrade_root"}, "백업 종류가 잘못됐습니다")
    root = backup_root_for(game, run_id)
    target = root / kind / normalize_relative(relative)
    require(within(target, root), f"백업 파일 경로가 안전하지 않습니다: {relative}")
    return target


def validate_state_document(
    document: dict[str, Any],
    manifest: dict[str, Any],
    manifest_sha256: str,
    *,
    schema: str,
    require_committed: bool,
) -> list[dict[str, Any]]:
    require(document.get("schema") == schema, "상태 파일 schema가 잘못됐습니다")
    require(document.get("version") == manifest["version"], "상태 파일 버전이 현재 배포판과 다릅니다")
    require(document.get("manifest_sha256") == manifest_sha256, "상태 파일이 현재 manifest와 일치하지 않습니다")
    run_id = document.get("run_id")
    require(isinstance(run_id, str) and RUN_ID_PATTERN.fullmatch(run_id) is not None, "상태 run_id가 잘못됐습니다")
    validate_font_receipt(document.get("font_generation"), manifest)
    records = document.get("records")
    require(isinstance(records, list) and len(records) == len(manifest["files"]), "상태 파일의 설치 파일 수가 잘못됐습니다")
    for index, (record, row) in enumerate(zip(records, manifest["files"])):
        require(isinstance(record, dict), f"상태 record가 잘못됐습니다: {index}")
        require(record.get("path") == row["path"], f"상태 경로가 manifest와 다릅니다: {index}")
        if row["method"] == DYNAMIC_FONT_AGG_METHOD:
            validate_identity(record.get("installed"), f"generated target {row['path']}")
        else:
            require(record.get("installed") == row["target"], f"설치 해시가 manifest와 다릅니다: {row['path']}")
        require(record.get("root_before") == expected_before(row), f"원본 상태가 manifest와 다릅니다: {row['path']}")
        cloud_before = record.get("cloud_before")
        if cloud_before is not None:
            validate_identity(cloud_before, f"cloud backup {row['path']}")
        require(isinstance(record.get("committed"), bool), f"commit 상태가 잘못됐습니다: {row['path']}")
        if require_committed:
            require(record["committed"] is True, f"완료되지 않은 설치 record입니다: {row['path']}")
    return records


def validate_backup_files(game: Path, document: dict[str, Any], records: Iterable[dict[str, Any]]) -> None:
    run_id = str(document["run_id"])
    expected_root = backup_root_for(game, run_id)
    require(expected_root.is_dir(), "백업 폴더가 없습니다")
    declared = document.get("backup")
    require(isinstance(declared, str) and Path(declared).resolve(strict=False) == expected_root.resolve(strict=False), "상태 백업 경로가 잘못됐습니다")
    for record in records:
        relative = str(record["path"])
        if record["root_before"] is not None:
            path = backup_file_for(game, run_id, "root", relative)
            require(file_identity(path) == record["root_before"], f"root 백업이 손상됐습니다: {relative}")
        if record["cloud_before"] is not None:
            path = backup_file_for(game, run_id, "cloud_saves", relative)
            require(file_identity(path) == record["cloud_before"], f"cloud 백업이 손상됐습니다: {relative}")


def copy_backup(source: Path, destination: Path, expected: dict[str, int | str] | None = None) -> dict[str, int | str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    actual = file_identity(destination)
    if expected is not None:
        require(actual == expected, f"백업 검증 실패: {source}")
    return actual


def rollback_install(game: Path, journal: dict[str, Any]) -> None:
    run_id = str(journal["run_id"])
    for record in reversed(journal.get("records", [])):
        root_target = checked_target(game, record["path"])
        root_backup = backup_file_for(game, run_id, "root", record["path"])
        current_root = optional_file_identity(root_target)
        if current_root == record["root_before"]:
            pass
        elif current_root == record["installed"]:
            if record["root_before"] is None:
                root_target.unlink()
            else:
                require(root_backup.is_file(), f"root 백업이 없습니다: {record['path']}")
                atomic_write(root_target, root_backup.read_bytes())
        else:
            raise PatchError(f"복구 중 사용자가 수정한 root 파일을 보존합니다: {record['path']}")
        require(optional_file_identity(root_target) == record["root_before"], f"root 복구 실패: {record['path']}")
        cloud_target = checked_target(game, f"cloud_saves/{record['path']}")
        current_cloud = optional_file_identity(cloud_target)
        if record["cloud_before"] is None:
            require(current_cloud is None, f"복구 중 새 cloud 파일을 보존합니다: {record['path']}")
        elif current_cloud is None:
            cloud_backup = backup_file_for(game, run_id, "cloud_saves", record["path"])
            require(cloud_backup.is_file(), f"cloud 백업이 없습니다: {record['path']}")
            atomic_write(cloud_target, cloud_backup.read_bytes())
        elif current_cloud != record["cloud_before"]:
            raise PatchError(f"복구 중 사용자가 수정한 cloud 파일을 보존합니다: {record['path']}")
        require(optional_file_identity(cloud_target) == record["cloud_before"], f"cloud 복구 실패: {record['path']}")


def validated_upgrade_source(
    package: Path,
    game: Path,
    current_manifest: dict[str, Any],
    receipt: dict[str, Any],
    *,
    verify_active_files: bool,
) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    previous_version = receipt.get("version")
    previous_sha256 = receipt.get("manifest_sha256")
    require(isinstance(previous_version, str), "이전 설치 기록의 버전이 잘못됐습니다")
    require(
        isinstance(previous_sha256, str) and re.fullmatch(r"[0-9A-F]{64}", previous_sha256) is not None,
        "이전 설치 기록의 manifest SHA-256이 잘못됐습니다",
    )
    previous_manifest, previous_sha256 = load_upgrade_manifest(
        package,
        current_manifest,
        previous_version,
        previous_sha256,
    )
    previous_records = validate_receipt(game, receipt, previous_manifest, previous_sha256)
    if verify_active_files:
        verify_installed_records(game, previous_records)
    return previous_manifest, previous_sha256, previous_records


def upgrade_original_sources(
    game: Path,
    manifest: dict[str, Any],
    previous_receipt: dict[str, Any],
    previous_records: list[dict[str, Any]],
) -> dict[str, Path]:
    by_path = {str(record["path"]): record for record in previous_records}
    current_paths = {str(row["path"]) for row in manifest["files"]}
    require(set(by_path) == current_paths, "직접 upgrade는 설치 파일 목록이 같은 버전끼리만 지원합니다")
    run_id = str(previous_receipt["run_id"])
    sources: dict[str, Path] = {}
    for row in manifest["files"]:
        relative = str(row["path"])
        record = by_path[relative]
        expected = expected_before(row)
        require(record["root_before"] == expected, f"upgrade 최초 원본이 현재 배포판과 다릅니다: {relative}")
        if expected is not None:
            source = backup_file_for(game, run_id, "root", relative)
            require(file_identity(source) == expected, f"upgrade 원본 백업이 손상됐습니다: {relative}")
            sources[relative] = source
    return sources


def rollback_upgrade(game: Path, journal: dict[str, Any]) -> None:
    run_id = str(journal["run_id"])
    for record in reversed(journal.get("records", [])):
        relative = str(record["path"])
        root_target = checked_target(game, relative)
        current_root = optional_file_identity(root_target)
        if current_root == record["upgrade_before"]:
            pass
        elif current_root == record["installed"]:
            upgrade_backup = backup_file_for(game, run_id, "upgrade_root", relative)
            require(file_identity(upgrade_backup) == record["upgrade_before"], f"upgrade 되돌림 백업이 손상됐습니다: {relative}")
            atomic_write(root_target, upgrade_backup.read_bytes())
        else:
            raise PatchError(f"upgrade 복구 중 사용자가 수정한 파일을 보존합니다: {relative}")
        require(optional_file_identity(root_target) == record["upgrade_before"], f"upgrade 되돌림 실패: {relative}")
        cloud_target = checked_target(game, f"cloud_saves/{relative}")
        require(not cloud_target.exists(), f"upgrade 복구 중 cloud 파일이 생겼습니다: {relative}")


def install_upgrade(
    game: Path,
    package: Path,
    manifest: dict[str, Any],
    manifest_sha256: str,
    previous_receipt: dict[str, Any],
    font_file: str | None = None,
    font_index: int = 0,
) -> dict[str, Any]:
    version = str(manifest["version"])
    state, receipt_path, journal_path = receipt_paths(game, version)
    previous_manifest, previous_sha256, previous_records = validated_upgrade_source(
        package,
        game,
        manifest,
        previous_receipt,
        verify_active_files=True,
    )
    source_paths = upgrade_original_sources(game, manifest, previous_receipt, previous_records)
    font_plan = prepare_font_plan(package, manifest, font_file, font_index)
    run_id = time.strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8]
    state.mkdir(parents=True, exist_ok=True)
    stage = checked_target(game, f"{STATE_DIR_NAME}/staging/{run_id}")
    backup = checked_target(game, f"{STATE_DIR_NAME}/backups/{run_id}")
    require(within(stage, state) and within(backup, state), "upgrade staging 또는 backup 경로가 잘못됐습니다")
    stage.mkdir(parents=True, exist_ok=False)
    try:
        staged_identities, font_metadata = stage_outputs(
            package,
            game,
            manifest,
            stage,
            font_plan,
            source_paths=source_paths,
        )
        validate_font_receipt(font_metadata, manifest)
        backup.mkdir(parents=True, exist_ok=False)
        previous_by_path = {str(record["path"]): record for record in previous_records}
        records: list[dict[str, Any]] = []
        previous_run_id = str(previous_receipt["run_id"])
        for row in manifest["files"]:
            relative = str(row["path"])
            previous_record = previous_by_path[relative]
            root_target = checked_target(game, relative)
            upgrade_before = file_identity(root_target)
            require(upgrade_before == previous_record["installed"], f"upgrade 직전 파일이 바뀌었습니다: {relative}")
            copy_backup(root_target, backup_file_for(game, run_id, "upgrade_root", relative), upgrade_before)

            root_before = previous_record["root_before"]
            if root_before is not None:
                original = backup_file_for(game, previous_run_id, "root", relative)
                copy_backup(original, backup_file_for(game, run_id, "root", relative), root_before)
            cloud_before = previous_record["cloud_before"]
            if cloud_before is not None:
                original_cloud = backup_file_for(game, previous_run_id, "cloud_saves", relative)
                copy_backup(original_cloud, backup_file_for(game, run_id, "cloud_saves", relative), cloud_before)
            records.append(
                {
                    "path": relative,
                    "root_before": root_before,
                    "root_backup": str(backup_file_for(game, run_id, "root", relative)),
                    "cloud_before": cloud_before,
                    "cloud_backup": str(backup_file_for(game, run_id, "cloud_saves", relative)),
                    "upgrade_before": upgrade_before,
                    "installed": staged_identities[relative],
                    "committed": False,
                }
            )
        journal = {
            "schema": "homm2-korean-operation-journal-v2",
            "operation": "upgrade",
            "status": "prepared",
            "version": version,
            "run_id": run_id,
            "manifest_sha256": manifest_sha256,
            "font_generation": font_metadata,
            "stage": str(stage),
            "backup": str(backup),
            "previous": {
                "version": previous_manifest["version"],
                "manifest_sha256": previous_sha256,
                "run_id": previous_receipt["run_id"],
            },
            "records": records,
        }
        atomic_write(journal_path, canonical(journal))
        order = sorted(
            range(len(records)),
            key=lambda index: (
                records[index]["path"].upper() == "HEROES2.EXE",
                records[index]["path"].upper() == "KOREAN.BIN",
                records[index]["path"].upper(),
            ),
        )
        try:
            for index in order:
                require_no_blockers()
                record = records[index]
                relative = record["path"]
                root_target = checked_target(game, relative)
                require(file_identity(root_target) == record["upgrade_before"], f"upgrade 중 설치 파일이 바뀌었습니다: {relative}")
                cloud_target = checked_target(game, f"cloud_saves/{relative}")
                require(not cloud_target.exists(), f"upgrade 중 cloud 파일이 생겼습니다: {relative}")
                staged = checked_target(stage, relative)
                require(file_identity(staged) == record["installed"], f"upgrade staging 결과가 바뀌었습니다: {relative}")
                os.replace(staged, root_target)
                require(file_identity(root_target) == record["installed"], f"upgrade 결과 검증 실패: {relative}")
                record["committed"] = True
                journal["status"] = "committing"
                atomic_write(journal_path, canonical(journal))
        except Exception:
            rollback_upgrade(game, journal)
            journal["status"] = "rolled_back"
            atomic_write(journal_path, canonical(journal))
            raise

        receipt_records = [{key: value for key, value in record.items() if key != "upgrade_before"} for record in records]
        receipt = {
            "schema": "homm2-korean-install-receipt-v1",
            "status": "installed",
            "version": version,
            "run_id": run_id,
            "manifest_sha256": manifest_sha256,
            "font_generation": font_metadata,
            "backup": str(backup),
            "upgraded_from": {
                "version": previous_manifest["version"],
                "manifest_sha256": previous_sha256,
                "run_id": previous_receipt["run_id"],
            },
            "records": receipt_records,
        }
        try:
            atomic_write(receipt_path, canonical(receipt))
        except Exception:
            rollback_upgrade(game, journal)
            journal["status"] = "rolled_back"
            atomic_write(journal_path, canonical(journal))
            raise
        journal_path.unlink()
        shutil.rmtree(stage, ignore_errors=True)
        print(f"upgrade 완료: {previous_manifest['version']} -> {version}")
        return verify(game, manifest, manifest_sha256, quiet=True)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def install(
    game: Path,
    package: Path,
    manifest: dict[str, Any],
    manifest_sha256: str,
    font_file: str | None = None,
    font_index: int = 0,
) -> dict[str, Any]:
    version = str(manifest["version"])
    state, receipt_path, journal_path = receipt_paths(game, version)
    require_no_blockers()
    validate_game_info(game, manifest)
    if journal_path.is_file():
        recover_pending(game, manifest, manifest_sha256, package)
    if receipt_path.is_file():
        receipt = read_json(receipt_path)
        if receipt.get("version") == version and receipt.get("manifest_sha256") == manifest_sha256:
            require(
                font_file is None and font_index == 0,
                "설치된 글꼴을 바꾸려면 먼저 UNINSTALL.cmd로 제거한 뒤 다시 설치해 주세요",
            )
            current = verify(game, manifest, manifest_sha256, quiet=True)
            print(f"이미 설치되어 있습니다: {version}")
            return current
        return install_upgrade(
            game,
            package,
            manifest,
            manifest_sha256,
            receipt,
            font_file,
            font_index,
        )
    originals = verify_originals(game, (row for row in manifest["files"] if row["method"] != "copy"))
    copy_rows = [row for row in manifest["files"] if row["method"] == "copy"]
    for row in copy_rows:
        target = checked_target(game, row["path"])
        require(not target.exists(), f"다른 패치 파일과 충돌합니다: {row['path']}")
    font_plan = prepare_font_plan(package, manifest, font_file, font_index)
    run_id = time.strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8]
    state.mkdir(parents=True, exist_ok=True)
    stage = checked_target(game, f"{STATE_DIR_NAME}/staging/{run_id}")
    backup = checked_target(game, f"{STATE_DIR_NAME}/backups/{run_id}")
    require(within(stage, state) and within(backup, state), "staging 또는 backup 경로가 상태 폴더 밖입니다")
    stage.mkdir(parents=True, exist_ok=False)
    require(within(stage, game) and within(stage, state), "생성된 staging 경로가 안전하지 않습니다")
    require(within(backup, game) and within(backup, state), "생성된 backup 경로가 안전하지 않습니다")
    try:
        staged_identities, font_metadata = stage_outputs(package, game, manifest, stage, font_plan)
        validate_font_receipt(font_metadata, manifest)
        backup.mkdir(parents=True, exist_ok=False)
        records: list[dict[str, Any]] = []
        for row in manifest["files"]:
            relative = str(row["path"])
            root_target = checked_target(game, relative)
            root_before = file_identity(root_target) if root_target.is_file() else None
            if row["method"] != "copy":
                require(root_before == originals[relative], f"백업 직전 원본이 바뀌었습니다: {relative}")
            else:
                require(root_before is None, f"복사 대상이 갑자기 생겼습니다: {relative}")
            root_backup = backup_file_for(game, run_id, "root", relative)
            if root_before is not None:
                copy_backup(root_target, root_backup, root_before)
            cloud_target = checked_target(game, f"cloud_saves/{relative}")
            cloud_before = file_identity(cloud_target) if cloud_target.is_file() else None
            cloud_backup = backup_file_for(game, run_id, "cloud_saves", relative)
            if cloud_before is not None:
                copy_backup(cloud_target, cloud_backup, cloud_before)
            records.append(
                {
                    "path": relative,
                    "root_before": root_before,
                    "root_backup": str(root_backup),
                    "cloud_before": cloud_before,
                    "cloud_backup": str(cloud_backup),
                    "installed": staged_identities[relative],
                    "committed": False,
                }
            )
        journal = {
            "schema": "homm2-korean-operation-journal-v2",
            "operation": "install",
            "status": "prepared",
            "version": version,
            "run_id": run_id,
            "manifest_sha256": manifest_sha256,
            "font_generation": font_metadata,
            "stage": str(stage),
            "backup": str(backup),
            "records": records,
        }
        atomic_write(journal_path, canonical(journal))
        order = sorted(
            range(len(records)),
            key=lambda index: (
                records[index]["path"].upper() == "HEROES2.EXE",
                records[index]["path"].upper() == "KOREAN.BIN",
                records[index]["path"].upper(),
            ),
        )
        try:
            for index in order:
                require_no_blockers()
                record = records[index]
                relative = record["path"]
                root_target = checked_target(game, relative)
                if record["root_before"] is None:
                    require(not root_target.exists(), f"설치 중 대상이 생겼습니다: {relative}")
                else:
                    require(file_identity(root_target) == record["root_before"], f"설치 중 원본이 바뀌었습니다: {relative}")
                cloud_target = checked_target(game, f"cloud_saves/{relative}")
                if record["cloud_before"] is None:
                    require(not cloud_target.exists(), f"설치 중 cloud 대상이 생겼습니다: {relative}")
                else:
                    require(file_identity(cloud_target) == record["cloud_before"], f"설치 중 cloud 대상이 바뀌었습니다: {relative}")
                    cloud_target.unlink()
                staged = checked_target(stage, relative)
                require(file_identity(staged) == record["installed"], f"staging 결과가 바뀌었습니다: {relative}")
                root_target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staged, root_target)
                require(file_identity(root_target) == record["installed"], f"설치 결과 검증 실패: {relative}")
                record["committed"] = True
                journal["status"] = "committing"
                atomic_write(journal_path, canonical(journal))
        except Exception:
            rollback_install(game, journal)
            journal["status"] = "rolled_back"
            atomic_write(journal_path, canonical(journal))
            raise
        receipt = {
            "schema": "homm2-korean-install-receipt-v1",
            "status": "installed",
            "version": version,
            "run_id": run_id,
            "manifest_sha256": manifest_sha256,
            "font_generation": font_metadata,
            "backup": str(backup),
            "records": records,
        }
        atomic_write(receipt_path, canonical(receipt))
        journal_path.unlink()
        shutil.rmtree(stage, ignore_errors=True)
        print(f"설치 완료: {version}")
        return verify(game, manifest, manifest_sha256, quiet=True)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def validate_receipt(
    game: Path, receipt: dict[str, Any], manifest: dict[str, Any], manifest_sha256: str
) -> list[dict[str, Any]]:
    require(receipt.get("status") == "installed", "receipt 설치 상태가 잘못됐습니다")
    records = validate_state_document(
        receipt,
        manifest,
        manifest_sha256,
        schema="homm2-korean-install-receipt-v1",
        require_committed=True,
    )
    validate_backup_files(game, receipt, records)
    return records


def optional_file_identity(path: Path) -> dict[str, int | str] | None:
    if not path.exists():
        return None
    require(path.is_file(), f"대상 경로가 파일이 아닙니다: {path}")
    return file_identity(path)


def verify_installed_records(game: Path, records: Iterable[dict[str, Any]]) -> None:
    for record in records:
        relative = str(record["path"])
        require(optional_file_identity(checked_target(game, relative)) == record["installed"], f"설치 파일이 바뀌었습니다: {relative}")
        cloud_target = checked_target(game, f"cloud_saves/{relative}")
        require(not cloud_target.exists(), f"cloud_saves 파일이 패치를 가리고 있습니다: {relative}")


def verify(game: Path, manifest: dict[str, Any], manifest_sha256: str, quiet: bool = False) -> dict[str, Any]:
    _, receipt_path, journal_path = receipt_paths(game, str(manifest["version"]))
    require(not journal_path.exists(), "미완료 설치 journal이 있습니다")
    receipt = read_json(receipt_path)
    records = validate_receipt(game, receipt, manifest, manifest_sha256)
    verify_installed_records(game, records)
    font_metadata = receipt["font_generation"]
    result = {
        "status": "installed_files_verified",
        "version": manifest["version"],
        "file_count": len(records),
        "game_dir": str(game),
        "font_mode": font_metadata["mode"],
        "font_family": font_metadata["primary"]["family"] or font_metadata["primary"]["file_name"],
        "font_fallback_glyphs": font_metadata["fallback_glyph_count"],
    }
    if not quiet:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def resume_uninstall(
    game: Path,
    manifest: dict[str, Any],
    manifest_sha256: str,
    journal: dict[str, Any],
    receipt: dict[str, Any] | None,
) -> dict[str, Any]:
    require(journal.get("operation") == "uninstall", "제거 journal 작업 종류가 잘못됐습니다")
    require(journal.get("status") in {"prepared", "uninstalling"}, "제거 journal 상태가 잘못됐습니다")
    records = validate_state_document(
        journal,
        manifest,
        manifest_sha256,
        schema="homm2-korean-operation-journal-v2",
        require_committed=True,
    )
    validate_backup_files(game, journal, records)
    require(all(isinstance(record.get("restored"), bool) for record in records), "제거 journal의 restored 상태가 잘못됐습니다")
    if receipt is not None:
        receipt_records = validate_receipt(game, receipt, manifest, manifest_sha256)
        require(receipt["run_id"] == journal["run_id"], "receipt와 제거 journal의 run_id가 다릅니다")
        require(receipt.get("backup") == journal.get("backup"), "receipt와 제거 journal의 백업 경로가 다릅니다")
        require(
            receipt.get("font_generation") == journal.get("font_generation"),
            "receipt와 제거 journal의 글꼴 정보가 다릅니다",
        )
        journal_records = [{key: value for key, value in record.items() if key != "restored"} for record in records]
        require(journal_records == receipt_records, "receipt와 제거 journal의 records가 다릅니다")
    _, receipt_path, journal_path = receipt_paths(game, str(manifest["version"]))
    run_id = str(journal["run_id"])
    for index in range(len(records) - 1, -1, -1):
        require_no_blockers()
        record = records[index]
        relative = str(record["path"])
        root_target = checked_target(game, relative)
        current_root = optional_file_identity(root_target)
        if current_root == record["root_before"]:
            pass
        elif current_root == record["installed"]:
            if record["root_before"] is None:
                root_target.unlink()
            else:
                root_backup = backup_file_for(game, run_id, "root", relative)
                atomic_write(root_target, root_backup.read_bytes())
        else:
            raise PatchError(f"사용자가 수정한 파일은 제거하지 않습니다: {relative}")
        require(optional_file_identity(root_target) == record["root_before"], f"root 복원 실패: {relative}")

        cloud_target = checked_target(game, f"cloud_saves/{relative}")
        current_cloud = optional_file_identity(cloud_target)
        if record["cloud_before"] is None:
            require(current_cloud is None, f"설치 후 생성된 cloud 파일과 충돌합니다: {relative}")
        elif current_cloud is None:
            cloud_backup = backup_file_for(game, run_id, "cloud_saves", relative)
            atomic_write(cloud_target, cloud_backup.read_bytes())
        elif current_cloud != record["cloud_before"]:
            raise PatchError(f"cloud 복원 대상이 다른 파일입니다: {relative}")
        require(optional_file_identity(cloud_target) == record["cloud_before"], f"cloud 복원 실패: {relative}")
        record["restored"] = True
        journal["status"] = "uninstalling"
        atomic_write(journal_path, canonical(journal))

    history_receipt = dict(receipt or journal)
    history_receipt["schema"] = "homm2-korean-install-receipt-v1"
    history_receipt.pop("operation", None)
    history_receipt["status"] = "uninstalled"
    history_receipt["uninstalled_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    history_receipt["records"] = [{key: value for key, value in record.items() if key != "restored"} for record in records]
    history = receipt_path.parent / f"receipt.uninstalled.{run_id}.json"
    atomic_write(history, canonical(history_receipt))
    if receipt_path.exists():
        receipt_path.unlink()
    journal_path.unlink()
    result = {"status": "uninstalled_and_restored", "version": manifest["version"], "file_count": len(records), "game_dir": str(game), "history": str(history)}
    print(f"제거 완료: {manifest['version']}")
    return result


def recover_upgrade(
    game: Path,
    package: Path,
    manifest: dict[str, Any],
    manifest_sha256: str,
    journal: dict[str, Any],
) -> dict[str, Any]:
    require(journal.get("operation") == "upgrade", "upgrade journal 작업 종류가 잘못됐습니다")
    require(journal.get("status") in {"prepared", "committing", "rolled_back"}, "upgrade journal 상태가 잘못됐습니다")
    records = validate_state_document(
        journal,
        manifest,
        manifest_sha256,
        schema="homm2-korean-operation-journal-v2",
        require_committed=False,
    )
    validate_backup_files(game, journal, records)
    run_id = str(journal["run_id"])
    for record in records:
        validate_identity(record.get("upgrade_before"), f"upgrade previous target {record['path']}")
        upgrade_backup = backup_file_for(game, run_id, "upgrade_root", str(record["path"]))
        require(file_identity(upgrade_backup) == record["upgrade_before"], f"upgrade 되돌림 백업이 손상됐습니다: {record['path']}")

    _, receipt_path, journal_path = receipt_paths(game, str(manifest["version"]))
    receipt = read_json(receipt_path)
    if receipt.get("version") == manifest["version"] and receipt.get("manifest_sha256") == manifest_sha256:
        receipt_records = validate_receipt(game, receipt, manifest, manifest_sha256)
        expected_records = [{key: value for key, value in record.items() if key != "upgrade_before"} for record in records]
        require(receipt_records == expected_records, "완료된 upgrade receipt와 journal이 다릅니다")
        require(receipt.get("font_generation") == journal.get("font_generation"), "upgrade 글꼴 기록이 다릅니다")
        verify_installed_records(game, receipt_records)
        journal_path.unlink()
        result = {"status": "completed_upgrade_finalized", "version": manifest["version"], "game_dir": str(game)}
        print("완료된 upgrade의 journal을 정리했습니다.")
        return result

    previous_manifest, previous_sha256, previous_records = validated_upgrade_source(
        package,
        game,
        manifest,
        receipt,
        verify_active_files=False,
    )
    previous = journal.get("previous")
    require(
        previous
        == {
            "version": previous_manifest["version"],
            "manifest_sha256": previous_sha256,
            "run_id": receipt["run_id"],
        },
        "upgrade journal의 이전 설치 기록이 다릅니다",
    )
    previous_by_path = {str(record["path"]): record for record in previous_records}
    for record in records:
        require(
            previous_by_path.get(str(record["path"]), {}).get("installed") == record["upgrade_before"],
            f"upgrade 되돌림 대상이 이전 receipt와 다릅니다: {record['path']}",
        )
    rollback_upgrade(game, journal)
    verify_installed_records(game, previous_records)
    journal["status"] = "recovered_to_previous_version"
    history = journal_path.parent / f"journal.upgrade-recovered.{journal['run_id']}.json"
    atomic_write(history, canonical(journal))
    journal_path.unlink()
    result = {
        "status": "incomplete_upgrade_rolled_back",
        "version": previous_manifest["version"],
        "game_dir": str(game),
        "history": str(history),
    }
    print(f"미완료 upgrade를 {previous_manifest['version']} 상태로 복구했습니다.")
    return result


def recover_pending(
    game: Path,
    manifest: dict[str, Any],
    manifest_sha256: str,
    package: Path | None = None,
) -> dict[str, Any]:
    state, receipt_path, journal_path = receipt_paths(game, str(manifest["version"]))
    require(journal_path.is_file(), "복구할 journal이 없습니다")
    require_no_blockers()
    journal = read_json(journal_path)
    operation = journal.get("operation")
    if operation == "upgrade":
        require(package is not None, "upgrade 복구에 배포 패키지 경로가 필요합니다")
        return recover_upgrade(game, package, manifest, manifest_sha256, journal)
    if operation == "uninstall":
        receipt = read_json(receipt_path) if receipt_path.is_file() else None
        return resume_uninstall(game, manifest, manifest_sha256, journal, receipt)
    require(operation == "install", "알 수 없는 journal 작업입니다")
    require(journal.get("status") in {"prepared", "committing", "rolled_back"}, "설치 journal 상태가 잘못됐습니다")
    records = validate_state_document(
        journal,
        manifest,
        manifest_sha256,
        schema="homm2-korean-operation-journal-v2",
        require_committed=False,
    )
    validate_backup_files(game, journal, records)
    if receipt_path.is_file():
        receipt = read_json(receipt_path)
        receipt_records = validate_receipt(game, receipt, manifest, manifest_sha256)
        require(receipt["run_id"] == journal["run_id"], "receipt와 설치 journal의 run_id가 다릅니다")
        require(receipt.get("backup") == journal.get("backup"), "receipt와 설치 journal의 백업 경로가 다릅니다")
        require(
            receipt.get("font_generation") == journal.get("font_generation"),
            "receipt와 설치 journal의 글꼴 정보가 다릅니다",
        )
        require(receipt_records == records, "receipt와 설치 journal의 records가 다릅니다")
        verify_installed_records(game, receipt_records)
        journal_path.unlink()
        result = {"status": "completed_install_finalized", "version": manifest["version"], "game_dir": str(game)}
        print("완료된 설치의 journal을 정리했습니다.")
        return result
    rollback_install(game, journal)
    journal["status"] = "recovered_to_original"
    history = state / f"journal.recovered.{journal['run_id']}.json"
    atomic_write(history, canonical(journal))
    journal_path.unlink()
    result = {"status": "incomplete_install_rolled_back", "version": manifest["version"], "game_dir": str(game), "history": str(history)}
    print("미완료 설치를 원본 상태로 복구했습니다.")
    return result


def uninstall(
    game: Path,
    manifest: dict[str, Any],
    manifest_sha256: str,
    package: Path | None = None,
) -> dict[str, Any]:
    version = str(manifest["version"])
    _, receipt_path, journal_path = receipt_paths(game, version)
    require_no_blockers()
    validate_game_info(game, manifest)
    if journal_path.is_file():
        return recover_pending(game, manifest, manifest_sha256, package)
    if not receipt_path.exists():
        result = {"status": "not_installed", "version": version, "game_dir": str(game)}
        print("설치 기록이 없습니다. 변경하지 않았습니다.")
        return result
    receipt = read_json(receipt_path)
    if receipt.get("version") != version or receipt.get("manifest_sha256") != manifest_sha256:
        require(package is not None, "이전 버전 제거에 배포 패키지 경로가 필요합니다")
        previous_manifest, previous_sha256, _ = validated_upgrade_source(
            package,
            game,
            manifest,
            receipt,
            verify_active_files=True,
        )
        manifest = previous_manifest
        manifest_sha256 = previous_sha256
        version = str(previous_manifest["version"])
    records = validate_receipt(game, receipt, manifest, manifest_sha256)
    verify_installed_records(game, records)
    journal = {
        "schema": "homm2-korean-operation-journal-v2",
        "operation": "uninstall",
        "status": "prepared",
        "version": version,
        "run_id": receipt["run_id"],
        "manifest_sha256": manifest_sha256,
        "font_generation": receipt["font_generation"],
        "backup": receipt["backup"],
        "records": [dict(record, restored=False) for record in records],
    }
    atomic_write(journal_path, canonical(journal))
    return resume_uninstall(game, manifest, manifest_sha256, journal, receipt)


def preflight(
    game: Path,
    package: Path,
    manifest: dict[str, Any],
    manifest_sha256: str | None = None,
    font_file: str | None = None,
    font_index: int = 0,
) -> dict[str, Any]:
    require_no_blockers()
    validate_game_info(game, manifest)
    _, receipt_path, journal_path = receipt_paths(game, str(manifest["version"]))
    if journal_path.exists():
        journal = read_json(journal_path)
        require(journal.get("operation") in {"install", "upgrade"}, "설치 전 제거 복구를 먼저 완료해 주세요")
        result = {
            "status": "preflight_pending_recovery",
            "version": manifest["version"],
            "game_dir": str(game),
            "pending_operation": journal["operation"],
        }
        print("미완료 작업을 안전하게 복구한 뒤 설치를 계속합니다.")
        return result
    for row in manifest["files"]:
        verify_package_file(package, row)
    upgrade_from: str | None = None
    if receipt_path.is_file():
        require(manifest_sha256 is not None, "설치 기록을 확인할 manifest SHA-256이 필요합니다")
        receipt = read_json(receipt_path)
        if receipt.get("version") == manifest["version"] and receipt.get("manifest_sha256") == manifest_sha256:
            require(
                font_file is None and font_index == 0,
                "설치된 글꼴을 바꾸려면 먼저 UNINSTALL.cmd로 제거한 뒤 다시 설치해 주세요",
            )
            current = verify(game, manifest, manifest_sha256, quiet=True)
            current["status"] = "preflight_already_installed"
            print(json.dumps(current, ensure_ascii=False, indent=2))
            return current
        previous_manifest, _, previous_records = validated_upgrade_source(
            package,
            game,
            manifest,
            receipt,
            verify_active_files=True,
        )
        originals = upgrade_original_sources(game, manifest, receipt, previous_records)
        upgrade_from = str(previous_manifest["version"])
    else:
        originals = verify_originals(game, (row for row in manifest["files"] if row["method"] != "copy"))
    font_plan = prepare_font_plan(package, manifest, font_file, font_index)
    font_metadata = font_plan.metadata()
    result = {
        "status": "preflight_upgrade_passed" if upgrade_from else "preflight_passed",
        "version": manifest["version"],
        "game_dir": str(game),
        "original_file_count": len(originals),
        "package_file_count": len(manifest["files"]) + 2 + len(validate_upgrades(manifest.get("upgrades"), str(manifest["version"]))),
        "font_mode": font_metadata["mode"],
        "font_family": font_metadata["primary"]["family"] or font_metadata["primary"]["file_name"],
        "font_primary_glyphs": font_metadata["primary_glyph_count"],
        "font_fallback_glyphs": font_metadata["fallback_glyph_count"],
    }
    if upgrade_from:
        result["upgrade_from"] = upgrade_from
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preflight", "install", "verify", "uninstall", "recover"))
    parser.add_argument("--game-dir")
    font_source = parser.add_mutually_exclusive_group()
    font_source.add_argument("--font-file", help="사용할 로컬 TTF/OTF/TTC/OTC 글꼴 파일")
    font_source.add_argument("--choose-font", action="store_true", help="Windows 글꼴 파일 선택 창 열기")
    parser.add_argument("--font-index", type=int, default=0, help="TTC/OTC face 번호(기본 0)")
    args = parser.parse_args()
    try:
        require(args.font_index >= 0, "글꼴 face 번호는 0 이상이어야 합니다")
        has_font_source = args.font_file is not None or args.choose_font
        require(
            args.action in {"preflight", "install"} or (not has_font_source and args.font_index == 0),
            "글꼴 옵션은 preflight/install에서만 사용합니다",
        )
        require(
            args.font_index == 0 or has_font_source,
            "--font-index를 사용하려면 --font-file 또는 --choose-font를 함께 지정해 주세요",
        )
        font_file = choose_font_file() if args.choose_font else args.font_file
        package, manifest, manifest_sha256 = load_manifest()
        game = detect_game_dir(args.game_dir)
        with operation_lock(game):
            if args.action == "preflight":
                preflight(
                    game,
                    package,
                    manifest,
                    manifest_sha256,
                    font_file,
                    args.font_index,
                )
            elif args.action == "install":
                install(
                    game,
                    package,
                    manifest,
                    manifest_sha256,
                    font_file,
                    args.font_index,
                )
            elif args.action == "verify":
                verify(game, manifest, manifest_sha256)
            elif args.action == "uninstall":
                uninstall(game, manifest, manifest_sha256, package)
            else:
                recover_pending(game, manifest, manifest_sha256, package)
        return 0
    except (PatchError, homm2_font.FontBuildError, OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
