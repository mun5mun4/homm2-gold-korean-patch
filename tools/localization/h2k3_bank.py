#!/usr/bin/env python3
"""H2K3 v3 bank format and atomic dynamic-slot runtime model."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


MAGIC = b"H2K3"
VERSION = 3
# The runtime consumes render_count with MOVZX from byte 0x0C and separately
# requires byte 0x0D to be zero.  Keep those fields explicit in the authoring
# format instead of relying on the high byte of a uint16 count.
HEADER = struct.Struct("<4sHHIBBHIIII")
HEADER_SIZE = HEADER.size
RENDER_ROW = struct.Struct("<12sI")
MARKER = 0x40
DOS_READ_LIMIT = 0xFF00
MAX_BANK_LENGTH = DOS_READ_LIMIT - 1
ALLOCATION_SIZE = 0x11000
SLOT_OFFSET = 0xFF00
SLOT_BYTES = 0x400
SLOT_TOKEN_LIMIT = SLOT_BYTES
SLOT_TOKEN_MASK = 0xFFFFFC03
FNV1A_BASIS = 0x811C9DC5
FNV1A_PRIME = 0x01000193


class BankError(ValueError):
    pass


@dataclass(frozen=True)
class RenderRow:
    prefix: bytes
    token: int
    file_offset: int


@dataclass(frozen=True)
class Descriptor:
    target: int
    expected: int
    marker_offset: int
    data_offset: int
    encoded: bytes
    header_offset: int


@dataclass(frozen=True)
class ParsedBank:
    raw: bytes
    total_length: int
    mapping_tag: int
    body_checksum: int
    render_rows: tuple[RenderRow, ...]
    descriptors: tuple[Descriptor, ...]
    records_offset: int


@dataclass(frozen=True)
class DescriptorScan:
    marker_offset: int
    terminator_offset: int
    next_record_offset: int
    visited_offsets: tuple[int, ...]


@dataclass(frozen=True)
class SimulatedLoad:
    state: int
    published_render_count: int
    memory: dict[int, int]
    private_bank: bytes | None
    bank_base: int
    table_pointer: int
    slot_base: int
    bytes_read: int
    malloc_calls: int
    malloc_successes: int
    free_calls: int
    live_allocation: bool
    allocation_interval: tuple[int, int] | None
    freed_pointer: int
    released_interval: tuple[int, int] | None
    failure_reason: str | None
    events: tuple[str, ...]
    state_trace: tuple[int, ...]

    @property
    def control(self) -> dict[str, int]:
        return {
            "bank_pointer": self.bank_base,
            "table_pointer": self.table_pointer,
            "slot_pointer": self.slot_base,
            "state": self.state,
            "active_render_count": self.published_render_count,
        }


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BankError(message)


def fnv1a32(data: bytes) -> int:
    value = FNV1A_BASIS
    for byte in data:
        value ^= byte
        value = (value * FNV1A_PRIME) & 0xFFFFFFFF
    return value


def token_allowed(value: int) -> bool:
    return 0 <= value < SLOT_TOKEN_LIMIT and (value & 3) == 0


def unit_target_allowed(value: int, unit_start: int, unit_end: int) -> bool:
    return unit_start <= value < unit_end and (value & 3) == 0


def target_allowed(value: int, unit_start: int, unit_end: int) -> bool:
    return token_allowed(value) or unit_target_allowed(value, unit_start, unit_end)


def effective_target(value: int, *, slot_base: int) -> int:
    return slot_base + value if token_allowed(value) else value


def scan_descriptor_payload_machine(raw: bytes, marker_offset: int, total_length: int) -> DescriptorScan:
    """Model the fixed helper's byte-level INC/bounds/CMP/JNE scan loop.

    ESI enters on the 0x40 marker.  The loop's back-edge targets INC ESI, so
    the first iteration reaches the first payload byte and every non-NUL
    iteration advances exactly once before the next bounds check.
    """
    require(0 <= marker_offset < total_length <= len(raw), "descriptor scan range is invalid")
    require(raw[marker_offset] == MARKER, "descriptor marker mismatch")
    cursor = marker_offset
    visited: list[int] = []
    while True:
        cursor += 1
        require(cursor < total_length, "descriptor has no terminator")
        visited.append(cursor)
        if raw[cursor] == 0:
            return DescriptorScan(marker_offset, cursor, cursor + 1, tuple(visited))


def valid_allocation_base(value: int) -> bool:
    """Model the non-NULL, dword-aligned, non-wrapping wrapper result contract."""
    return (
        isinstance(value, int)
        and 0 < value <= 0xFFFFFFFF
        and (value & 3) == 0
        and value + ALLOCATION_SIZE <= 0x100000000
    )


def serialize_bank(
    render_rows: Sequence[tuple[bytes, int]],
    descriptors: Iterable[tuple[int, int, bytes]],
    *,
    mapping_tag: int,
    unit_start: int,
    unit_end: int,
) -> tuple[bytes, tuple[RenderRow, ...], tuple[Descriptor, ...]]:
    rows = tuple(render_rows)
    records = tuple(descriptors)
    require(0 <= len(rows) <= 0xFF, "render count must be 0..255")
    require(1 <= len(records) <= 0xFFFF, "descriptor count must be 1..65535")
    require(0 <= mapping_tag <= 0xFFFFFFFF, "mapping tag is outside uint32")

    render_blob = bytearray()
    parsed_rows: list[RenderRow] = []
    prefixes: set[bytes] = set()
    tokens: set[int] = set()
    for index, (prefix, token) in enumerate(rows):
        require(len(prefix) == 12, f"render row {index} prefix is not 12 bytes")
        require(b"\0" not in prefix, f"render row {index} prefix contains NUL")
        require(prefix not in prefixes, f"render row {index} prefix is duplicated")
        require(token_allowed(token), f"render row {index} token is not allowed")
        require(token not in tokens, f"render row {index} token is duplicated")
        prefixes.add(prefix)
        tokens.add(token)
        file_offset = HEADER_SIZE + len(render_blob)
        render_blob.extend(RENDER_ROW.pack(prefix, token))
        parsed_rows.append(RenderRow(bytes(prefix), token, file_offset))

    descriptor_blob = bytearray()
    parsed_descriptors: list[Descriptor] = []
    targets: set[int] = set()
    for index, (target, expected, encoded) in enumerate(records):
        require(
            target_allowed(target, unit_start, unit_end),
            f"descriptor {index} target is not allowed",
        )
        require(target not in targets, f"descriptor {index} target is duplicated")
        require(0 <= expected <= 0xFFFFFFFF, f"descriptor {index} expected is outside uint32")
        if token_allowed(target):
            require(expected == 0, f"descriptor {index} token expected must be zero")
        require(b"\0" not in encoded, f"descriptor {index} payload contains NUL")
        targets.add(target)
        header_offset = HEADER_SIZE + len(render_blob) + len(descriptor_blob)
        descriptor_blob.extend(struct.pack("<II", target, expected))
        marker_offset = HEADER_SIZE + len(render_blob) + len(descriptor_blob)
        descriptor_blob.append(MARKER)
        data_offset = HEADER_SIZE + len(render_blob) + len(descriptor_blob)
        descriptor_blob.extend(encoded)
        descriptor_blob.append(0)
        parsed_descriptors.append(
            Descriptor(target, expected, marker_offset, data_offset, bytes(encoded), header_offset)
        )

    descriptor_tokens = {row.target for row in parsed_descriptors if token_allowed(row.target)}
    require(descriptor_tokens == tokens, "render tokens and descriptor token targets differ")

    records_offset = HEADER_SIZE + len(render_blob)
    body = bytes(render_blob + descriptor_blob)
    total_length = HEADER_SIZE + len(body)
    require(total_length <= MAX_BANK_LENGTH, "bank exceeds H2K3 v3 limit")
    checksum = fnv1a32(body)
    header = HEADER.pack(
        MAGIC,
        VERSION,
        len(parsed_descriptors),
        total_length,
        len(parsed_rows),
        0,
        HEADER_SIZE,
        HEADER_SIZE,
        records_offset,
        mapping_tag,
        checksum,
    )
    return header + body, tuple(parsed_rows), tuple(parsed_descriptors)


def parse_bank(
    raw: bytes,
    *,
    expected_mapping_tag: int,
    unit_start: int,
    unit_end: int,
    reject_duplicates: bool = True,
    strict_authoring: bool = True,
) -> ParsedBank:
    require(HEADER_SIZE <= len(raw) <= MAX_BANK_LENGTH, "bank length is invalid")
    (
        magic,
        version,
        descriptor_count,
        total_length,
        render_count,
        reserved,
        header_size,
        table_offset,
        records_offset,
        mapping_tag,
        checksum,
    ) = HEADER.unpack_from(raw)
    require(magic == MAGIC, "magic mismatch")
    require(version == VERSION, "version mismatch")
    require(descriptor_count != 0, "descriptor count is zero")
    require(reserved == 0, "reserved header byte is nonzero")
    require(total_length == len(raw), "total length differs from actual bytes")
    require(header_size == HEADER_SIZE, "header size mismatch")
    require(table_offset == HEADER_SIZE, "render table offset mismatch")
    require(records_offset == HEADER_SIZE + render_count * RENDER_ROW.size, "records offset mismatch")
    require(records_offset <= total_length, "records offset exceeds total length")
    require(mapping_tag == expected_mapping_tag, "mapping tag mismatch")
    require(fnv1a32(raw[header_size:]) == checksum, "body checksum mismatch")

    rows: list[RenderRow] = []
    prefixes: set[bytes] = set()
    tokens: set[int] = set()
    cursor = table_offset
    for index in range(render_count):
        prefix, token = RENDER_ROW.unpack_from(raw, cursor)
        if strict_authoring:
            require(b"\0" not in prefix, f"render row {index} prefix contains NUL")
            require(token_allowed(token), f"render row {index} token is not allowed")
        if strict_authoring and reject_duplicates:
            require(prefix not in prefixes, f"render row {index} prefix is duplicated")
            require(token not in tokens, f"render row {index} token is duplicated")
        prefixes.add(prefix)
        tokens.add(token)
        rows.append(RenderRow(prefix, token, cursor))
        cursor += RENDER_ROW.size
    require(cursor == records_offset, "render table did not end at records offset")

    descriptors: list[Descriptor] = []
    targets: set[int] = set()
    for index in range(descriptor_count):
        require(cursor + 9 <= total_length, f"descriptor {index} header is truncated")
        header_offset = cursor
        target, expected = struct.unpack_from("<II", raw, cursor)
        require(
            target_allowed(target, unit_start, unit_end),
            f"descriptor {index} target is not allowed",
        )
        if reject_duplicates:
            require(target not in targets, f"descriptor {index} target is duplicated")
        if strict_authoring and token_allowed(target):
            require(expected == 0, f"descriptor {index} token expected must be zero")
        targets.add(target)
        marker_offset = cursor + 8
        require(raw[marker_offset] == MARKER, f"descriptor {index} marker mismatch")
        data_offset = marker_offset + 1
        try:
            scan = scan_descriptor_payload_machine(raw, marker_offset, total_length)
        except BankError as exc:
            raise BankError(f"descriptor {index} has no terminator") from exc
        descriptors.append(
            Descriptor(
                target,
                expected,
                marker_offset,
                data_offset,
                raw[data_offset : scan.terminator_offset],
                header_offset,
            )
        )
        cursor = scan.next_record_offset
    require(cursor == total_length, "trailing bytes remain after descriptors")

    if strict_authoring:
        descriptor_tokens = {row.target for row in descriptors if token_allowed(row.target)}
        require(descriptor_tokens == tokens, "render tokens and descriptor token targets differ")
    return ParsedBank(
        bytes(raw), total_length, mapping_tag, checksum, tuple(rows), tuple(descriptors), records_offset
    )


def simulate_atomic_load(
    raw: bytes | None,
    memory: Mapping[int, int],
    *,
    bank_base: int,
    expected_mapping_tag: int,
    unit_start: int,
    unit_end: int,
    allocation_succeeds: bool = True,
    read_succeeds: bool = True,
    protected_intervals: Sequence[tuple[int, int]] = (),
) -> SimulatedLoad:
    """Model one DOS read, allocation lifetime, validation, patch, and publication."""
    before = dict(memory)
    events = ["entry_state_00", "state_01", "open_attempt"]
    state_trace = [0x00, 0x01]

    def result(
        state: int,
        *,
        published: int = 0,
        final_memory: Mapping[int, int] = before,
        private_bank: bytes | None = None,
        control_bank: int = 0,
        control_table: int = 0,
        control_slot: int = 0,
        bytes_read: int = 0,
        malloc_calls: int = 0,
        malloc_successes: int = 0,
        free_calls: int = 0,
        live: bool = False,
        interval: tuple[int, int] | None = None,
        freed_pointer: int = 0,
        released_interval: tuple[int, int] | None = None,
        failure_reason: str | None = None,
    ) -> SimulatedLoad:
        return SimulatedLoad(
            state=state,
            published_render_count=published,
            memory=dict(final_memory),
            private_bank=private_bank,
            bank_base=control_bank,
            table_pointer=control_table,
            slot_base=control_slot,
            bytes_read=bytes_read,
            malloc_calls=malloc_calls,
            malloc_successes=malloc_successes,
            free_calls=free_calls,
            live_allocation=live,
            allocation_interval=interval,
            freed_pointer=freed_pointer,
            released_interval=released_interval,
            failure_reason=failure_reason,
            events=tuple(events),
            state_trace=tuple(state_trace),
        )

    if raw is None:
        events.extend(("open_missing", "state_81"))
        state_trace.append(0x81)
        return result(0x81, failure_reason="open_missing")

    events.extend(("open_ok", "malloc_attempt"))
    if not allocation_succeeds or bank_base == 0:
        events.extend(("malloc_null", "close", "state_85"))
        state_trace.append(0x85)
        return result(
            0x85,
            malloc_calls=1,
            failure_reason="allocation_null",
        )

    events.append("malloc_success")
    # The injected machine code only tests the wrapper result for NULL.  The
    # wrapper's alignment/address-space guarantees are acceptance preconditions,
    # not runtime branches that may be invented by this model.
    require(valid_allocation_base(bank_base), "allocator returned an invalid base")

    allocation_interval = (bank_base, bank_base + ALLOCATION_SIZE)
    for protected_start, protected_end in protected_intervals:
        require(
            0 <= protected_start < protected_end <= 0x100000000,
            "protected interval is invalid",
        )
        require(
            max(bank_base, protected_start) >= min(allocation_interval[1], protected_end),
            "allocator result overlaps a protected interval",
        )

    slot_base = bank_base + SLOT_OFFSET
    require(
        bank_base < bank_base + HEADER_SIZE <= slot_base < slot_base + SLOT_BYTES <= allocation_interval[1],
        "internal allocation intervals overlap or escape the allocation",
    )
    events.append("slots_zero")
    if not read_succeeds:
        events.extend(("read_error", "close", "free_call", "control_clear", "state_83"))
        state_trace.append(0x83)
        return result(
            0x83,
            malloc_calls=1,
            malloc_successes=1,
            free_calls=1,
            interval=allocation_interval,
            freed_pointer=bank_base,
            released_interval=allocation_interval,
            failure_reason="read_error",
        )

    dos_buffer = bytes(raw[:DOS_READ_LIMIT])
    bytes_read = len(dos_buffer)
    events.extend(("read_complete", "close"))
    try:
        parsed = parse_bank(
            dos_buffer,
            expected_mapping_tag=expected_mapping_tag,
            unit_start=unit_start,
            unit_end=unit_end,
            reject_duplicates=False,
            strict_authoring=False,
        )
    except BankError as exc:
        if bytes_read == DOS_READ_LIMIT:
            failure_reason = "oversize_read"
        elif str(exc) == "body checksum mismatch":
            failure_reason = "checksum_mismatch"
        else:
            failure_reason = f"malformed_bank:{exc}"
        events.extend(("validation_failed", "free_call", "control_clear", "state_84"))
        state_trace.append(0x84)
        return result(
            0x84,
            bytes_read=bytes_read,
            malloc_calls=1,
            malloc_successes=1,
            free_calls=1,
            interval=allocation_interval,
            freed_pointer=bank_base,
            released_interval=allocation_interval,
            failure_reason=failure_reason,
        )

    events.append("bank_structure_valid")
    validation_memory = dict(before)
    for offset in range(0, SLOT_BYTES, 4):
        validation_memory[slot_base + offset] = 0
    rewritten = bytearray(dos_buffer)
    effective: list[tuple[Descriptor, int]] = []
    for descriptor in parsed.descriptors:
        target = effective_target(descriptor.target, slot_base=slot_base)
        if validation_memory.get(target) != descriptor.expected:
            events.extend(("expected_mismatch", "free_call", "control_clear", "state_84"))
            state_trace.append(0x84)
            return result(
                0x84,
                bytes_read=bytes_read,
                malloc_calls=1,
                malloc_successes=1,
                free_calls=1,
                interval=allocation_interval,
                freed_pointer=bank_base,
                released_interval=allocation_interval,
                failure_reason="expected_mismatch",
            )
        if token_allowed(descriptor.target):
            struct.pack_into("<I", rewritten, descriptor.header_offset, target)
        effective.append((descriptor, target))

    events.append("validate_complete")
    after = dict(validation_memory)
    for descriptor, target in effective:
        after[target] = bank_base + descriptor.marker_offset
    events.extend(("patch_complete", "count_publish", "state_02"))
    state_trace.append(0x02)
    return result(
        0x02,
        published=len(parsed.render_rows),
        final_memory=after,
        private_bank=bytes(rewritten),
        control_bank=bank_base,
        control_table=bank_base + HEADER_SIZE,
        control_slot=slot_base,
        bytes_read=bytes_read,
        malloc_calls=1,
        malloc_successes=1,
        live=True,
        interval=allocation_interval,
    )


def resolve_render_pointer(
    parsed: ParsedBank,
    text: bytes,
    memory: Mapping[int, int],
    *,
    slot_base: int,
) -> int | None:
    """Model the first-match resolver and per-use token guard."""
    for row in parsed.render_rows:
        if text.startswith(row.prefix):
            if not token_allowed(row.token):
                return None
            value = memory.get(slot_base + row.token, 0)
            return value or None
    return None
