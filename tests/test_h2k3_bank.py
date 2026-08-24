#!/usr/bin/env python3
"""Offline unit tests for the H2K3 bank and malloc-lifetime model."""

from __future__ import annotations

import struct
import unittest

from tools.localization.h2k3_bank import (
    ALLOCATION_SIZE,
    DOS_READ_LIMIT,
    HEADER,
    HEADER_SIZE,
    MARKER,
    MAX_BANK_LENGTH,
    RENDER_ROW,
    SLOT_BYTES,
    SLOT_OFFSET,
    BankError,
    fnv1a32,
    parse_bank,
    resolve_render_pointer,
    scan_descriptor_payload_machine,
    serialize_bank,
    simulate_atomic_load,
    token_allowed,
)


MAPPING_TAG = 0xFF3DD427
UNIT_START = 0x31271C
UNIT_END = 0x312824
BANK_BASE = 0x50000000
UNIT_TARGET = UNIT_START
UNIT_EXPECTED = 0x0017F000
PREFIX_A = b"{Basic Leade"
PREFIX_B = b"{Advanced Le"


def checksummed(raw: bytearray) -> bytes:
    struct.pack_into("<I", raw, 0x1C, fnv1a32(raw[HEADER_SIZE:]))
    return bytes(raw)


def sample_bank() -> tuple[bytes, tuple, tuple]:
    return serialize_bank(
        ((PREFIX_A, 0), (PREFIX_B, 4)),
        (
            (UNIT_TARGET, UNIT_EXPECTED, b"unit"),
            (0, 0, b"first"),
            (4, 0, b"second"),
        ),
        mapping_tag=MAPPING_TAG,
        unit_start=UNIT_START,
        unit_end=UNIT_END,
    )


class H2K3BankTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bank, self.rows, self.descriptors = sample_bank()
        self.memory = {UNIT_TARGET: UNIT_EXPECTED}

    def parse(self, raw: bytes, **kwargs):
        return parse_bank(
            raw,
            expected_mapping_tag=MAPPING_TAG,
            unit_start=UNIT_START,
            unit_end=UNIT_END,
            **kwargs,
        )

    def simulate(self, raw: bytes | None, memory=None, **kwargs):
        return simulate_atomic_load(
            raw,
            self.memory if memory is None else memory,
            bank_base=BANK_BASE,
            expected_mapping_tag=MAPPING_TAG,
            unit_start=UNIT_START,
            unit_end=UNIT_END,
            **kwargs,
        )

    def test_header_schema_and_roundtrip(self) -> None:
        self.assertEqual(HEADER.format, "<4sHHIBBHIIII")
        self.assertEqual(HEADER.size, 32)
        fields = HEADER.unpack_from(self.bank)
        self.assertEqual(fields[4], 2)
        self.assertEqual(fields[5], 0)
        parsed = self.parse(self.bank)
        self.assertEqual(len(parsed.render_rows), 2)
        self.assertEqual(len(parsed.descriptors), 3)
        self.assertEqual(parsed.raw, self.bank)

    def test_machine_descriptor_scan_advances_on_every_non_nul_byte(self) -> None:
        descriptor = self.descriptors[1]
        scan = scan_descriptor_payload_machine(self.bank, descriptor.marker_offset, len(self.bank))
        expected = tuple(range(descriptor.data_offset, descriptor.data_offset + len(descriptor.encoded) + 1))
        self.assertEqual(scan.visited_offsets, expected)
        self.assertEqual(scan.terminator_offset, descriptor.data_offset + len(descriptor.encoded))
        self.assertEqual(scan.next_record_offset, scan.terminator_offset + 1)
        self.assertTrue(
            all(right == left + 1 for left, right in zip(scan.visited_offsets, scan.visited_offsets[1:]))
        )

        truncated = self.bank[: scan.terminator_offset]
        with self.assertRaisesRegex(BankError, "no terminator"):
            scan_descriptor_payload_machine(truncated, descriptor.marker_offset, len(truncated))

    def test_success_rebases_private_tokens_and_publishes_last(self) -> None:
        slot_base = BANK_BASE + SLOT_OFFSET
        dirty = dict(self.memory)
        for offset in range(0, SLOT_BYTES, 4):
            dirty[slot_base + offset] = 0xDEADBEEF
        loaded = self.simulate(self.bank, dirty)

        self.assertEqual(loaded.state, 0x02)
        self.assertEqual(loaded.state_trace, (0x00, 0x01, 0x02))
        self.assertEqual(loaded.published_render_count, 2)
        self.assertEqual(loaded.control["bank_pointer"], BANK_BASE)
        self.assertEqual(loaded.control["table_pointer"], BANK_BASE + HEADER_SIZE)
        self.assertEqual(loaded.control["slot_pointer"], slot_base)
        self.assertEqual(loaded.allocation_interval, (BANK_BASE, BANK_BASE + ALLOCATION_SIZE))
        self.assertTrue(loaded.live_allocation)
        self.assertEqual((loaded.malloc_calls, loaded.malloc_successes, loaded.free_calls), (1, 1, 0))
        self.assertEqual(loaded.freed_pointer, 0)
        self.assertIsNone(loaded.released_interval)
        self.assertIsNone(loaded.failure_reason)
        self.assertEqual(
            loaded.events[-4:],
            ("validate_complete", "patch_complete", "count_publish", "state_02"),
        )

        self.assertIsNotNone(loaded.private_bank)
        private = loaded.private_bank or b""
        for descriptor in self.descriptors:
            expected_target = slot_base + descriptor.target if token_allowed(descriptor.target) else descriptor.target
            self.assertEqual(struct.unpack_from("<I", private, descriptor.header_offset)[0], expected_target)
            self.assertEqual(loaded.memory[expected_target], BANK_BASE + descriptor.marker_offset)
            self.assertEqual(private[descriptor.marker_offset], MARKER)

        self.assertEqual(loaded.memory[slot_base + 8], 0)
        self.assertEqual(resolve_render_pointer(self.parse(self.bank), PREFIX_A + b" rest", loaded.memory, slot_base=slot_base), loaded.memory[slot_base])

    def test_missing_and_null_allocation_have_no_free(self) -> None:
        missing = self.simulate(None)
        self.assertEqual(missing.state, 0x81)
        self.assertEqual((missing.malloc_calls, missing.free_calls), (0, 0))
        self.assertEqual(missing.failure_reason, "open_missing")
        self.assertEqual(missing.memory, self.memory)
        self.assertEqual(missing.control["bank_pointer"], 0)

        null = self.simulate(self.bank, allocation_succeeds=False)
        self.assertEqual(null.state, 0x85)
        self.assertEqual((null.malloc_calls, null.malloc_successes, null.free_calls), (1, 0, 0))
        self.assertEqual(null.failure_reason, "allocation_null")
        self.assertEqual(null.memory, self.memory)
        self.assertEqual(null.control["active_render_count"], 0)
        self.assertEqual(null.events[-3:], ("malloc_null", "close", "state_85"))

    def test_read_error_frees_exact_allocation_and_clears_controls(self) -> None:
        failed = self.simulate(self.bank, read_succeeds=False)
        self.assertEqual(failed.state, 0x83)
        self.assertEqual((failed.malloc_calls, failed.malloc_successes, failed.free_calls), (1, 1, 1))
        self.assertEqual(failed.freed_pointer, BANK_BASE)
        self.assertEqual(failed.released_interval, (BANK_BASE, BANK_BASE + ALLOCATION_SIZE))
        self.assertFalse(failed.live_allocation)
        self.assertEqual(failed.memory, self.memory)
        self.assertEqual((failed.bank_base, failed.table_pointer, failed.slot_base), (0, 0, 0))
        self.assertEqual(failed.events[-3:], ("free_call", "control_clear", "state_83"))

    def test_checksum_expected_and_oversize_reasons_are_distinct_and_atomic(self) -> None:
        corrupt = bytearray(self.bank)
        corrupt[-2] ^= 1
        checksum = self.simulate(bytes(corrupt))
        self.assertEqual(checksum.failure_reason, "checksum_mismatch")

        expected = self.simulate(self.bank, {UNIT_TARGET: UNIT_EXPECTED ^ 4})
        self.assertEqual(expected.failure_reason, "expected_mismatch")

        oversize_raw = self.bank + b"X" * (DOS_READ_LIMIT - len(self.bank) + 123)
        oversize = self.simulate(oversize_raw)
        self.assertEqual(oversize.failure_reason, "oversize_read")
        self.assertEqual(oversize.bytes_read, DOS_READ_LIMIT)

        for failed in (checksum, expected, oversize):
            self.assertEqual(failed.state, 0x84)
            self.assertEqual((failed.malloc_calls, failed.malloc_successes, failed.free_calls), (1, 1, 1))
            self.assertEqual(failed.freed_pointer, BANK_BASE)
            self.assertEqual(failed.released_interval, (BANK_BASE, BANK_BASE + ALLOCATION_SIZE))
            self.assertEqual(failed.memory, checksum.memory if failed is checksum else ({UNIT_TARGET: UNIT_EXPECTED ^ 4} if failed is expected else self.memory))
            self.assertEqual((failed.bank_base, failed.table_pointer, failed.slot_base), (0, 0, 0))

    def test_reserved_byte_is_always_rejected(self) -> None:
        raw = bytearray(self.bank)
        raw[0x0D] = 1
        with self.assertRaisesRegex(BankError, "reserved"):
            self.parse(bytes(raw), strict_authoring=False, reject_duplicates=False)

    def test_header_and_body_malformed_corpus(self) -> None:
        cases: dict[str, bytes] = {}
        raw = bytearray(self.bank); raw[0] ^= 1; cases["magic"] = bytes(raw)
        raw = bytearray(self.bank); struct.pack_into("<H", raw, 4, 4); cases["version"] = bytes(raw)
        raw = bytearray(self.bank); struct.pack_into("<H", raw, 6, 0); cases["count"] = bytes(raw)
        raw = bytearray(self.bank); struct.pack_into("<I", raw, 8, len(raw) + 1); cases["length"] = bytes(raw)
        raw = bytearray(self.bank); struct.pack_into("<H", raw, 14, 31); cases["header"] = bytes(raw)
        raw = bytearray(self.bank); struct.pack_into("<I", raw, 16, 31); cases["table"] = bytes(raw)
        raw = bytearray(self.bank); struct.pack_into("<I", raw, 20, 31); cases["records"] = bytes(raw)
        raw = bytearray(self.bank); struct.pack_into("<I", raw, 24, MAPPING_TAG ^ 1); cases["mapping"] = bytes(raw)
        raw = bytearray(self.bank); raw[self.descriptors[0].marker_offset] = 0x41; cases["marker"] = checksummed(raw)
        raw = bytearray(self.bank); raw[-1] = 0x41; cases["terminator"] = checksummed(raw)
        raw = bytearray(self.bank); raw.extend(b"X"); struct.pack_into("<I", raw, 8, len(raw)); cases["trailing"] = checksummed(raw)
        raw = bytearray(self.bank); struct.pack_into("<I", raw, self.descriptors[0].header_offset, 0x20000000); cases["target"] = checksummed(raw)

        for name, malformed in cases.items():
            with self.subTest(name=name), self.assertRaises(BankError):
                self.parse(malformed, strict_authoring=False, reject_duplicates=False)
            with self.subTest(name=f"atomic-{name}"):
                failed = self.simulate(malformed)
                self.assertEqual(failed.state, 0x84)
                self.assertEqual(failed.memory, self.memory)
                self.assertEqual(failed.free_calls, 1)

    def test_every_strict_prefix_truncation_fails_closed(self) -> None:
        for cut in range(len(self.bank)):
            with self.subTest(cut=cut):
                failed = self.simulate(self.bank[:cut])
                self.assertEqual(failed.state, 0x84)
                self.assertEqual(failed.memory, self.memory)
                self.assertEqual(failed.free_calls, 1)
                self.assertEqual((failed.bank_base, failed.table_pointer, failed.slot_base), (0, 0, 0))

    def test_fnv_covers_every_body_byte(self) -> None:
        for offset in range(HEADER_SIZE, len(self.bank)):
            corrupt = bytearray(self.bank)
            corrupt[offset] ^= 1
            with self.subTest(offset=offset):
                failed = self.simulate(bytes(corrupt))
                self.assertEqual(failed.failure_reason, "checksum_mismatch")
                self.assertEqual(failed.memory, self.memory)
                self.assertEqual(failed.free_calls, 1)

    def test_authoring_rejects_duplicate_prefix_token_and_target(self) -> None:
        base_descriptors = ((UNIT_TARGET, UNIT_EXPECTED, b"u"), (0, 0, b"a"), (4, 0, b"b"))
        with self.assertRaisesRegex(BankError, "prefix is duplicated"):
            serialize_bank(((PREFIX_A, 0), (PREFIX_A, 4)), base_descriptors, mapping_tag=MAPPING_TAG, unit_start=UNIT_START, unit_end=UNIT_END)
        with self.assertRaisesRegex(BankError, "token is duplicated"):
            serialize_bank(((PREFIX_A, 0), (PREFIX_B, 0)), base_descriptors, mapping_tag=MAPPING_TAG, unit_start=UNIT_START, unit_end=UNIT_END)
        with self.assertRaisesRegex(BankError, "target is duplicated"):
            serialize_bank(((PREFIX_A, 0),), ((0, 0, b"a"), (0, 0, b"b")), mapping_tag=MAPPING_TAG, unit_start=UNIT_START, unit_end=UNIT_END)

    def test_runtime_duplicate_descriptor_is_deterministic_last_wins(self) -> None:
        raw = bytearray(self.bank)
        struct.pack_into("<I", raw, self.descriptors[2].header_offset, 0)
        duplicate = checksummed(raw)
        with self.assertRaisesRegex(BankError, "duplicated"):
            self.parse(duplicate)
        runtime = self.parse(duplicate, reject_duplicates=False, strict_authoring=False)
        loaded = self.simulate(duplicate)
        slot_base = BANK_BASE + SLOT_OFFSET
        self.assertEqual(loaded.state, 0x02)
        self.assertEqual(loaded.memory[slot_base], BANK_BASE + runtime.descriptors[2].marker_offset)
        self.assertEqual(loaded.memory[slot_base + 4], 0)

    def test_runtime_duplicate_render_prefix_is_deterministic_first_match(self) -> None:
        raw = bytearray(self.bank)
        second_prefix = HEADER_SIZE + RENDER_ROW.size
        raw[second_prefix : second_prefix + 12] = PREFIX_A
        duplicate = checksummed(raw)
        with self.assertRaisesRegex(BankError, "prefix is duplicated"):
            self.parse(duplicate)
        runtime = self.parse(duplicate, reject_duplicates=False, strict_authoring=False)
        loaded = self.simulate(duplicate)
        first_pointer = loaded.memory[BANK_BASE + SLOT_OFFSET]
        second_pointer = loaded.memory[BANK_BASE + SLOT_OFFSET + 4]
        self.assertNotEqual(first_pointer, second_pointer)
        self.assertEqual(
            resolve_render_pointer(runtime, PREFIX_A + b" suffix", loaded.memory, slot_base=loaded.slot_base),
            first_pointer,
        )

    def test_invalid_runtime_render_token_is_guarded_at_use(self) -> None:
        raw = bytearray(self.bank)
        struct.pack_into("<I", raw, HEADER_SIZE + 12, 0x400)
        malformed_row = checksummed(raw)
        with self.assertRaisesRegex(BankError, "token is not allowed"):
            self.parse(malformed_row)
        runtime = self.parse(malformed_row, reject_duplicates=False, strict_authoring=False)
        loaded = self.simulate(malformed_row)
        self.assertEqual(loaded.state, 0x02)
        self.assertIsNone(resolve_render_pointer(runtime, PREFIX_A + b" suffix", loaded.memory, slot_base=loaded.slot_base))

    def test_token_descriptor_expected_must_be_zero_for_authoring(self) -> None:
        with self.assertRaisesRegex(BankError, "expected must be zero"):
            serialize_bank(((PREFIX_A, 0),), ((0, 1, b"bad"),), mapping_tag=MAPPING_TAG, unit_start=UNIT_START, unit_end=UNIT_END)
        raw = bytearray(self.bank)
        struct.pack_into("<I", raw, self.descriptors[1].header_offset + 4, 1)
        nonzero = checksummed(raw)
        with self.assertRaisesRegex(BankError, "expected must be zero"):
            self.parse(nonzero)
        failed = self.simulate(nonzero)
        self.assertEqual(failed.failure_reason, "expected_mismatch")

    def test_token_boundaries_and_direct_only_bank(self) -> None:
        self.assertTrue(token_allowed(0))
        self.assertTrue(token_allowed(0x3FC))
        for value in (-1, 1, 0x3FD, 0x400, 0xFFFFFFFF):
            self.assertFalse(token_allowed(value))
        direct, _, _ = serialize_bank((), ((UNIT_TARGET, UNIT_EXPECTED, b"direct"),), mapping_tag=MAPPING_TAG, unit_start=UNIT_START, unit_end=UNIT_END)
        loaded = self.simulate(direct)
        self.assertEqual(loaded.state, 0x02)
        self.assertEqual(loaded.published_render_count, 0)

    def test_exact_maximum_bank_and_ff00_rejection(self) -> None:
        fixed = HEADER_SIZE + 8 + 1 + 1
        maximum_payload = b"A" * (MAX_BANK_LENGTH - fixed)
        maximum, _, _ = serialize_bank((), ((UNIT_TARGET, UNIT_EXPECTED, maximum_payload),), mapping_tag=MAPPING_TAG, unit_start=UNIT_START, unit_end=UNIT_END)
        self.assertEqual(len(maximum), MAX_BANK_LENGTH)
        self.parse(maximum)
        with self.assertRaisesRegex(BankError, "exceeds"):
            serialize_bank((), ((UNIT_TARGET, UNIT_EXPECTED, maximum_payload + b"A"),), mapping_tag=MAPPING_TAG, unit_start=UNIT_START, unit_end=UNIT_END)

    def test_allocator_contract_preconditions_are_not_fake_runtime_branches(self) -> None:
        for invalid_base in (0x50000001, 0xFFFF0000):
            with self.subTest(base=hex(invalid_base)), self.assertRaisesRegex(BankError, "allocator returned"):
                simulate_atomic_load(self.bank, self.memory, bank_base=invalid_base, expected_mapping_tag=MAPPING_TAG, unit_start=UNIT_START, unit_end=UNIT_END)
        with self.assertRaisesRegex(BankError, "overlaps"):
            self.simulate(self.bank, protected_intervals=((BANK_BASE + 0x1000, BANK_BASE + 0x2000),))
        loaded = self.simulate(self.bank, protected_intervals=((0x100000, 0x200000), (0x60000000, 0x60001000)))
        self.assertEqual(loaded.state, 0x02)


if __name__ == "__main__":
    unittest.main()
