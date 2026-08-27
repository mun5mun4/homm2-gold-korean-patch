#!/usr/bin/env python3
"""Build HoMM2 bitmap-font resources from bundled or user-selected fonts.

The module rasterizes only the 874 characters declared by the release mapping
and returns rebuilt AGG bytes to the transactional installer.  A separately
selected user font is read locally and is never copied into the package.
"""

from __future__ import annotations

import hashlib
import heapq
import io
import re
import struct
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from PIL import Image, ImageDraw, ImageFont


FONT_RESOURCE_NAMES = ("FONT.ICN", "SMALFONT.ICN")
LEGACY_SPRITE_COUNT = 96
AT_SIGN_SPRITE_INDEX = 32
KOREAN_FIRST_INDEX = 0x100
KOREAN_LAST_INDEX = 0x469
KOREAN_GLYPH_COUNT = KOREAN_LAST_INDEX - KOREAN_FIRST_INDEX + 1
FILLER_SPRITE_COUNT = KOREAN_FIRST_INDEX - LEGACY_SPRITE_COUNT
FINAL_SPRITE_COUNT = KOREAN_LAST_INDEX + 1
NORMAL_PIXEL_SIZE = 14
SMALL_PIXEL_SIZE = 12
NORMAL_CELL_WIDTH = 13
NORMAL_CELL_HEIGHT = 14
SMALL_CELL_WIDTH = 11
SMALL_CELL_HEIGHT = 12
FOREGROUND_PALETTE_INDEX = 10
SHADOW_PALETTE_INDEX = 21
SHADOW_OFFSET_X = 1
SHADOW_OFFSET_Y = 1
MINIMUM_PIXEL_SIZE = 4
RENDERER_ID = "pillow-freetype-monochrome-v3-typographic-baseline"
BASELINE_POLICY = "logical-cell-preserve-glyph-bearing-common-baseline-v3"
FIT_POLICY = "largest-common-integer-pixel-size-ink-union-fit-v3"
CROP_POLICY = "tight-mask-preserve-logical-cell-offset-v1"
SHADOW_POLICY = "clip-at-logical-cell-edge-v1"
# The fixed raster identities below describe the historical Nanum default.
# Other pinned or user-selected fonts receive the same structural/ROI checks,
# while their exact generated identities are recorded in the install receipt.
CANONICAL_RASTER_PRIMARY_SHA256 = "787EFFD7EFED2ABCA88ADE231FAA8191F4E9FCF85B1805A13EE1DC3724B72089"

RECRUIT_COST_RESOURCE_NAME = "RECRBKG.ICN"
RECRUIT_COST_LABEL = "병력당 비용:"
RECRUIT_COST_ROI = (157, 51, 96, 17)
RECRUIT_COST_BACKGROUND_SAMPLE_X = 151
RECRUIT_COST_TOP_ADJUST = 2
RECRUIT_COST_FOREGROUND_PALETTE_INDEX = 10
RECRUIT_COST_SHADOW_PALETTE_INDEX = 51
RECRUIT_COST_SOURCE_SIZE = 91_987
RECRUIT_COST_SOURCE_SHA256 = "D7B9EF7C819CADACFABF0BCB857976535945DC6F52DC60581D30AC69513E7024"
RECRUIT_COST_OUTPUT_SIZE = 102_017
RECRUIT_COST_OUTPUT_SHA256 = "F4A2C1B33BDA292E1F4DB06DDE6FF65F1DCF7CA554037FB1011360C6071C505D"
RECRUIT_COST_GLYPH_BOX = (62, 11)
RECRUIT_COST_INK_BBOX = (175, 56, 236, 67)
RECRUIT_COST_INK_PIXEL_COUNT = 339
# Absolute sprite indices pinned by mapping874.fixed-interface-font.txt.  Legacy
# ASCII sprites use ord(character) - 0x20; Korean sprites begin at 0x100.
RECRUIT_COST_GLYPHS = (
    ("병", 0x122, True),
    ("력", 0x115, True),
    ("당", 0x17D, True),
    (" ", 0x00, False),
    ("비", 0x163, True),
    ("용", 0x127, True),
    (":", 0x1A, False),
)

# Fixed English labels baked into original ICN sprites.  HSBTNS.ICN is
# intentionally absent: the earlier user-approved policy keeps the vertical
# hero DISMISS/EXIT buttons in English while their hover/status text is Korean.
IMAGE_UI_RESOURCE_SOURCE_IDENTITIES = {
    "REQUEST.ICN": (9_086, "C5261794A31EDD5B01B4A53C56926E069B633A62F71424E990FEC99BB2AD4D1C"),
    "REQUESTS.ICN": (16_833, "30FD5D32B8264A5739994B1EE7632CC4FCCF96E5C1323D7CFC37124B1D1056B7"),
    "SYSTEM.ICN": (12_180, "CAB48A99ACB61E882D391BF6E2507C0D2B418381E86C1F007AACDFFE6B94881D"),
    "SYSTEME.ICN": (12_089, "66C49A2003AB894194557804EAE68A758ECC7B0FAA350FFB5FC02898D2D26F2C"),
    "TREASURY.ICN": (5_258, "1D2A54B0A1C4A47B388D93C6E3866B499B71289283F2A5D859D1E432E446BBB5"),
    "WELLXTRA.ICN": (2_108, "B4A586C13741A5DD1346A342637C9AD265155C55D20B64292A7D718A05FBC2B0"),
    "WELLBKG.ICN": (231_294, "37A87BBF0BC7EAF5018CD67806ED9287AB5C26265657F7ABFD01D67AE5152A6B"),
    "RECRUIT.ICN": (8_003, "13F9EB5BE2893288DF9F15F383F30852D8BD1BA47765C2274D430372C9031A69"),
    "TRADPOST.ICN": (12_879, "A81EEA8B1E3E2044AA284575D2A4720DFDD564B20A8106706071F3B7B6225837"),
}
IMAGE_UI_RESOURCE_OUTPUT_IDENTITIES = {
    "REQUEST.ICN": (14_274, "04541CF630A12ECE6B90CC03A6FFBF5E60E572AEA5DA9A87F94C4519E42A728B"),
    "REQUESTS.ICN": (30_419, "E41F68ED5451E2F6B6541760E6FC2B38A047DE592F37CC3AE3DBD6C06F43810F"),
    "SYSTEM.ICN": (26_972, "BF7EAA196ADD7A89C79F920119B34225EFB15F50317016A3DDEE73B0A0C90E5E"),
    "SYSTEME.ICN": (26_956, "F46894FBE3DBF51FBD9C953F6EEC0834675CC126A8F6952462D6C63EADF92DE9"),
    "TREASURY.ICN": (7_533, "3F2270A7B2F180C45149C552E8A9E31877A2C358E73DB240A04027DF77CCF0B8"),
    "WELLXTRA.ICN": (3_134, "B52ADBA156834F9D401EB661D487D304DCC35961FF65348EC7A95BC1D8C3CE46"),
    "WELLBKG.ICN": (264_852, "2902B596AC1C17B41357A3AD93BEDDABB809514E797F7A2E5B65C082AC6F9005"),
    "RECRUIT.ICN": (14_527, "D7A987F150444CF904C36AA02FAD0C3555EB0AEC180141BCAF7F0D0252BCDB44"),
    "TRADPOST.ICN": (18_686, "964AA3433C5891950EFB33A20D43A64B9AA8038BD6E478A57272B857EA3A612D"),
}
IMAGE_UI_PALETTE_MAPS = {
    "good_released": {FOREGROUND_PALETTE_INDEX: 10, SHADOW_PALETTE_INDEX: 51},
    "good_pressed": {FOREGROUND_PALETTE_INDEX: 62, SHADOW_PALETTE_INDEX: 42},
    "evil_released": {FOREGROUND_PALETTE_INDEX: 10, SHADOW_PALETTE_INDEX: 26},
    "evil_pressed": {FOREGROUND_PALETTE_INDEX: 36, SHADOW_PALETTE_INDEX: 18},
    # Expansion campaign-slot captions are intentionally flat dark letters,
    # unlike the embossed action buttons around them.
    "plain_good_released": {FOREGROUND_PALETTE_INDEX: 32, SHADOW_PALETTE_INDEX: 41},
    "embedded_evil_released": {FOREGROUND_PALETTE_INDEX: 10, SHADOW_PALETTE_INDEX: 32},
    "town_cost_released": {FOREGROUND_PALETTE_INDEX: 10, SHADOW_PALETTE_INDEX: 10},
    "town_released": {FOREGROUND_PALETTE_INDEX: 129, SHADOW_PALETTE_INDEX: 111},
    "town_pressed": {FOREGROUND_PALETTE_INDEX: 61, SHADOW_PALETTE_INDEX: 117},
}
IMAGE_UI_TEXT_TARGETS = (
    # Shared request/system OKAY buttons.
    {"resource": "REQUEST.ICN", "sprite": 1, "text": "확인", "state": "released", "interface": "good", "roi": (14, 4, 68, 17), "background": 41},
    {"resource": "REQUEST.ICN", "sprite": 2, "text": "확인", "state": "pressed", "interface": "good", "roi": (14, 5, 68, 17), "background": 45},
    {"resource": "REQUEST.ICN", "sprite": 3, "text": "취소", "state": "released", "interface": "good", "roi": (6, 4, 84, 17), "background": 41},
    {"resource": "REQUEST.ICN", "sprite": 4, "text": "취소", "state": "pressed", "interface": "good", "roi": (6, 5, 84, 17), "background": 45},
    {"resource": "REQUESTS.ICN", "sprite": 1, "text": "확인", "state": "released", "interface": "good", "roi": (14, 4, 68, 17), "background": 41},
    {"resource": "REQUESTS.ICN", "sprite": 2, "text": "확인", "state": "pressed", "interface": "good", "roi": (14, 5, 68, 17), "background": 45},
    {"resource": "REQUESTS.ICN", "sprite": 3, "text": "취소", "state": "released", "interface": "good", "roi": (6, 4, 84, 17), "background": 41},
    {"resource": "REQUESTS.ICN", "sprite": 4, "text": "취소", "state": "pressed", "interface": "good", "roi": (6, 5, 84, 17), "background": 45},
    {"resource": "REQUESTS.ICN", "sprite": 9, "text": "소", "state": "released", "interface": "good", "roi": (4, 4, 48, 17), "background": 41},
    {"resource": "REQUESTS.ICN", "sprite": 10, "text": "소", "state": "pressed", "interface": "good", "roi": (4, 5, 48, 17), "background": 45},
    {"resource": "REQUESTS.ICN", "sprite": 11, "text": "중", "state": "released", "interface": "good", "roi": (4, 4, 48, 17), "background": 41},
    {"resource": "REQUESTS.ICN", "sprite": 12, "text": "중", "state": "pressed", "interface": "good", "roi": (4, 5, 48, 17), "background": 45},
    {"resource": "REQUESTS.ICN", "sprite": 13, "text": "대", "state": "released", "interface": "good", "roi": (4, 4, 48, 17), "background": 41},
    {"resource": "REQUESTS.ICN", "sprite": 14, "text": "대", "state": "pressed", "interface": "good", "roi": (4, 5, 48, 17), "background": 45},
    {"resource": "REQUESTS.ICN", "sprite": 15, "text": "특대", "state": "released", "interface": "good", "roi": (4, 4, 48, 17), "background": 41},
    {"resource": "REQUESTS.ICN", "sprite": 16, "text": "특대", "state": "pressed", "interface": "good", "roi": (4, 5, 48, 17), "background": 45},
    {"resource": "REQUESTS.ICN", "sprite": 17, "text": "전체", "state": "released", "interface": "good", "roi": (4, 4, 48, 17), "background": 41},
    {"resource": "REQUESTS.ICN", "sprite": 18, "text": "전체", "state": "pressed", "interface": "good", "roi": (4, 5, 48, 17), "background": 45},
    {"resource": "SYSTEM.ICN", "sprite": 1, "text": "확인", "state": "released", "interface": "good", "roi": (6, 4, 83, 17), "background": 41},
    {"resource": "SYSTEM.ICN", "sprite": 2, "text": "확인", "state": "pressed", "interface": "good", "roi": (6, 5, 83, 17), "background": 45},
    {"resource": "SYSTEM.ICN", "sprite": 3, "text": "취소", "state": "released", "interface": "good", "roi": (6, 4, 83, 17), "background": 41},
    {"resource": "SYSTEM.ICN", "sprite": 4, "text": "취소", "state": "pressed", "interface": "good", "roi": (6, 5, 83, 17), "background": 45},
    {"resource": "SYSTEM.ICN", "sprite": 5, "text": "예", "state": "released", "interface": "good", "roi": (6, 4, 83, 17), "background": 41},
    {"resource": "SYSTEM.ICN", "sprite": 6, "text": "예", "state": "pressed", "interface": "good", "roi": (6, 5, 83, 17), "background": 45},
    {"resource": "SYSTEM.ICN", "sprite": 7, "text": "아니요", "state": "released", "interface": "good", "roi": (6, 4, 83, 17), "background": 41},
    {"resource": "SYSTEM.ICN", "sprite": 8, "text": "아니요", "state": "pressed", "interface": "good", "roi": (6, 5, 83, 17), "background": 45},
    {"resource": "SYSTEM.ICN", "sprite": 9, "text": "배우기", "state": "released", "interface": "good", "roi": (6, 4, 83, 17), "background": 41},
    {"resource": "SYSTEM.ICN", "sprite": 10, "text": "배우기", "state": "pressed", "interface": "good", "roi": (6, 5, 83, 17), "background": 45},
    {"resource": "SYSTEME.ICN", "sprite": 1, "text": "확인", "state": "released", "interface": "evil", "roi": (6, 4, 83, 17), "background": 17},
    {"resource": "SYSTEME.ICN", "sprite": 2, "text": "확인", "state": "pressed", "interface": "evil", "roi": (6, 5, 83, 17), "background": 21},
    {"resource": "SYSTEME.ICN", "sprite": 3, "text": "취소", "state": "released", "interface": "evil", "roi": (6, 4, 83, 17), "background": 17},
    {"resource": "SYSTEME.ICN", "sprite": 4, "text": "취소", "state": "pressed", "interface": "evil", "roi": (6, 5, 83, 17), "background": 21},
    {"resource": "SYSTEME.ICN", "sprite": 5, "text": "예", "state": "released", "interface": "evil", "roi": (6, 4, 83, 17), "background": 17},
    {"resource": "SYSTEME.ICN", "sprite": 6, "text": "예", "state": "pressed", "interface": "evil", "roi": (6, 5, 83, 17), "background": 21},
    {"resource": "SYSTEME.ICN", "sprite": 7, "text": "아니요", "state": "released", "interface": "evil", "roi": (6, 4, 83, 17), "background": 17},
    {"resource": "SYSTEME.ICN", "sprite": 8, "text": "아니요", "state": "pressed", "interface": "evil", "roi": (6, 5, 83, 17), "background": 21},
    {"resource": "SYSTEME.ICN", "sprite": 9, "text": "배우기", "state": "released", "interface": "evil", "roi": (6, 4, 83, 17), "background": 17},
    {"resource": "SYSTEME.ICN", "sprite": 10, "text": "배우기", "state": "pressed", "interface": "evil", "roi": (6, 5, 83, 17), "background": 21},
    # Castle, well, recruit and trading-post buttons.
    {"resource": "TREASURY.ICN", "sprite": 1, "text": "나가기", "state": "released", "interface": "good", "roi": (10, 4, 60, 17), "background": 41},
    {"resource": "TREASURY.ICN", "sprite": 2, "text": "나가기", "state": "pressed", "interface": "good", "roi": (10, 5, 60, 17), "background": 45},
    {"resource": "WELLXTRA.ICN", "sprite": 0, "text": "나가기", "state": "released", "interface": "good", "roi": (6, 2, 49, 15), "background": 41},
    {"resource": "WELLXTRA.ICN", "sprite": 1, "text": "나가기", "state": "pressed", "interface": "good", "roi": (6, 3, 49, 15), "background": 45},
    {"resource": "RECRUIT.ICN", "sprite": 4, "text": "최대", "state": "released", "interface": "good", "roi": (8, 5, 52, 20), "layout_roi": (8, 5, 50, 20), "clear_roi": (8, 5, 52, 16), "background": 41},
    {"resource": "RECRUIT.ICN", "sprite": 5, "text": "최대", "state": "pressed", "interface": "good", "roi": (8, 6, 52, 20), "layout_roi": (8, 6, 50, 20), "clear_roi": (8, 6, 52, 16), "background": 45},
    # CANCEL reaches outside the old 68-pixel text ROI.  Reuse a cleaned copy
    # of the matching standard button face so no C/L fragments remain while
    # the original corner highlights and bevel are retained.
    {"resource": "RECRUIT.ICN", "sprite": 6, "text": "취소", "state": "released", "interface": "good", "roi": (6, 4, 84, 17), "background": 41, "donor_resource": "REQUEST.ICN", "donor_sprite": 1, "donor_clear_roi": (14, 4, 68, 17)},
    {"resource": "RECRUIT.ICN", "sprite": 7, "text": "취소", "state": "pressed", "interface": "good", "roi": (6, 5, 84, 17), "background": 45, "donor_resource": "REQUEST.ICN", "donor_sprite": 2, "donor_clear_roi": (14, 5, 68, 17)},
    {"resource": "RECRUIT.ICN", "sprite": 8, "text": "확인", "state": "released", "interface": "good", "roi": (14, 4, 68, 17), "background": 41},
    {"resource": "RECRUIT.ICN", "sprite": 9, "text": "확인", "state": "pressed", "interface": "good", "roi": (14, 5, 68, 17), "background": 45},
    {"resource": "TRADPOST.ICN", "sprite": 15, "text": "거래", "state": "released", "interface": "good", "roi": (6, 4, 84, 17), "background": 41},
    {"resource": "TRADPOST.ICN", "sprite": 16, "text": "거래", "state": "pressed", "interface": "good", "roi": (6, 5, 84, 17), "background": 45},
    {"resource": "TRADPOST.ICN", "sprite": 17, "text": "나가기", "state": "released", "interface": "good", "roi": (6, 4, 84, 17), "background": 41},
    {"resource": "TRADPOST.ICN", "sprite": 18, "text": "나가기", "state": "pressed", "interface": "good", "roi": (6, 5, 84, 17), "background": 45},
)
IMAGE_UI_WELL_MIRROR = {
    "source_resource": "WELLXTRA.ICN",
    "source_sprite": 0,
    "source_roi": (6, 2, 49, 15),
    "target_resource": "WELLBKG.ICN",
    "target_sprite": 0,
    "target_roi": (584, 463, 49, 15),
}

# Large tan menu/network/editor buttons share one 132x62 face.  Protocol names,
# COM port identifiers and baud-rate units remain technical Latin labels; only
# natural-language actions and player counts are localized.
MENU132_RESOURCE_SOURCE_IDENTITIES = {
    "BTNCMPGN.ICN": (30_975, "76C767E9BCB8E2EE2531D38845F87E7081214429AE099C1A3E2DD923B55BF256"),
    "BTNCOM.ICN": (27_107, "EB9A5808F8F8B339057E6F09553ADDCF155598DD1EE860549C6E1ED33AFB0CEE"),
    "BTNHOTST.ICN": (36_319, "6C226BD99F2A31B77B7296C1DE55CD9FBD4CE7EB669379CEF1AC0C0D8B666C46"),
    "BTNMODEM.ICN": (20_521, "0D63A8A29FEBEAB464830970120450A25FDA2F22EE98790D0B9FDD7F22EFDF34"),
    "BTNMP.ICN": (31_426, "9A6A8E811DE32C387BDFD60CA1D61C1791659AE9AF29A524C00343787D899640"),
    "BTNNET.ICN": (16_503, "B59426AC09EAC53451235C7C8417C06B185B8B07028CBBC73D44B8F27A01888A"),
    "BTNNEWGM.ICN": (29_594, "788F504FEFB3FEC6310FD04A70E9E9C5E0312E82BBF2660967885D88E7EE8595"),
    "BTNNET2.ICN": (21_530, "DE51C2837D4BE85265C8B91D521AFC74D89B49D67F10121BD727D878464C8366"),
    "BTNMCFG.ICN": (27_891, "72005E24BBFAF2358A8B0B9CB69A14306CCF0D9F51A727219BE08550BCF8369B"),
    "BTNBAUD.ICN": (30_975, "76C767E9BCB8E2EE2531D38845F87E7081214429AE099C1A3E2DD923B55BF256"),
    "BTNDC.ICN": (16_503, "B59426AC09EAC53451235C7C8417C06B185B8B07028CBBC73D44B8F27A01888A"),
    "BTNDCCFG.ICN": (22_264, "EA12C7B3A0ABE58643B4A47370A10A6405E14A6B57C9D12D1FE0EBFAC09319CE"),
}
MENU132_RESOURCE_OUTPUT_IDENTITIES = {
    "BTNCMPGN.ICN": (41_993, "5D360E43603F724BE3FC50A1EB247E746726294223A9E84E0A32870C65EF296C"),
    "BTNCOM.ICN": (38_125, "8CDCE025FFC6F8BDC04A01E2E49A5C8AA6D042FE4804F1D1723F0C4167F9266A"),
    "BTNHOTST.ICN": (100_614, "022BB338F1477FD08AA1B1DC8F2333EC2AB6F9A2C7BEF0797D18B0F81AF5606A"),
    "BTNMODEM.ICN": (50_310, "625899E7269A31F17D444D04F0F755321AB9C4FC626B72EE45DBF9F7CBE5B887"),
    "BTNMP.ICN": (72_798, "C4D7B12BFBE7E5033838DC5D3DE3950F432E0FFF01490BC429A80D72FFAC4D5A"),
    "BTNNET.ICN": (50_310, "6DA519A401D0EE601C2D4F56E86C1933E925705628C6D60D4EA10A509E869BA7"),
    "BTNNEWGM.ICN": (67_078, "CC2F54172847909E5ADE64BAA25A8E1BF30878FA60CDDD8133C5DA4800757302"),
    "BTNNET2.ICN": (32_548, "CD0DFA23164647DA49D5093314B8FB1638D2346D62A4A57569DB7F0A69CEE265"),
    "BTNMCFG.ICN": (67_078, "FF51E7EFDA1876AE123C09A60C388855C46ED6BEF4A3CC1402FA73C426F1A22E"),
    "BTNBAUD.ICN": (41_993, "5D360E43603F724BE3FC50A1EB247E746726294223A9E84E0A32870C65EF296C"),
    "BTNDC.ICN": (50_310, "6DA519A401D0EE601C2D4F56E86C1933E925705628C6D60D4EA10A509E869BA7"),
    "BTNDCCFG.ICN": (67_078, "023355861483A875CB49D88838826453A64A0DCE71D50F213EA296F938CF0182"),
}
MENU132_TEXT_PAIRS = {
    "BTNCMPGN.ICN": ((8, "취소"),),
    "BTNCOM.ICN": ((8, "취소"),),
    "BTNHOTST.ICN": ((0, "2명"), (2, "3명"), (4, "4명"), (6, "5명"), (8, "6명"), (10, "취소")),
    "BTNMODEM.ICN": ((0, "호스트\n(발신)"), (2, "게스트\n(수신)"), (4, "취소")),
    "BTNMP.ICN": ((0, "교대 플레이"), (2, "네트워크"), (6, "직접 연결"), (8, "취소")),
    "BTNNET.ICN": ((0, "호스트"), (2, "게스트"), (4, "취소")),
    "BTNNEWGM.ICN": ((0, "일반 게임"), (2, "캠페인"), (4, "멀티플레이"), (6, "취소")),
    "BTNNET2.ICN": ((6, "취소"),),
    "BTNMCFG.ICN": ((0, "호스트\n(발신)"), (2, "게스트\n(수신)"), (4, "통신 설정"), (6, "취소")),
    "BTNBAUD.ICN": ((8, "취소"),),
    "BTNDC.ICN": ((0, "호스트"), (2, "게스트"), (4, "취소")),
    "BTNDCCFG.ICN": ((0, "호스트"), (2, "게스트"), (4, "설정"), (6, "취소")),
}
MENU132_TEXT_TARGETS = tuple(
    {
        "resource": resource_name,
        "sprite": released_index + state_index,
        "text": text,
        "state": state,
        "interface": "good",
        "roi": (8, 8, 116, 46),
        "background": 41 if state == "released" else 45,
        "donor_resource": "BTNCOM.ICN",
        "donor_sprite": state_index,
        "donor_clear_roi": (24, 14 + state_index, 84, 34),
        "line_gap": 2,
    }
    for resource_name, pairs in MENU132_TEXT_PAIRS.items()
    for released_index, text in pairs
    for state_index, state in enumerate(("released", "pressed"))
)

# Campaign progress screens use narrow ornamental faces whose English letters
# are multi-tone relief pixels.  Only those non-background pixels are cleared;
# the wood/stone button face and the lower wooden ledge stay byte-exact.
CAMPAIGN_BUTTON_RESOURCE_SOURCE_IDENTITIES = {
    "CAMPXTRG.ICN": (33_201, "1F167F64CA88A2E7AC951E7E8599C37523DC68B8480A547AB3B0AC40052D57C7"),
    "CAMPXTRE.ICN": (32_985, "0F2321C66D33F7DBE7D75D625085523402A7BC895847E002B815B65FC0EA01B5"),
    "X_CMPBTN.ICN": (9_585, "7085A085D2203DD3EF552862623538841DFC048B26ACC351BD468AFBE578A3A4"),
}
CAMPAIGN_BUTTON_RESOURCE_OUTPUT_IDENTITIES = {
    "CAMPXTRG.ICN": (45_413, "9336FA9B38175ACB185BFE82C4D3CECAB3D0B28784BF7DC7C498C8E96E033DE0"),
    "CAMPXTRE.ICN": (45_369, "B49C6F6BA3F03BB94D8964BF429BB20860BC708E678BE62D507497870472AE83"),
    "X_CMPBTN.ICN": (20_418, "D0116130DAB40107BDA3827E0405D353E70E82515CABD326C66CE894ED0BBE10"),
}
CAMPAIGN_BUTTON_ARCHIVE_RESOURCE_SETS = (
    frozenset(("CAMPXTRG.ICN", "CAMPXTRE.ICN")),
    frozenset(("X_CMPBTN.ICN",)),
)
CAMPAIGN_BUTTON_LABELS = ("인트로 보기", "다시 시작", "확인", "취소")
CAMPAIGN_BUTTON_LAYOUTS = {
    "CAMPXTRG.ICN": (
        ((10, 4, 131, 16), (6, 6, 128, 15)),
        ((14, 4, 95, 16), (6, 6, 95, 15)),
        ((27, 4, 57, 16), (20, 6, 56, 15)),
        ((10, 3, 89, 17), (8, 6, 80, 15)),
    ),
    "CAMPXTRE.ICN": (
        ((8, 4, 131, 16), (6, 6, 128, 15)),
        ((12, 4, 95, 16), (6, 6, 95, 15)),
        ((25, 4, 57, 16), (20, 6, 56, 15)),
        ((8, 3, 89, 17), (8, 6, 80, 15)),
    ),
    "X_CMPBTN.ICN": (
        ((6, 4, 127, 16), (5, 5, 128, 15)),
        ((6, 4, 95, 16), (5, 5, 95, 15)),
        ((19, 4, 57, 16), (19, 5, 56, 15)),
        ((5, 3, 85, 17), (7, 5, 80, 15)),
    ),
}
CAMPAIGN_BUTTON_TEXT_TARGETS = tuple(
    {
        "resource": resource_name,
        "sprite": label_index * 2 + state_index,
        "text": CAMPAIGN_BUTTON_LABELS[label_index],
        "state": state,
        "interface": "good" if resource_name == "CAMPXTRG.ICN" else "evil",
        "roi": CAMPAIGN_BUTTON_LAYOUTS[resource_name][label_index][state_index],
        "background": (
            (41 if state == "released" else 45)
            if resource_name == "CAMPXTRG.ICN"
            else (17 if state == "released" else 22)
        ),
        "clear_mode": "non_background",
    }
    for resource_name in CAMPAIGN_BUTTON_LAYOUTS
    for label_index in range(len(CAMPAIGN_BUTTON_LABELS))
    for state_index, state in enumerate(("released", "pressed"))
)

# The campaign-progress backgrounds bake their captions into full-screen
# textured bitmaps.  English relief pixels are selected with pinned palette
# masks, the exposed texture is restored from nearby same-surface pixels, and
# Korean captions are drawn with the generated font.  The base archive owns
# the two original-campaign variants; the expansion archive owns X_CMPBKG.
CAMP_PROGRESS_RESOURCE_SOURCE_IDENTITIES = {
    "CAMPBKGG.ICN": (282_547, "F98DBAF55DD3A5AA0A53E8E763C1BFDEB221D1CFE6754862053ECBCC69EA6806"),
    "CAMPBKGE.ICN": (282_033, "5574FBF2908870662FE5F1D6B0AE2B26E7B9529FCAA2C9BBF3B355A98C2577E2"),
    "X_CMPBKG.ICN": (285_412, "D1EF57097A52B57A016F9C8DB3E29F7633FE552CD01A5B12AE8C3B1DE19A266C"),
}
CAMP_PROGRESS_RESOURCE_OUTPUT_IDENTITIES = {
    "CAMPBKGG.ICN": (310_580, "77E189C4E3F7AA778D17D8217B197259BCB848B3F3BE0DA1680BDDE39249AC2A"),
    "CAMPBKGE.ICN": (310_580, "2F3E0BA725AA06E7B75315A6D3B1CA8EAC2F2269936AAA6293C438B0F1EEEEB6"),
    "X_CMPBKG.ICN": (310_580, "1AA00F02FEBD3BF686B263AB74F903A5328567D2073F371558A64C8C38476FDF"),
}
CAMP_PROGRESS_ARCHIVE_RESOURCE_SETS = (
    frozenset(("CAMPBKGG.ICN", "CAMPBKGE.ICN")),
    frozenset(("X_CMPBKG.ICN",)),
)
CAMP_PROGRESS_PALETTE_MAPS = {
    "good": {FOREGROUND_PALETTE_INDEX: 113, SHADOW_PALETTE_INDEX: 62},
    "evil": {FOREGROUND_PALETTE_INDEX: 12, SHADOW_PALETTE_INDEX: 36},
}
CAMP_PROGRESS_SPECS = {
    "CAMPBKGG.ICN": {
        "theme": "good",
        "texts": (
            {
                "key": "title",
                "english": "ROLAND'S CAMPAIGN",
                "text": "롤란드의 캠페인",
                "mask_roi": (78, 31, 268, 36),
                "layout_roi": (60, 32, 320, 34),
                "forced_mask": (82, 32, 40, 34),
                "seed": "gold",
                "dilate": 3,
                "clone": ("same_y_bands", ((31, 77), (365, 391)), 101),
                "font": "normal",
                "scale": 2,
            },
            {
                "key": "days",
                "english": "DAYS SPENT:",
                "text": "진행 일수",
                "mask_roi": (417, 28, 158, 24),
                "layout_roi": (416, 28, 165, 24),
                "seed": "gold",
                "dilate": 3,
                "clone": ("same_y_bands", ((577, 608),), 211),
                "font": "small",
                "scale": 2,
            },
            {
                "key": "scenario",
                "english": "SCENARIO",
                "text": "시나리오",
                "mask_roi": (36, 85, 113, 23),
                "layout_roi": (35, 84, 135, 24),
                "seed": "gold",
                "dilate": 3,
                "clone": ("same_y_bands", ((153, 190),), 307),
                "font": "small",
                "scale": 2,
            },
            {
                "key": "awards",
                "english": "AWARDS",
                "text": "보상",
                "mask_roi": (466, 73, 96, 22),
                "layout_roi": (450, 72, 128, 24),
                "seed": "gold",
                "dilate": 3,
                "clone": ("offset", (0, 31)),
                "font": "small",
                "scale": 2,
            },
            {
                "key": "choice",
                "english": "CHOICE",
                "text": "선택",
                "mask_roi": (467, 181, 96, 22),
                "layout_roi": (450, 180, 128, 24),
                "seed": "gold",
                "dilate": 3,
                "clone": ("offset", (0, 31)),
                "font": "small",
                "scale": 2,
            },
        ),
    },
    "CAMPBKGE.ICN": {
        "theme": "evil",
        "texts": (
            {
                "key": "title",
                "english": "ARCHIBALD'S CAMPAIGN",
                "text": "아치발드의 캠페인",
                "mask_roi": (66, 31, 296, 36),
                "layout_roi": (55, 32, 330, 34),
                "forced_mask": (68, 32, 43, 34),
                "seed": "light",
                "dilate": 3,
                "clone": ("same_y_bands", ((31, 65), (365, 391)), 401),
                "font": "normal",
                "scale": 2,
            },
            {
                "key": "days",
                "english": "DAYS SPENT:",
                "text": "진행 일수",
                "mask_roi": (417, 28, 158, 24),
                "layout_roi": (416, 28, 165, 24),
                "seed": "light",
                "dilate": 3,
                "clone": ("same_y_bands", ((577, 608),), 503),
                "font": "small",
                "scale": 2,
            },
            {
                "key": "scenario",
                "english": "SCENARIO",
                "text": "시나리오",
                "mask_roi": (36, 85, 113, 23),
                "layout_roi": (35, 84, 135, 24),
                "seed": "light",
                "dilate": 3,
                "clone": ("same_y_bands", ((153, 190),), 601),
                "font": "small",
                "scale": 2,
            },
            {
                "key": "awards",
                "english": "AWARDS",
                "text": "보상",
                "mask_roi": (466, 73, 96, 22),
                "layout_roi": (450, 72, 128, 24),
                "seed": "light",
                "dilate": 3,
                "clone": ("offset", (0, 31)),
                "font": "small",
                "scale": 2,
            },
            {
                "key": "choice",
                "english": "CHOICE",
                "text": "선택",
                "mask_roi": (467, 181, 96, 22),
                "layout_roi": (450, 180, 128, 24),
                "seed": "light",
                "dilate": 3,
                "clone": ("offset", (0, 31)),
                "font": "small",
                "scale": 2,
            },
        ),
    },
    "X_CMPBKG.ICN": {
        "theme": "good",
        "texts": (
            {
                "key": "days",
                "english": "DAYS SPENT:",
                "text": "진행 일수",
                "mask_roi": (417, 28, 158, 24),
                "layout_roi": (416, 28, 165, 24),
                "seed": "gold",
                "dilate": 3,
                "clone": ("same_y_bands", ((577, 608),), 701),
                "font": "small",
                "scale": 2,
            },
            {
                "key": "scenario",
                "english": "SCENARIO",
                "text": "시나리오",
                "mask_roi": (36, 85, 113, 23),
                "layout_roi": (35, 84, 135, 24),
                "seed": "gold",
                "dilate": 3,
                "clone": ("same_y_bands", ((153, 190),), 809),
                "font": "small",
                "scale": 2,
            },
            {
                "key": "awards",
                "english": "AWARDS",
                "text": "보상",
                "mask_roi": (466, 73, 96, 22),
                "layout_roi": (450, 72, 128, 24),
                "seed": "gold",
                "dilate": 3,
                "clone": ("offset", (0, 31)),
                "font": "small",
                "scale": 2,
            },
            {
                "key": "choice",
                "english": "CHOICE",
                "text": "선택",
                "mask_roi": (467, 181, 96, 22),
                "layout_roi": (450, 180, 128, 24),
                "seed": "gold",
                "dilate": 3,
                "clone": ("offset", (0, 31)),
                "font": "small",
                "scale": 2,
            },
        ),
    },
}

# Common in-game action panels.  These resources are all owned by the base
# archive; embedded default faces in larger backgrounds are mirrored in a
# separate pass after their standalone faces have been localized.
GAME_BUTTON_RESOURCE_SOURCE_IDENTITIES = {
    "SPANBTN.ICN": (2_123, "F6C32575201ACD1C6AB763DBB97B2B226747C2E798BA0D36E51D95F7C9C5236E"),
    "SPANBTNE.ICN": (2_107, "08C15712CEA91924DAD137D72F637E7528BE6A1D6F18395AE5CAA0C573FA3DEF"),
    "CSPANBTN.ICN": (2_123, "F6C32575201ACD1C6AB763DBB97B2B226747C2E798BA0D36E51D95F7C9C5236E"),
    "CSPANBTE.ICN": (2_107, "08C15712CEA91924DAD137D72F637E7528BE6A1D6F18395AE5CAA0C573FA3DEF"),
    "ESPANBTN.ICN": (2_123, "F6C32575201ACD1C6AB763DBB97B2B226747C2E798BA0D36E51D95F7C9C5236E"),
    "SWAPBTN.ICN": (2_279, "6BC36FB2D9C6FC2B11E7B65AE062F9F8CB9CC400A4C0B5100366193A5FA33302"),
    "TRADPOSE.ICN": (12_856, "DF108CC59C44CFE89721390CC01098116EB8ECD601349395FE00CDBD8FAC54C4"),
    "VIEWARMY.ICN": (143_520, "F8C6587410AC0665423F7F1FAF543084B31525B7443D6CC70521B73FBCE7486C"),
    "VIEWARME.ICN": (137_203, "8BF92CBBD933FD79F438EE6D51DB86F2A6646B5BC8008E7F85C83B3CEE59A907"),
    "SURRENDR.ICN": (6_859, "497F662822C69E0A47457426385C74AC1CEC1FFC6290CDDD0633A0FA0279142E"),
    "SURRENDE.ICN": (6_849, "F9AE4719D391E6947A22FA3B2120545625FB1E26C7D78422D71FEB08CB689D92"),
    "OVERVIEW.ICN": (115_306, "844B858FDB0AB37B82FC4537933678C73DBA8081DEE77CA6AC223B8051F97D8F"),
    "APANEL.ICN": (15_838, "98FA663E052BB2AD52537123A6D300301B0241ED9036F415D33242322F564673"),
    "APANELE.ICN": (15_191, "6C57698DBAFFF3F969FFC69A1CFFB1A9A8D9F88E08A92B55FDC9EC793523E7D9"),
    "CPANEL.ICN": (18_388, "CCA49B25158201F3772B1965D2F1AB855B27F1B0504157F654CD7BC2CB345733"),
    "CPANELE.ICN": (17_766, "563C181DF2ECD2D65E6EB9FFCFB6589501BF29FB5299386160D4A5B0268C0041"),
    "WINCMBTB.ICN": (2_052, "DDB4CB6930264FA8E73E9B2E6C525BCE239B7879FA91D3C8A73C8087F6A7D497"),
    "WINCMBBE.ICN": (2_051, "3D1EC96064E761ED912F5C4408C7CDC681C13DFFE4D41232AA0BAB8FDC6200F9"),
    "NGEXTRA.ICN": (120_603, "E4D9C99E7400C1922DFFBB0D01F08217DE1CC72D29C20BD3C7F4666CB5F48860"),
}
GAME_BUTTON_RESOURCE_OUTPUT_IDENTITIES = {
    "SPANBTN.ICN": (4_904, "272FEC88AC4FCE5ACB4DA4450C1E2892BF38C1C5376EF8B8A808F691084883C3"),
    "SPANBTNE.ICN": (4_904, "043EE51A25D58D2A599F4A4E112B944A0D041D427895CCE9E395DFA5E7C0D63C"),
    "CSPANBTN.ICN": (4_904, "272FEC88AC4FCE5ACB4DA4450C1E2892BF38C1C5376EF8B8A808F691084883C3"),
    "CSPANBTE.ICN": (4_904, "043EE51A25D58D2A599F4A4E112B944A0D041D427895CCE9E395DFA5E7C0D63C"),
    "ESPANBTN.ICN": (4_904, "272FEC88AC4FCE5ACB4DA4450C1E2892BF38C1C5376EF8B8A808F691084883C3"),
    "SWAPBTN.ICN": (4_620, "AA336E37E994CE3D4A10151515500C63E56E936D4CF40DAA28DAE49DB5B8B4D7"),
    "TRADPOSE.ICN": (18_691, "5BAF8032AA5EDFECA01256A5A4DC6C8F79F290C4994C5E2500CE7EA071ADAABB"),
    "VIEWARMY.ICN": (150_991, "8123A0DD4C5D6381243F3CC1F4BB742E1E3CEC233819BEB5E1C449E2F214280B"),
    "VIEWARME.ICN": (144_764, "DC064F16AD94B399B8EEE68CDB8C80E7993F92B5F1606AC1159DB73E9AE75036"),
    "SURRENDR.ICN": (14_339, "0C83BFE00CE77863B3A5C2FFB1D261210A18F63FAC5E8335738B72FD4FA64995"),
    "SURRENDE.ICN": (14_331, "1961BB8C92182F1295C5DD8BC3EAE5F3537D70763115495286E4590044D8C0A5"),
    "OVERVIEW.ICN": (127_803, "8F21B2C92EA76B0E21D72CD4D2B9B580DC6D28122DD74B0ECF6DC2A48D3A1FBE"),
    "APANEL.ICN": (26_092, "67186726201331849D987A1A858AF293994F28CC899F30B6252BE5B3EF26D8EA"),
    "APANELE.ICN": (25_612, "C53F68DAE9776EAE614E7697C995B3A12485689EC7B3C881E75AA60051A03881"),
    "CPANEL.ICN": (48_843, "3A7F127E287A2A597DE2BAE6FBD70360941A562AF80FF7A3F4E11CD76B90093D"),
    "CPANELE.ICN": (48_843, "29A2AC360226278B8B77B52D6987C09443BF7B91FD109EDDF6CB6659277F9F6C"),
    "WINCMBTB.ICN": (4_108, "409532F71A34A416EB843518C30517F5015EACAD01C4188795DE96020DA4C070"),
    "WINCMBBE.ICN": (4_108, "C1944ADB1FD12D69834179768A6844E7E0DEAC7F6E18FAC5A161E5D676E142DD"),
    "NGEXTRA.ICN": (127_161, "9C32F8A8F4EB3F7E020677BAA7C5FACC239E61FAE3D595F4B7CB8FDA9CEF5737"),
}
GAME_BUTTON_EVIL_RESOURCES = frozenset(
    ("SPANBTNE.ICN", "CSPANBTE.ICN", "TRADPOSE.ICN", "VIEWARME.ICN", "SURRENDE.ICN", "APANELE.ICN", "CPANELE.ICN", "WINCMBBE.ICN")
)
GAME_BUTTON_PAIR_SPECS = {
    "SPANBTN.ICN": ((0, "확인", (6, 4, 83, 17), (6, 5, 84, 17)),),
    "SPANBTNE.ICN": ((0, "확인", (6, 4, 83, 17), (6, 5, 84, 17)),),
    "CSPANBTN.ICN": ((0, "확인", (6, 4, 83, 17), (6, 5, 84, 17)),),
    "CSPANBTE.ICN": ((0, "확인", (6, 4, 83, 17), (6, 5, 84, 17)),),
    "ESPANBTN.ICN": ((0, "확인", (6, 4, 83, 17), (6, 5, 84, 17)),),
    "SWAPBTN.ICN": ((0, "나가기", (6, 4, 68, 18), (6, 5, 68, 18)),),
    "TRADPOSE.ICN": (
        (15, "거래", (6, 4, 84, 17), (6, 5, 84, 17)),
        (17, "나가기", (6, 4, 84, 17), (6, 5, 84, 17)),
    ),
    "VIEWARMY.ICN": (
        (1, "해산", (4, 4, 88, 19), (4, 5, 88, 19)),
        (3, "나가기", (6, 4, 84, 18), (6, 5, 84, 18)),
        (5, "승급", (4, 4, 88, 19), (4, 5, 88, 19)),
    ),
    "VIEWARME.ICN": (
        (1, "해산", (4, 4, 88, 19), (4, 5, 88, 19)),
        (3, "나가기", (6, 4, 84, 18), (6, 5, 84, 18)),
        (5, "승급", (4, 4, 88, 19), (4, 5, 88, 19)),
    ),
    "SURRENDR.ICN": (
        (0, "수락", (8, 4, 100, 19), (8, 5, 100, 19)),
        (2, "거절", (8, 4, 100, 19), (8, 5, 100, 19)),
    ),
    "SURRENDE.ICN": (
        (0, "수락", (8, 4, 100, 19), (8, 5, 100, 19)),
        (2, "거절", (8, 4, 100, 19), (8, 5, 100, 19)),
    ),
    "OVERVIEW.ICN": (
        (0, "영웅", (8, 6, 83, 30), (8, 7, 83, 30)),
        (2, "도시/성", (8, 6, 83, 30), (8, 7, 83, 30)),
        (4, "나가기", (7, 4, 85, 17), (7, 5, 85, 17)),
    ),
    "APANEL.ICN": (
        (4, "정보", (14, 18, 68, 20), (14, 19, 68, 20)),
        (8, "취소", (6, 4, 84, 17), (6, 5, 84, 17)),
    ),
    "APANELE.ICN": (
        (4, "정보", (14, 18, 68, 20), (14, 19, 68, 20)),
        (8, "취소", (6, 4, 84, 17), (6, 5, 84, 17)),
    ),
    "CPANEL.ICN": (
        (0, "새 게임", (8, 8, 80, 40), (8, 9, 80, 40)),
        (2, "불러오기", (8, 8, 80, 40), (8, 9, 80, 40)),
        (4, "저장하기", (8, 8, 80, 40), (8, 9, 80, 40)),
        (6, "게임 종료", (8, 8, 80, 40), (8, 9, 80, 40)),
        (8, "취소", (6, 4, 84, 17), (6, 5, 84, 17)),
    ),
    "CPANELE.ICN": (
        (0, "새 게임", (8, 8, 80, 40), (8, 9, 80, 40)),
        (2, "불러오기", (8, 8, 80, 40), (8, 9, 80, 40)),
        (4, "저장하기", (8, 8, 80, 40), (8, 9, 80, 40)),
        (6, "게임 종료", (8, 8, 80, 40), (8, 9, 80, 40)),
        (8, "취소", (6, 4, 84, 17), (6, 5, 84, 17)),
    ),
    "WINCMBTB.ICN": ((0, "확인", (6, 4, 68, 17), (6, 5, 68, 17)),),
    "WINCMBBE.ICN": ((0, "확인", (6, 4, 68, 17), (6, 5, 68, 17)),),
    "NGEXTRA.ICN": (
        (64, "선택", (4, 2, 72, 15), (4, 3, 72, 15)),
        (66, "확인", (6, 4, 84, 17), (6, 5, 84, 17)),
        (68, "취소", (6, 4, 84, 17), (6, 5, 84, 17)),
    ),
}
GAME_BUTTON_TEXT_TARGETS = tuple(
    {
        "resource": resource_name,
        "sprite": released_index + state_index,
        "text": text,
        "state": state,
        "interface": "evil" if resource_name in GAME_BUTTON_EVIL_RESOURCES else "good",
        "roi": released_roi if state == "released" else pressed_roi,
        "background": (
            (17 if state == "released" else 21)
            if resource_name in GAME_BUTTON_EVIL_RESOURCES
            else (41 if state == "released" else 45)
        ),
        "clear_mode": "non_background",
    }
    for resource_name, pairs in GAME_BUTTON_PAIR_SPECS.items()
    for released_index, text, released_roi, pressed_roi in pairs
    for state_index, state in enumerate(("released", "pressed"))
)

EXPANSION_MENU_RESOURCE_SOURCE_IDENTITIES = {
    "X_NEWCMP.ICN": (29_418, "3FB04F8FC1802126BA0377CA78FBB94D7CA1982921CD8C74EBF963BD149A8267"),
    "X_LOADCM.ICN": (23_312, "A262DEFF1214F7B6B330BA2C8157FEAD3D4F7C76A552931E65F60E5E11D1F0DA"),
    "X_MAPMNU.ICN": (20_486, "D25EF7EF33A316C0107576EAAF71C4DD921B61B1933F7DEF49CD476F27CCCB3D"),
}
EXPANSION_MENU_RESOURCE_OUTPUT_IDENTITIES = {
    "X_NEWCMP.ICN": (68_820, "C35B912E4DE70B4D5150B364CA65DFB76F74167FF464D9CB1D11A79181808CF4"),
    "X_LOADCM.ICN": (50_310, "B21EA66329A63C1861C2534C0321B83A974A188F2ADD52C18326DC9FA7866876"),
    "X_MAPMNU.ICN": (50_310, "D3B069FF847A9F0EF98D21464AA214AB1C124F72ED82AD3055218E558C066A08"),
}
EXPANSION_MENU_ACTION_PAIRS = {
    "X_LOADCM.ICN": ((0, "오리지널 캠페인"), (2, "확장 캠페인"), (4, "취소")),
    "X_MAPMNU.ICN": ((0, "오리지널 맵"), (2, "확장 맵"), (4, "취소")),
}
EXPANSION_MENU_TEXT_TARGETS = (
    *(
        {
            "resource": "X_NEWCMP.ICN",
            "sprite": sprite_index,
            "text": text,
            "state": "released",
            "interface": "plain_good",
            "roi": (8, 8, 116, 46),
            "background": 41,
            "clear_mode": "palettes",
            "clear_palettes": (32,),
        }
        for sprite_index, text in (
            (0, "오리지널"),
            (2, "캠페인 1"),
            (4, "캠페인 2"),
            (6, "캠페인 3"),
            (8, "캠페인 4"),
        )
    ),
    *(
        {
            "resource": "X_NEWCMP.ICN",
            "sprite": 10 + state_index,
            "text": "취소",
            "state": state,
            "interface": "good",
            "roi": (0, 0, 132, 62),
            "layout_roi": (8, 8, 116, 46),
            "background": 41 if state == "released" else 45,
            "donor_resource": "X_NEWCMP.ICN",
            "donor_sprite": state_index,
            "donor_clear_roi": (8, 8, 116, 46),
            "donor_clear_mode": "palettes" if state == "released" else "none",
            "donor_clear_palettes": (32,) if state == "released" else (),
        }
        for state_index, state in enumerate(("released", "pressed"))
    ),
    *(
        {
            "resource": resource_name,
            "sprite": released_index + state_index,
            "text": text,
            "state": state,
            "interface": "good",
            "roi": (0, 0, 132, 62),
            "layout_roi": (8, 8, 116, 46),
            "background": 41 if state == "released" else 45,
            "donor_resource": "X_NEWCMP.ICN",
            "donor_sprite": state_index,
            "donor_clear_roi": (8, 8, 116, 46),
            "donor_clear_mode": "palettes" if state == "released" else "none",
            "donor_clear_palettes": (32,) if state == "released" else (),
        }
        for resource_name, pairs in EXPANSION_MENU_ACTION_PAIRS.items()
        for released_index, text in pairs
        for state_index, state in enumerate(("released", "pressed"))
    ),
)

EMBEDDED_UI_RESOURCE_SOURCE_IDENTITIES = {
    "SPANBKG.ICN": (97_298, "808A3880DE14561DF3DFBFE6DC71419969D4610B0BF5BCA5220AF42440066F36"),
    "SPANBKGE.ICN": (91_025, "0B2430679B4A487C673F4BF2D0CE85C81F066E485980C88EC4666B369028AEDE"),
    "CSPANBKG.ICN": (73_254, "81908B16199CC87C9217BE65E41BC213F5E8907218638213F1E56BEC3C2D4651"),
    "CSPANBKE.ICN": (68_306, "92C648DAC71C1D0DFE1A32B1A93F8D0ADD9F07FC651DF59AE86F2ADF0D62EDDC"),
    "ESPANBKG.ICN": (90_563, "75EBE1B3F3381DD06A1B19FCF3552524C8433E7A09902AD6B2B443928D766669"),
    "REQBKG.ICN": (131_754, "F8B616C6757B7DDA2DA33EDAF3DACB66970D4200BAAD031CFAB35FC59003E031"),
    "REQSBKG.ICN": (163_543, "598325AE397B53468EB2ADD0EF7AE7139671308E147256DAA0E96E85A749D2A2"),
    "RECR2BKG.ICN": (52_522, "26288C033BDE3AE329681E327AB8C6202B5EDF77726758C2E44C458923CE8293"),
    "APANBKG.ICN": (59_163, "C748AD8FEAB326CC9334E6807FBC4CBF9D90BA3CC0C15BA0779F7495CE29005D"),
    "APANBKGE.ICN": (55_495, "02A04B5D197873FC97F896E36CB67E07FBA02640E9848D2D4C01EF54D01336CD"),
    "CPANBKG.ICN": (60_639, "036B1229016484E218E7C9F5C039B33DA8792F32E5F8381667BB6C1D98AF3B59"),
    "CPANBKGE.ICN": (57_001, "260A361A6BB023EF9470BBE89EB1232405194BF5647C7E0E08699B2C77CADE30"),
    "NGSPBKG.ICN": (138_609, "FC7375CD44E232D6D74EACE15CD3BCC20D9A34FE3D6952F6CCDDBEA745825FE2"),
    "NGHSBKG.ICN": (159_395, "9D0EC56C5D65F7B7886A74C18D65CB628454146237D70AB848BE1BBA6D83DAB7"),
    "NGMPBKG.ICN": (177_540, "E4D8F5C87CB2A6E19BFE24448B106D23C718368559EAE73C66DF624492E90D55"),
    "SWAPWIN.ICN": (242_875, "10F67BD4EF22E73AAD0310D061D90E575C8C427BEB7A353085578D7581AA29FD"),
    "SCENIBKG.ICN": (187_445, "3DFF14F8107E3DA605882A20AD97A96977E703213CB30DEACF4178CEB6B1A8A1"),
    "WINLOSE.ICN": (118_203, "C57804D756E5656D5CC52F6D3736E58500A8BFEB7CBB914E481EEF228AB7EECF"),
    "WINLOSEE.ICN": (109_867, "A9CDE777F0142D130F0DED05BBB41FB6FAD79316E3AAAE09A497E8586382DC56"),
    "CASLWIND.ICN": (84_536, "8E7AD0E0D6E02865B94759CBDD06158F490CAE925DB6371ADE399F8B325E430F"),
}
EMBEDDED_UI_RESOURCE_OUTPUT_IDENTITIES = {
    "SPANBKG.ICN": (103_903, "0654E37893084C6B2C4FC30D6207BA430A818F060CCED60DAA65632F71AB2A45"),
    "SPANBKGE.ICN": (103_898, "8551B9A8C3466C2489441BB668E41864E52947B83352865A543308ECB3CD3CAD"),
    "CSPANBKG.ICN": (78_708, "9D28AC80B04C690C5E85F09007B971E77551EA712353E4AEBD580D9D10247B5E"),
    "CSPANBKE.ICN": (78_703, "CBBCEF1B8B883C4850FF3821B70E8F90A9689D4C990E3B6419BB9F0C51C21995"),
    "ESPANBKG.ICN": (102_018, "22C91A0F87EF8F9E53BECC77F739C4676E8D93C864AB0391F5E9F34F5E0D2917"),
    "REQBKG.ICN": (142_721, "6AB4534DE805B574D88A6B191F8EFC96E2C904BDD44D744E6A75B0A791886DF0"),
    "REQSBKG.ICN": (179_227, "D9E61C66748DA140ED696E1DCE0E15F06767B0292E394F3D7048DEFCF7583CF2"),
    "RECR2BKG.ICN": (57_462, "A81FD84293508AB580108C5547E9AB8CE82E45700FBB31C4C91DCD9DE2750D03"),
    "APANBKG.ICN": (79_007, "1FF86B47B4F6D35030C4E93C2031C2CE786759879FE1F670F768752F00ACF4F0"),
    "APANBKGE.ICN": (79_006, "1668670C74FAED451E630884EF705AEC76C620F263D9FA75135BB8129007C39C"),
    "CPANBKG.ICN": (79_007, "15448AB20D0F6DF023307EAA7716B455FF6366F4E3123AEDA94C06BC44F7F899"),
    "CPANBKGE.ICN": (79_006, "9B9FA02A80D1F1E8147DCDF8A9B384A572D7CDA8D93CD8E7379DBFA8F404D527"),
    "NGSPBKG.ICN": (164_192, "E43AD1A14BF6900A1CD89C7DAD7726D6088D86234601F95D4D28E3B952BB9E0C"),
    "NGHSBKG.ICN": (185_930, "8E61AF0E45994A68FB28A0B2C20401731D414D0FB508130632FA629F865481AB"),
    "NGMPBKG.ICN": (205_301, "0B06B723AB6F7EDEDC6CB9E4DD5C989256AAF4ECF4D1D502E5D29F4082B81F69"),
    "SWAPWIN.ICN": (291_980, "9FB333890BEBD1358B6C9104F773B2C90D2BCF7D4D69D93487DE5789E9EBD05C"),
    "SCENIBKG.ICN": (204_808, "16258FDD51DE6B1CD2B2E09F1551C3466C3E891CF05E9425036CC215849C9AF7"),
    "WINLOSE.ICN": (124_481, "EC3265C80F54CD62839625B1F8EC1085ABCCC65E0810EE03DC61BDB2B87C3EBD"),
    "WINLOSEE.ICN": (124_481, "82152C8FCBE123330DB1703AD03CCD0B95A0C0D5EDD9F4F278E3E2991DD36F54"),
    "CASLWIND.ICN": (124_978, "2221A7494EF559C6292D924532525E3DE4F3FAFB6C3F0B422FC652DA01797567"),
}
EMBEDDED_UI_MIRRORS = (
    {"source_resource": "SPANBTN.ICN", "source_sprite": 0, "source_roi": (6, 4, 83, 17), "target_resource": "SPANBKG.ICN", "target_sprite": 0, "target_roi": (119, 366, 83, 17)},
    {"source_resource": "SPANBTNE.ICN", "source_sprite": 0, "source_roi": (6, 4, 83, 17), "target_resource": "SPANBKGE.ICN", "target_sprite": 0, "target_roi": (119, 366, 83, 17)},
    {"source_resource": "CSPANBTN.ICN", "source_sprite": 0, "source_roi": (6, 4, 83, 17), "target_resource": "CSPANBKG.ICN", "target_sprite": 0, "target_roi": (119, 256, 83, 17)},
    {"source_resource": "CSPANBTE.ICN", "source_sprite": 0, "source_roi": (6, 4, 83, 17), "target_resource": "CSPANBKE.ICN", "target_sprite": 0, "target_roi": (119, 256, 83, 17)},
    {"source_resource": "ESPANBTN.ICN", "source_sprite": 0, "source_roi": (6, 4, 83, 17), "target_resource": "ESPANBKG.ICN", "target_sprite": 0, "target_roi": (119, 256, 83, 17)},
    {"source_resource": "REQUEST.ICN", "source_sprite": 1, "source_roi": (14, 4, 68, 17), "target_resource": "REQBKG.ICN", "target_sprite": 0, "target_roi": (257, 320, 68, 17)},
    {"source_resource": "REQUEST.ICN", "source_sprite": 3, "source_roi": (6, 4, 84, 17), "target_resource": "REQBKG.ICN", "target_sprite": 0, "target_roi": (40, 320, 84, 17)},
    *(
        {"source_resource": "REQUESTS.ICN", "source_sprite": source_sprite, "source_roi": (4, 4, 48, 17), "target_resource": "REQSBKG.ICN", "target_sprite": 0, "target_roi": (target_x, 27, 48, 17)}
        for source_sprite, target_x in zip((9, 11, 13, 15, 17), (40, 102, 164, 226, 288))
    ),
    {"source_resource": "REQUESTS.ICN", "source_sprite": 1, "source_roi": (14, 4, 68, 17), "target_resource": "REQSBKG.ICN", "target_sprite": 0, "target_roi": (153, 414, 68, 17)},
    {"source_resource": RECRUIT_COST_RESOURCE_NAME, "source_sprite": 0, "source_roi": RECRUIT_COST_ROI, "target_resource": "RECR2BKG.ICN", "target_sprite": 0, "target_roi": RECRUIT_COST_ROI},
    {"source_resource": "APANEL.ICN", "source_sprite": 4, "source_roi": (14, 18, 68, 20), "target_resource": "APANBKG.ICN", "target_sprite": 0, "target_roi": (76, 125, 68, 20)},
    {"source_resource": "APANEL.ICN", "source_sprite": 8, "source_roi": (6, 4, 84, 17), "target_resource": "APANBKG.ICN", "target_sprite": 0, "target_roi": (134, 188, 84, 17)},
    {"source_resource": "APANELE.ICN", "source_sprite": 4, "source_roi": (14, 18, 68, 20), "target_resource": "APANBKGE.ICN", "target_sprite": 0, "target_roi": (76, 125, 68, 20)},
    {"source_resource": "APANELE.ICN", "source_sprite": 8, "source_roi": (6, 4, 84, 17), "target_resource": "APANBKGE.ICN", "target_sprite": 0, "target_roi": (134, 188, 84, 17)},
    *(
        {"source_resource": source_resource, "source_sprite": source_sprite, "source_roi": source_roi, "target_resource": target_resource, "target_sprite": 0, "target_roi": target_roi}
        for source_resource, target_resource in (("CPANEL.ICN", "CPANBKG.ICN"), ("CPANELE.ICN", "CPANBKGE.ICN"))
        for source_sprite, source_roi, target_roi in (
            (0, (8, 8, 80, 40), (70, 39, 80, 40)),
            (2, (8, 8, 80, 40), (203, 39, 80, 40)),
            (4, (8, 8, 80, 40), (70, 115, 80, 40)),
            (6, (8, 8, 80, 40), (203, 115, 80, 40)),
            (8, (6, 4, 84, 17), (134, 188, 84, 17)),
        )
    ),
    *(
        {"source_resource": "NGEXTRA.ICN", "source_sprite": source_sprite, "source_roi": source_roi, "target_resource": target_resource, "target_sprite": 0, "target_roi": target_roi}
        for target_resource, button_y in (("NGSPBKG.ICN", 330), ("NGHSBKG.ICN", 380), ("NGMPBKG.ICN", 425))
        for source_sprite, source_roi, target_roi in (
            (64, (4, 2, 72, 15), (312, 47, 72, 15)),
            (66, (14, 4, 68, 17), (44, button_y + 4, 68, 17)),
            (68, (6, 4, 84, 17), (293, button_y + 4, 84, 17)),
        )
    ),
    {"source_resource": "SWAPBTN.ICN", "source_sprite": 0, "source_roi": (6, 4, 68, 18), "target_resource": "SWAPWIN.ICN", "target_sprite": 0, "target_roi": (286, 432, 68, 18)},
    {"source_resource": "SYSTEM.ICN", "source_sprite": 1, "source_roi": (14, 4, 67, 17), "target_resource": "SCENIBKG.ICN", "target_sprite": 0, "target_roi": (193, 430, 67, 17)},
    {"source_resource": "WINCMBTB.ICN", "source_sprite": 0, "source_roi": (6, 4, 68, 17), "target_resource": "WINLOSE.ICN", "target_sprite": 0, "target_roi": (126, 414, 68, 17)},
    {"source_resource": "TREASURY.ICN", "source_sprite": 1, "source_roi": (10, 4, 60, 17), "target_resource": "CASLWIND.ICN", "target_sprite": 0, "target_roi": (565, 433, 60, 17)},
)
EMBEDDED_UI_TEXT_TARGETS = (
    {"resource": "WINLOSEE.ICN", "sprite": 0, "text": "확인", "state": "released", "interface": "embedded_evil", "roi": (126, 414, 68, 17), "background": 21},
)

TOWNWIND_RESOURCE_NAME = "TOWNWIND.ICN"
TOWNWIND_SOURCE_IDENTITY = (24_524, "6FB2FF5B55DB92C4E7A28546EBD611C5452688A63164C7AFB78601A5238012AF")
TOWNWIND_OUTPUT_IDENTITY = (30_577, "BAF090734C8A8DDDA54DAB7BEBA23B95597A18A68034D9FC6FC9C953BD912F2C")
TOWNWIND_COST_TARGETS = (
    {
        "resource": TOWNWIND_RESOURCE_NAME,
        "sprite": 3,
        "text": RECRUIT_COST_LABEL,
        "state": "released",
        "interface": "town_cost",
        "roi": (20, 2, 92, 13),
        "background": 0,
        "clear_mode": "row_sample",
        "background_sample_x": 14,
        "skip_shadow": True,
    },
)
TOWNWIND_BUTTON_TARGETS = (
    {"resource": TOWNWIND_RESOURCE_NAME, "sprite": 9, "text": "최대", "state": "released", "interface": "town", "roi": (6, 4, 49, 15), "background": 120, "clear_mode": "non_background"},
    {"resource": TOWNWIND_RESOURCE_NAME, "sprite": 10, "text": "최대", "state": "pressed", "interface": "town", "roi": (6, 5, 48, 14), "background": 122, "clear_mode": "non_background"},
    {"resource": TOWNWIND_RESOURCE_NAME, "sprite": 20, "text": "모집", "state": "released", "interface": "town", "roi": (12, 4, 88, 15), "background": 120, "clear_mode": "non_background"},
    {"resource": TOWNWIND_RESOURCE_NAME, "sprite": 21, "text": "모집", "state": "pressed", "interface": "town", "roi": (12, 5, 87, 14), "background": 122, "clear_mode": "non_background"},
)

# The combat text bar exists only in the base HEROES2.AGG.  Its compact SKIP
# and AUTO controls use the generated small font; HEROES2X.AGG intentionally
# takes the missing-resource no-op path.
TEXTBAR_RESOURCE_NAME = "TEXTBAR.ICN"
TEXTBAR_SOURCE_IDENTITY = (
    18_213,
    "00710457495ED98772F4D6492B6E56189CA9E3277443E792E5F1EE1CC1678A5C",
)
TEXTBAR_OUTPUT_IDENTITY = (
    20_852,
    "A7C6D1AD5424FA086C73335A623B29FA3494CD777274017078220AC0422B6352",
)
TEXTBAR_TARGETS = (
    {"resource": TEXTBAR_RESOURCE_NAME, "sprite": 0, "text": "넘기기", "state": "released", "interface": "good", "roi": (4, 11, 41, 14), "background": 41},
    {"resource": TEXTBAR_RESOURCE_NAME, "sprite": 1, "text": "넘기기", "state": "pressed", "interface": "good", "roi": (4, 12, 41, 14), "background": 45},
    {"resource": TEXTBAR_RESOURCE_NAME, "sprite": 4, "text": "자동", "state": "released", "interface": "good", "roi": (5, 2, 39, 13), "background": 41},
    {"resource": TEXTBAR_RESOURCE_NAME, "sprite": 5, "text": "자동", "state": "pressed", "interface": "good", "roi": (5, 3, 39, 13), "background": 45},
)

# The main menu uses five irregular textured signs rather than flat button
# faces.  Gold English lettering is detected across all four illumination
# states, texture is restored from nearby clean 3x3 patches, and the small
# Korean font is overlaid at 2x scale.  HEROES.ICN contains the same five
# default-state signs; the localized BTNSHNGL state-0 sprites are mirrored
# into both the base and expansion backgrounds.
FANCY_MAIN_MENU_BUTTON_RESOURCE_NAME = "BTNSHNGL.ICN"
FANCY_MAIN_MENU_HEROES_RESOURCE_NAME = "HEROES.ICN"
FANCY_MAIN_MENU_PALETTE_RESOURCE_NAME = "KB.PAL"
FANCY_MAIN_MENU_BUTTON_SOURCE_IDENTITY = (
    89_377,
    "63EADA2F70756BC49CE256F9C3C1BA21330C564A23E345B53649E983F94A61C7",
)
FANCY_MAIN_MENU_BUTTON_OUTPUT_IDENTITY = (
    96_428,
    "A13B2EAE95FBFE63ED2BC096A3954B5F68C808062AC6AFAD92377F132AB0DF6C",
)
FANCY_MAIN_MENU_HEROES_SOURCE_IDENTITIES = {
    "main": (288_082, "0F5F01D354E5E38CB646C0CBC08DBD7D0E1050505B21923EA53A8CBE87F26721"),
    "expansion": (287_946, "98E2233F7108842C93513915324E2D91C2AC85AEEE4A16496DC2A9D253B41534"),
}
FANCY_MAIN_MENU_HEROES_OUTPUT_IDENTITIES = {
    "main": (310_580, "63131E26470F6841CA1359C10696ECF1271AB24A5259AB332C2D673050DE1980"),
    "expansion": (310_580, "41E6D950E3EAFDDEEECAF2794B85B56D7DB387DA5D5C9CA668BF4B79B0904B3D"),
}
FANCY_MAIN_MENU_PALETTE_IDENTITY = (
    768,
    "913EFFF67608A3CBF6381D432BB6CEE467BEF50CEB6F23E13EE320E205BE625A",
)
FANCY_MAIN_MENU_STATE_PALETTES = (
    {FOREGROUND_PALETTE_INDEX: 122, SHADOW_PALETTE_INDEX: 62},
    {FOREGROUND_PALETTE_INDEX: 117, SHADOW_PALETTE_INDEX: 62},
    {FOREGROUND_PALETTE_INDEX: 108, SHADOW_PALETTE_INDEX: 62},
    {FOREGROUND_PALETTE_INDEX: 108, SHADOW_PALETTE_INDEX: 62},
)
FANCY_MAIN_MENU_SPECS = (
    {
        "key": "new_game",
        "text": "새\n게임",
        "sprites": (0, 1, 2, 3),
        "layout_roi": (9, 25, 63, 53),
        "mask_boxes": ((14, 26, 49, 24), (8, 54, 64, 25)),
    },
    {
        "key": "load_game",
        "text": "불러\n오기",
        "sprites": (4, 5, 6, 7),
        "layout_roi": (8, 20, 64, 44),
        "mask_boxes": ((10, 20, 61, 23), (7, 42, 66, 23)),
    },
    {
        "key": "high_scores",
        "text": "최고\n기록",
        "sprites": (8, 9, 10, 11),
        "layout_roi": (7, 9, 70, 49),
        "mask_boxes": ((20, 8, 46, 27), (7, 37, 70, 22)),
    },
    {
        "key": "credits",
        "text": "제작진",
        "sprites": (12, 13, 14, 15),
        "layout_roi": (1, 9, 73, 22),
        "mask_boxes": ((0, 8, 75, 23),),
    },
    {
        "key": "quit",
        "text": "종료",
        "sprites": (16, 17, 18, 19),
        "layout_roi": (12, 10, 66, 24),
        "mask_boxes": ((12, 10, 67, 27),),
    },
)

AGG_ENTRY_SIZE = 12
AGG_NAME_SIZE = 15
ICN_HEADER_SIZE = 6
ICN_SPRITE_HEADER_SIZE = 13
MAPPING_ROW = re.compile(
    r"^index 0x([0-9A-Fa-f]+) escape ([0-9A-Fa-f]{2}) ([0-9A-Fa-f]{2}) = "
    r"U\+([0-9A-Fa-f]{4,6}) (.)$"
)


class FontBuildError(RuntimeError):
    pass


def require(value: bool, message: str) -> None:
    if not value:
        raise FontBuildError(message)


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def agg_filename_hash(name: str) -> int:
    try:
        name.encode("ascii")
    except UnicodeEncodeError as exc:
        raise FontBuildError(f"AGG 리소스 이름이 ASCII가 아닙니다: {name!r}") from exc
    result = 0
    cumulative = 0
    for character in reversed(name):
        value = ord(character.upper())
        result = ((result << 5) + (result >> 25)) & 0xFFFFFFFF
        cumulative = (cumulative + value) & 0xFFFFFFFF
        result = (result + cumulative + value) & 0xFFFFFFFF
    return result


@dataclass(frozen=True)
class MappingRow:
    index: int
    lead: int
    trail: int
    codepoint: int
    character: str


def parse_mapping(path: Path) -> tuple[MappingRow, ...]:
    require(path.is_file(), f"글자 매핑 파일이 없습니다: {path}")
    rows: list[MappingRow] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = MAPPING_ROW.fullmatch(line)
        if match is None:
            continue
        index, lead, trail, codepoint = (int(value, 16) for value in match.groups()[:4])
        character = match.group(5)
        require(character == chr(codepoint), f"매핑 문자와 코드포인트가 다릅니다: {line}")
        rows.append(MappingRow(index, lead, trail, codepoint, character))

    require(len(rows) == KOREAN_GLYPH_COUNT, f"한글 매핑은 {KOREAN_GLYPH_COUNT}자여야 합니다: {len(rows)}")
    require(len({row.codepoint for row in rows}) == len(rows), "한글 매핑에 중복 문자가 있습니다")
    for offset, row in enumerate(rows):
        expected_index = KOREAN_FIRST_INDEX + offset
        expected_lead = 0x82 + (offset >> 7)
        expected_trail = 0x80 + (offset & 0x7F)
        require(row.index == expected_index, f"매핑 인덱스가 연속적이지 않습니다: 0x{row.index:X}")
        require(
            (row.lead, row.trail) == (expected_lead, expected_trail),
            f"매핑 escape가 인덱스와 맞지 않습니다: U+{row.codepoint:04X}",
        )
    return tuple(rows)


def _be_u16(raw: bytes, offset: int, label: str) -> int:
    require(0 <= offset <= len(raw) - 2, f"글꼴 {label} u16 범위가 잘못됐습니다")
    return struct.unpack_from(">H", raw, offset)[0]


def _be_u32(raw: bytes, offset: int, label: str) -> int:
    require(0 <= offset <= len(raw) - 4, f"글꼴 {label} u32 범위가 잘못됐습니다")
    return struct.unpack_from(">I", raw, offset)[0]


def _font_face_offsets(raw: bytes, label: str) -> tuple[int, ...]:
    require(len(raw) >= 12, f"글꼴 파일이 너무 짧습니다: {label}")
    if raw[:4] != b"ttcf":
        return (0,)
    count = _be_u32(raw, 8, f"{label}:ttc-count")
    require(0 < count <= 256 and 12 + count * 4 <= len(raw), f"글꼴 컬렉션 face 수가 잘못됐습니다: {label}")
    offsets = tuple(_be_u32(raw, 12 + index * 4, f"{label}:ttc-offset") for index in range(count))
    require(len(set(offsets)) == len(offsets), f"글꼴 컬렉션 face offset이 중복됐습니다: {label}")
    return offsets


def _sfnt_tables(raw: bytes, face_offset: int, label: str) -> dict[str, tuple[int, int]]:
    require(face_offset + 12 <= len(raw), f"글꼴 face 헤더가 잘렸습니다: {label}")
    require(
        raw[face_offset : face_offset + 4] in {b"\x00\x01\x00\x00", b"OTTO", b"true", b"typ1"},
        f"지원되는 SFNT 글꼴 face가 아닙니다: {label}",
    )
    count = _be_u16(raw, face_offset + 4, f"{label}:table-count")
    require(0 < count <= 4096 and face_offset + 12 + count * 16 <= len(raw), f"글꼴 table 수가 잘못됐습니다: {label}")
    tables: dict[str, tuple[int, int]] = {}
    for index in range(count):
        p = face_offset + 12 + index * 16
        try:
            tag = raw[p : p + 4].decode("ascii")
        except UnicodeDecodeError as exc:
            raise FontBuildError(f"글꼴 table tag가 ASCII가 아닙니다: {label}") from exc
        offset = _be_u32(raw, p + 8, f"{label}:{tag}-offset")
        length = _be_u32(raw, p + 12, f"{label}:{tag}-length")
        require(tag not in tables and offset <= len(raw) and length <= len(raw) - offset, f"글꼴 table 범위가 잘못됐습니다: {label}:{tag}")
        tables[tag] = (offset, length)
    require("cmap" in tables, f"Unicode cmap table이 없는 글꼴입니다: {label}")
    return tables


def _decode_name(raw: bytes, platform: int) -> str:
    try:
        if platform in {0, 3}:
            return raw.decode("utf-16-be").strip("\0 ")
        if platform == 1:
            return raw.decode("mac_roman").strip("\0 ")
        return raw.decode("utf-8").strip("\0 ")
    except UnicodeDecodeError:
        return ""


def _font_names(raw: bytes, tables: Mapping[str, tuple[int, int]], label: str) -> dict[int, str]:
    if "name" not in tables:
        return {}
    offset, length = tables["name"]
    require(length >= 6, f"글꼴 name table이 너무 짧습니다: {label}")
    count = _be_u16(raw, offset + 2, f"{label}:name-count")
    strings_offset = _be_u16(raw, offset + 4, f"{label}:name-strings")
    require(6 + count * 12 <= length and strings_offset <= length, f"글꼴 name table 범위가 잘못됐습니다: {label}")
    candidates: dict[int, list[tuple[tuple[int, int, int], str]]] = {1: [], 2: [], 4: [], 6: []}
    for index in range(count):
        p = offset + 6 + index * 12
        platform, encoding, language, name_id, byte_length, relative = struct.unpack_from(">HHHHHH", raw, p)
        if name_id not in candidates:
            continue
        start = offset + strings_offset + relative
        end = start + byte_length
        if start < offset or end > offset + length:
            continue
        value = _decode_name(raw[start:end], platform)
        if not value:
            continue
        priority = (
            0 if platform == 3 and language == 0x0409 else 1 if platform == 3 else 2 if platform == 0 else 3,
            encoding,
            language,
        )
        candidates[name_id].append((priority, value))
    return {name_id: sorted(values, key=lambda item: item[0])[0][1] for name_id, values in candidates.items() if values}


def _cmap_format4_lookup(raw: bytes, offset: int, length: int, label: str) -> Callable[[int], int]:
    require(length >= 16, f"cmap format 4가 너무 짧습니다: {label}")
    seg_count = _be_u16(raw, offset + 6, f"{label}:seg-count") // 2
    require(0 < seg_count <= 0x8000 and 16 + seg_count * 8 <= length, f"cmap format 4 segment가 잘못됐습니다: {label}")
    ends_offset = offset + 14
    starts_offset = ends_offset + seg_count * 2 + 2
    deltas_offset = starts_offset + seg_count * 2
    ranges_offset = deltas_offset + seg_count * 2
    ends = tuple(_be_u16(raw, ends_offset + index * 2, label) for index in range(seg_count))
    starts = tuple(_be_u16(raw, starts_offset + index * 2, label) for index in range(seg_count))

    def lookup(codepoint: int) -> int:
        if not 0 <= codepoint <= 0xFFFF:
            return 0
        index = bisect_left(ends, codepoint)
        if index >= seg_count or codepoint < starts[index]:
            return 0
        delta = _be_u16(raw, deltas_offset + index * 2, label)
        range_offset = _be_u16(raw, ranges_offset + index * 2, label)
        if range_offset == 0:
            return (codepoint + delta) & 0xFFFF
        glyph_address = ranges_offset + index * 2 + range_offset + (codepoint - starts[index]) * 2
        if glyph_address + 2 > offset + length:
            return 0
        glyph = _be_u16(raw, glyph_address, label)
        return ((glyph + delta) & 0xFFFF) if glyph else 0

    return lookup


def _cmap_group_lookup(raw: bytes, offset: int, length: int, label: str, *, constant: bool) -> Callable[[int], int]:
    require(length >= 16, f"cmap group table이 너무 짧습니다: {label}")
    count = _be_u32(raw, offset + 12, f"{label}:group-count")
    require(count <= 0x100000 and 16 + count * 12 <= length, f"cmap group 수가 잘못됐습니다: {label}")
    starts: list[int] = []
    groups: list[tuple[int, int, int]] = []
    previous_end = -1
    for index in range(count):
        start, end, glyph = struct.unpack_from(">III", raw, offset + 16 + index * 12)
        require(start <= end <= 0x10FFFF and start > previous_end, f"cmap group 범위가 잘못됐습니다: {label}")
        starts.append(start)
        groups.append((start, end, glyph))
        previous_end = end

    def lookup(codepoint: int) -> int:
        index = bisect_right(starts, codepoint) - 1
        if index < 0:
            return 0
        start, end, glyph = groups[index]
        if codepoint > end:
            return 0
        return glyph if constant else glyph + codepoint - start

    return lookup


def _cmap_trimmed_lookup(
    raw: bytes, offset: int, length: int, label: str, *, wide: bool
) -> Callable[[int], int]:
    if wide:
        require(length >= 20, f"cmap format 10이 너무 짧습니다: {label}")
        start = _be_u32(raw, offset + 12, f"{label}:start")
        count = _be_u32(raw, offset + 16, f"{label}:count")
        glyphs_offset = offset + 20
        header_size = 20
    else:
        require(length >= 10, f"cmap format 6이 너무 짧습니다: {label}")
        start = _be_u16(raw, offset + 6, f"{label}:start")
        count = _be_u16(raw, offset + 8, f"{label}:count")
        glyphs_offset = offset + 10
        header_size = 10
    require(count <= 0x110000 and header_size + count * 2 <= length, f"cmap trimmed 범위가 잘못됐습니다: {label}")

    def lookup(codepoint: int) -> int:
        if codepoint < start or codepoint >= start + count:
            return 0
        return _be_u16(raw, glyphs_offset + (codepoint - start) * 2, label)

    return lookup


def _unicode_cmap_lookups(raw: bytes, tables: Mapping[str, tuple[int, int]], label: str) -> tuple[Callable[[int], int], ...]:
    cmap_offset, cmap_length = tables["cmap"]
    require(cmap_length >= 4, f"cmap table이 너무 짧습니다: {label}")
    count = _be_u16(raw, cmap_offset + 2, f"{label}:cmap-count")
    require(4 + count * 8 <= cmap_length, f"cmap encoding record가 잘렸습니다: {label}")
    lookups: list[Callable[[int], int]] = []
    seen_offsets: set[int] = set()
    for index in range(count):
        p = cmap_offset + 4 + index * 8
        platform, encoding = struct.unpack_from(">HH", raw, p)
        if platform != 0 and not (platform == 3 and encoding in {1, 10}):
            continue
        relative = _be_u32(raw, p + 4, f"{label}:cmap-subtable")
        subtable = cmap_offset + relative
        if relative >= cmap_length or subtable in seen_offsets or subtable + 4 > cmap_offset + cmap_length:
            continue
        seen_offsets.add(subtable)
        format_number = _be_u16(raw, subtable, f"{label}:cmap-format")
        if format_number in {4, 6}:
            length = _be_u16(raw, subtable + 2, f"{label}:cmap-length")
        elif format_number in {10, 12, 13}:
            require(subtable + 8 <= cmap_offset + cmap_length, f"cmap subtable 헤더가 잘렸습니다: {label}")
            length = _be_u32(raw, subtable + 4, f"{label}:cmap-length")
        else:
            continue
        if length < 4 or relative + length > cmap_length:
            continue
        sublabel = f"{label}:cmap-{format_number}"
        if format_number == 4:
            lookups.append(_cmap_format4_lookup(raw, subtable, length, sublabel))
        elif format_number == 6:
            lookups.append(_cmap_trimmed_lookup(raw, subtable, length, sublabel, wide=False))
        elif format_number == 10:
            lookups.append(_cmap_trimmed_lookup(raw, subtable, length, sublabel, wide=True))
        elif format_number == 12:
            lookups.append(_cmap_group_lookup(raw, subtable, length, sublabel, constant=False))
        else:
            lookups.append(_cmap_group_lookup(raw, subtable, length, sublabel, constant=True))
    require(lookups, f"지원되는 Unicode cmap 형식이 없습니다: {label}")
    return tuple(lookups)


@dataclass(frozen=True)
class FontFace:
    path: Path
    face_index: int
    face_count: int
    sha256: str
    size: int
    raw: bytes
    family: str
    subfamily: str
    full_name: str
    postscript_name: str
    codepoints: frozenset[int]

    def public_metadata(self) -> dict[str, Any]:
        return {
            "file_name": self.path.name,
            "size": self.size,
            "sha256": self.sha256,
            "face_index": self.face_index,
            "face_count": self.face_count,
            "family": self.family,
            "subfamily": self.subfamily,
            "full_name": self.full_name,
            "postscript_name": self.postscript_name,
        }


def inspect_font(
    path: Path,
    face_index: int = 0,
    required_codepoints: Iterable[int] | None = None,
) -> FontFace:
    path = path.expanduser().resolve(strict=True)
    require(path.is_file(), f"글꼴 파일이 아닙니다: {path}")
    try:
        raw = path.read_bytes()
        face_offsets = _font_face_offsets(raw, path.name)
        face_count = len(face_offsets)
        require(0 <= face_index < face_count, f"글꼴 face 번호 범위는 0..{face_count - 1}입니다: {face_index}")
        tables = _sfnt_tables(raw, face_offsets[face_index], f"{path.name}[{face_index}]")
        names = _font_names(raw, tables, f"{path.name}[{face_index}]")
        wanted = (
            {int(codepoint) for codepoint in required_codepoints}
            if required_codepoints is not None
            else set(range(0xAC00, 0xD7A4))
        )
        require(all(0 <= codepoint <= 0x10FFFF for codepoint in wanted), "확인할 Unicode 코드포인트가 잘못됐습니다")
        lookups = _unicode_cmap_lookups(raw, tables, f"{path.name}[{face_index}]")
        supported = frozenset(codepoint for codepoint in wanted if any(lookup(codepoint) != 0 for lookup in lookups))
        return FontFace(
            path=path,
            face_index=face_index,
            face_count=face_count,
            sha256=sha256_bytes(raw),
            size=len(raw),
            raw=raw,
            family=names.get(1, ""),
            subfamily=names.get(2, ""),
            full_name=names.get(4, ""),
            postscript_name=names.get(6, ""),
            codepoints=supported,
        )
    except FontBuildError:
        raise
    except Exception as exc:
        raise FontBuildError(f"지원되는 TTF/OTF/TTC/OTC 글꼴을 읽지 못했습니다: {path.name}: {exc}") from exc


@dataclass(frozen=True)
class FontPlan:
    mapping: tuple[MappingRow, ...]
    primary: FontFace
    fallback: FontFace | None
    primary_codepoints: frozenset[int]
    fallback_codepoints: frozenset[int]
    mode: str

    def metadata(self) -> dict[str, Any]:
        return {
            "schema": "homm2-generated-font-receipt-v1",
            "mode": self.mode,
            "renderer": RENDERER_ID,
            "normal_pixel_size": NORMAL_PIXEL_SIZE,
            "small_pixel_size": SMALL_PIXEL_SIZE,
            "normal_cell": {
                "width": NORMAL_CELL_WIDTH,
                "height": NORMAL_CELL_HEIGHT,
            },
            "small_cell": {
                "width": SMALL_CELL_WIDTH,
                "height": SMALL_CELL_HEIGHT,
            },
            "shadow_offset": [SHADOW_OFFSET_X, SHADOW_OFFSET_Y],
            "baseline_policy": BASELINE_POLICY,
            "fit_policy": FIT_POLICY,
            "crop_policy": CROP_POLICY,
            "shadow_policy": SHADOW_POLICY,
            "mapping_glyph_count": len(self.mapping),
            "first_index": KOREAN_FIRST_INDEX,
            "last_index": KOREAN_LAST_INDEX,
            "blank_legacy_sprite_index": AT_SIGN_SPRITE_INDEX,
            "primary_glyph_count": len(self.primary_codepoints),
            "fallback_glyph_count": len(self.fallback_codepoints),
            "primary": self.primary.public_metadata(),
            "fallback": self.fallback.public_metadata() if self.fallback else None,
        }


def make_font_plan(
    mapping_path: Path,
    primary_path: Path,
    *,
    primary_face_index: int = 0,
    fallback_path: Path | None = None,
    fallback_face_index: int = 0,
    mode: str,
) -> FontPlan:
    require(mode in {"default", "custom"}, f"글꼴 선택 모드가 잘못됐습니다: {mode}")
    mapping = parse_mapping(mapping_path)
    required = {row.codepoint for row in mapping}
    primary = inspect_font(primary_path, primary_face_index, required)
    primary_codepoints = frozenset(required & primary.codepoints)
    missing = required - primary_codepoints

    fallback: FontFace | None = None
    fallback_codepoints: frozenset[int] = frozenset()
    if missing and fallback_path is not None:
        fallback = inspect_font(fallback_path, fallback_face_index, missing)
        fallback_codepoints = frozenset(missing & fallback.codepoints)
        missing -= fallback_codepoints
    require(
        not missing,
        "선택 글꼴과 기본 대체 글꼴에 없는 문자가 있습니다: "
        + " ".join(f"U+{codepoint:04X}" for codepoint in sorted(missing)[:20]),
    )
    return FontPlan(mapping, primary, fallback, primary_codepoints, fallback_codepoints, mode)


@dataclass(frozen=True)
class Sprite:
    offset_x: int
    offset_y: int
    width: int
    height: int
    animation: int
    payload: bytes


@dataclass(frozen=True)
class _DecodedSprite:
    offset_x: int
    offset_y: int
    width: int
    height: int
    animation: int
    pixels: bytes
    transform: bytes


def _encode_sprite_data(width: int, height: int, pixels: bytes, transform: bytes) -> bytes:
    require(width > 0 and height > 0, "글리프 크기가 0입니다")
    require(len(pixels) == width * height == len(transform), "글리프 버퍼 크기가 잘못됐습니다")
    output = bytearray()
    for y in range(height):
        x = 0
        while x < width:
            position = y * width + x
            flag = transform[position]
            limit = 127 if flag == 0 else 63 if flag == 1 else 255
            run = 0
            while x + run < width and run < limit:
                if transform[y * width + x + run] != flag:
                    break
                run += 1
            require(run > 0, "글리프 RLE가 진행되지 않습니다")
            if flag == 0:
                output.append(run)
                start = y * width + x
                output.extend(pixels[start : start + run])
            elif flag == 1:
                output.append(0x80 + run)
            else:
                require(2 <= flag <= 15, f"지원하지 않는 ICN transform입니다: {flag}")
                tag = 0x40 | ((flag - 2) << 2)
                if run <= 3:
                    output.extend((0xC0, tag | run))
                else:
                    output.extend((0xC0, tag, run))
            x += run
        output.append(0)
    output.append(0x80)
    return bytes(output)


def _decode_sprite(sprite: Sprite, *, label: str) -> _DecodedSprite:
    pixels = bytearray(sprite.width * sprite.height)
    transform = bytearray([1]) * (sprite.width * sprite.height)
    position = 0
    row = 0
    x = 0
    monochrome = bool(sprite.animation & 0x20)
    ended = False

    def take() -> int:
        nonlocal position
        require(position < len(sprite.payload), f"ICN 명령이 잘렸습니다: {label}")
        value = sprite.payload[position]
        position += 1
        return value

    def put(target: bytearray, value: bytes | int, count: int) -> None:
        nonlocal x
        require(0 <= row < sprite.height and x + count <= sprite.width, f"ICN run이 스프라이트를 넘었습니다: {label}")
        start = row * sprite.width + x
        target[start : start + count] = bytes((value,)) * count if isinstance(value, int) else value

    while position < len(sprite.payload):
        command = take()
        if command == 0x80:
            ended = True
            break
        if command == 0:
            row += 1
            x = 0
            require(row <= sprite.height, f"ICN 행이 너무 많습니다: {label}")
            continue
        require(row < sprite.height, f"ICN이 마지막 행 뒤에 기록됩니다: {label}")
        if monochrome:
            if command < 0x80:
                put(transform, 0, command)
                x += command
            else:
                x += command - 0x80
            require(x <= sprite.width, f"ICN monochrome skip이 넘쳤습니다: {label}")
        elif command < 0x80:
            count = command
            require(position + count <= len(sprite.payload), f"ICN literal이 잘렸습니다: {label}")
            literal = sprite.payload[position : position + count]
            position += count
            put(pixels, literal, count)
            put(transform, 0, count)
            x += count
        elif command < 0xC0:
            x += command - 0x80
            require(x <= sprite.width, f"ICN skip이 넘쳤습니다: {label}")
        elif command == 0xC0:
            tag = take()
            count = tag & 3 or take()
            transform_type = ((tag & 0x3C) >> 2) + 2
            if tag & 0x40 and transform_type < 16:
                put(transform, transform_type, count)
            x += count
            require(x <= sprite.width, f"ICN transform이 넘쳤습니다: {label}")
        else:
            count = take() if command == 0xC1 else command - 0xC0
            color = take()
            put(pixels, color, count)
            put(transform, 0, count)
            x += count
    require(ended and position == len(sprite.payload), f"ICN 종료 marker가 잘못됐습니다: {label}")
    return _DecodedSprite(
        sprite.offset_x,
        sprite.offset_y,
        sprite.width,
        sprite.height,
        sprite.animation,
        bytes(pixels),
        bytes(transform),
    )


def _validate_sprite_payload(sprite: Sprite) -> None:
    position = 0
    for _ in range(sprite.height):
        x = 0
        while True:
            require(position < len(sprite.payload), "글리프 RLE 행이 잘렸습니다")
            command = sprite.payload[position]
            position += 1
            if command == 0:
                break
            require(command != 0x80, "글리프 RLE 종료가 행 안에 있습니다")
            if command > 0x80:
                x += command - 0x80
            else:
                require(position + command <= len(sprite.payload), "글리프 RLE literal이 잘렸습니다")
                position += command
                x += command
            require(x <= sprite.width, "글리프 RLE가 행 너비를 넘었습니다")
        require(x == sprite.width, "글리프 RLE 행 너비가 맞지 않습니다")
    require(position + 1 == len(sprite.payload) and sprite.payload[position] == 0x80, "글리프 RLE 끝이 잘못됐습니다")


@dataclass(frozen=True)
class _GlyphMask:
    character: str
    left: int
    top: int
    mask: Image.Image

    @property
    def right(self) -> int:
        return self.left + self.mask.width

    @property
    def bottom(self) -> int:
        return self.top + self.mask.height


@dataclass(frozen=True)
class _FaceLayout:
    requested_pixel_size: int
    resolved_pixel_size: int
    cell_width: int
    cell_height: int
    origin_x: int
    baseline_y: int
    union_left: int
    union_top: int
    union_right: int
    union_bottom: int
    glyphs: Mapping[int, _GlyphMask]

    def shadow_edge_clip_count(self) -> int:
        clipped = 0
        for glyph in self.glyphs.values():
            occupied_width = min(self.cell_width, glyph.mask.width + SHADOW_OFFSET_X)
            offset_x = (self.cell_width - occupied_width) // 2
            width = self.cell_width - offset_x
            offset_y = self.baseline_y + glyph.top
            height = self.cell_height - offset_y
            for y in range(glyph.mask.height):
                for x in range(glyph.mask.width):
                    if not glyph.mask.getpixel((x, y)):
                        continue
                    if x + SHADOW_OFFSET_X >= width or y + SHADOW_OFFSET_Y >= height:
                        clipped += 1
        return clipped

    def metadata(self) -> dict[str, Any]:
        return {
            "requested_pixel_size": self.requested_pixel_size,
            "resolved_pixel_size": self.resolved_pixel_size,
            "cell_width": self.cell_width,
            "cell_height": self.cell_height,
            "origin_x": self.origin_x,
            "baseline_y": self.baseline_y,
            "ink_union": [self.union_left, self.union_top, self.union_right, self.union_bottom],
            "glyph_count": len(self.glyphs),
            "foreground_clip_count": 0,
            "shadow_edge_clip_count": self.shadow_edge_clip_count(),
        }


def _rasterize_glyph(font: ImageFont.FreeTypeFont, character: str) -> _GlyphMask:
    bbox = font.getbbox(character, anchor="ls")
    require(bbox is not None, f"빈 글리프입니다: U+{ord(character):04X}")
    left, top, right, bottom = (int(value) for value in bbox)
    require(left < right and top < bottom, f"글리프 bbox가 비었습니다: U+{ord(character):04X}")
    padding = 4
    anchor_x = padding - left
    anchor_y = padding - top
    image = Image.new("1", (right - left + padding * 2, bottom - top + padding * 2), 0)
    draw = ImageDraw.Draw(image)
    draw.text((anchor_x, anchor_y), character, font=font, fill=1, anchor="ls")
    crop = image.getbbox()
    require(crop is not None, f"렌더링 결과가 빈 글리프입니다: U+{ord(character):04X}")
    mask = image.crop(crop)
    actual_left = crop[0] - anchor_x
    actual_top = crop[1] - anchor_y
    return _GlyphMask(character, actual_left, actual_top, mask)


def _load_freetype(face: FontFace, pixel_size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(
        io.BytesIO(face.raw),
        pixel_size,
        index=face.face_index,
        layout_engine=ImageFont.Layout.BASIC,
    )


def _build_face_layout(
    face: FontFace,
    characters: Mapping[int, str],
    *,
    requested_pixel_size: int,
    cell_width: int,
    cell_height: int,
) -> _FaceLayout | None:
    if not characters:
        return None
    require(len(set(characters.values())) == len(characters), "face 글리프 문자가 중복됐습니다")
    require(
        requested_pixel_size >= MINIMUM_PIXEL_SIZE
        and cell_width > SHADOW_OFFSET_X
        and cell_height > SHADOW_OFFSET_Y,
        "글리프 논리 셀 설정이 잘못됐습니다",
    )

    pixel_size = requested_pixel_size
    while True:
        font = _load_freetype(face, pixel_size)
        glyphs = {codepoint: _rasterize_glyph(font, character) for codepoint, character in characters.items()}
        union_left = min(glyph.left for glyph in glyphs.values())
        union_top = min(glyph.top for glyph in glyphs.values())
        union_right = max(glyph.right for glyph in glyphs.values())
        union_bottom = max(glyph.bottom for glyph in glyphs.values())
        maximum_width = max(glyph.mask.width for glyph in glyphs.values())
        maximum_height = max(glyph.mask.height for glyph in glyphs.values())
        union_height = union_bottom - union_top
        if (
            maximum_width <= cell_width
            and maximum_height <= cell_height
            and union_height <= cell_height
        ):
            origin_x = cell_width // 2
            baseline_y = -union_top
            return _FaceLayout(
                requested_pixel_size,
                pixel_size,
                cell_width,
                cell_height,
                origin_x,
                baseline_y,
                union_left,
                union_top,
                union_right,
                union_bottom,
                glyphs,
            )

        require(
            pixel_size > MINIMUM_PIXEL_SIZE,
            f"글리프 face를 {cell_width}x{cell_height} 논리 셀에 맞출 수 없습니다: {face.path.name}",
        )
        pixel_size -= 1


def _build_common_face_layouts(
    faces: Mapping[str, tuple[FontFace, Mapping[int, str]]],
    *,
    requested_pixel_size: int,
    cell_width: int,
    cell_height: int,
) -> dict[str, _FaceLayout]:
    """Resolve every active face at one size and one typographic baseline."""

    active = {
        name: (face, characters)
        for name, (face, characters) in faces.items()
        if characters
    }
    require(active, "렌더링할 face 글리프가 없습니다")

    pixel_size = requested_pixel_size
    while True:
        layouts = {
            name: _build_face_layout(
                face,
                characters,
                requested_pixel_size=pixel_size,
                cell_width=cell_width,
                cell_height=cell_height,
            )
            for name, (face, characters) in active.items()
        }
        require(all(layout is not None for layout in layouts.values()), "활성 face 레이아웃이 비었습니다")
        concrete = {name: layout for name, layout in layouts.items() if layout is not None}

        # A face may need a smaller size for its own width or ink union.  Rebuild
        # every other face at that same size so primary and fallback glyphs do
        # not change scale in the middle of one line.
        resolved_pixel_size = min(layout.resolved_pixel_size for layout in concrete.values())
        if resolved_pixel_size < pixel_size:
            pixel_size = resolved_pixel_size
            continue

        union_left = min(layout.union_left for layout in concrete.values())
        union_top = min(layout.union_top for layout in concrete.values())
        union_right = max(layout.union_right for layout in concrete.values())
        union_bottom = max(layout.union_bottom for layout in concrete.values())
        if union_bottom - union_top <= cell_height:
            baseline_y = -union_top
            return {
                name: _FaceLayout(
                    requested_pixel_size,
                    pixel_size,
                    cell_width,
                    cell_height,
                    layout.origin_x,
                    baseline_y,
                    union_left,
                    union_top,
                    union_right,
                    union_bottom,
                    layout.glyphs,
                )
                for name, layout in concrete.items()
            }

        require(
            pixel_size > MINIMUM_PIXEL_SIZE,
            f"여러 글꼴 face를 {cell_width}x{cell_height} 공통 기준선에 맞출 수 없습니다",
        )
        pixel_size -= 1


def _render_sprite(layout: _FaceLayout, codepoint: int) -> Sprite:
    glyph = layout.glyphs[codepoint]
    occupied_width = min(layout.cell_width, glyph.mask.width + SHADOW_OFFSET_X)
    offset_x = (layout.cell_width - occupied_width) // 2
    offset_y = layout.baseline_y + glyph.top
    width = layout.cell_width - offset_x
    height = layout.cell_height - offset_y
    require(
        0 <= offset_x < layout.cell_width
        and 0 <= offset_y < layout.cell_height
        and width >= glyph.mask.width
        and height >= glyph.mask.height
        and offset_y + height <= layout.cell_height,
        f"글리프가 논리 셀을 넘었습니다: U+{codepoint:04X}",
    )
    pixels = bytearray(width * height)
    transform = bytearray([1]) * (width * height)

    points = [
        (x, y)
        for y in range(glyph.mask.height)
        for x in range(glyph.mask.width)
        if glyph.mask.getpixel((x, y))
    ]
    require(points, f"렌더링 결과에 점이 없습니다: U+{codepoint:04X}")
    for x, y in points:
        shadow_x = x + SHADOW_OFFSET_X
        shadow_y = y + SHADOW_OFFSET_Y
        if shadow_x < width and shadow_y < height:
            index = shadow_y * width + shadow_x
            pixels[index] = SHADOW_PALETTE_INDEX
            transform[index] = 0
    for x, y in points:
        index = y * width + x
        pixels[index] = FOREGROUND_PALETTE_INDEX
        transform[index] = 0

    sprite = Sprite(offset_x, offset_y, width, height, 0, _encode_sprite_data(width, height, bytes(pixels), bytes(transform)))
    _validate_sprite_payload(sprite)
    return sprite


@dataclass(frozen=True)
class RenderedFont:
    normal: tuple[Sprite, ...]
    small: tuple[Sprite, ...]
    metadata: dict[str, Any]
    mapping: tuple[MappingRow, ...] = ()


def render_font(plan: FontPlan) -> RenderedFont:
    try:
        primary_characters = {
            row.codepoint: row.character for row in plan.mapping if row.codepoint in plan.primary_codepoints
        }
        fallback_characters = {
            row.codepoint: row.character for row in plan.mapping if row.codepoint in plan.fallback_codepoints
        }
        faces: dict[str, tuple[FontFace, Mapping[int, str]]] = {
            "primary": (plan.primary, primary_characters),
        }
        if plan.fallback is not None:
            faces["fallback"] = (plan.fallback, fallback_characters)
        normal_layouts = _build_common_face_layouts(
            faces,
            requested_pixel_size=NORMAL_PIXEL_SIZE,
            cell_width=NORMAL_CELL_WIDTH,
            cell_height=NORMAL_CELL_HEIGHT,
        )
        small_layouts = _build_common_face_layouts(
            faces,
            requested_pixel_size=SMALL_PIXEL_SIZE,
            cell_width=SMALL_CELL_WIDTH,
            cell_height=SMALL_CELL_HEIGHT,
        )
        primary_normal = normal_layouts.get("primary")
        primary_small = small_layouts.get("primary")
        fallback_normal = normal_layouts.get("fallback")
        fallback_small = small_layouts.get("fallback")
    except FontBuildError:
        raise
    except Exception as exc:
        raise FontBuildError(f"FreeType으로 글꼴을 열지 못했습니다: {exc}") from exc

    normal: list[Sprite] = []
    small: list[Sprite] = []
    for row in plan.mapping:
        use_primary = row.codepoint in plan.primary_codepoints
        normal_font = primary_normal if use_primary else fallback_normal
        small_font = primary_small if use_primary else fallback_small
        require(normal_font is not None and small_font is not None, f"대체 글꼴 선택 오류: U+{row.codepoint:04X}")
        normal.append(_render_sprite(normal_font, row.codepoint))
        small.append(_render_sprite(small_font, row.codepoint))
    require(len(normal) == len(small) == KOREAN_GLYPH_COUNT, "생성된 글리프 수가 맞지 않습니다")
    metadata = plan.metadata()
    metadata["resolved_faces"] = {
        "primary": {
            "normal": primary_normal.metadata() if primary_normal else None,
            "small": primary_small.metadata() if primary_small else None,
        },
        "fallback": {
            "normal": fallback_normal.metadata() if fallback_normal else None,
            "small": fallback_small.metadata() if fallback_small else None,
        }
        if plan.fallback is not None
        else None,
    }
    return RenderedFont(tuple(normal), tuple(small), metadata, tuple(plan.mapping))


@dataclass(frozen=True)
class IcnArchive:
    sprites: tuple[Sprite, ...]


def parse_icn(raw: bytes, *, label: str) -> IcnArchive:
    require(len(raw) >= ICN_HEADER_SIZE, f"ICN이 너무 짧습니다: {label}")
    count, total_size = struct.unpack_from("<HI", raw, 0)
    require(total_size + ICN_HEADER_SIZE == len(raw), f"ICN 크기 필드가 맞지 않습니다: {label}")
    headers_size = count * ICN_SPRITE_HEADER_SIZE
    require(ICN_HEADER_SIZE + headers_size <= len(raw), f"ICN 헤더가 잘렸습니다: {label}")
    offsets: list[int] = []
    headers: list[tuple[int, int, int, int, int]] = []
    for index in range(count):
        p = ICN_HEADER_SIZE + index * ICN_SPRITE_HEADER_SIZE
        offset_x, offset_y, width, height, animation, data_offset = struct.unpack_from("<hhHHBI", raw, p)
        require(headers_size <= data_offset < total_size, f"ICN 데이터 offset이 잘못됐습니다: {label}:{index}")
        require(not offsets or data_offset >= offsets[-1], f"ICN 데이터 offset 순서가 잘못됐습니다: {label}:{index}")
        offsets.append(data_offset)
        headers.append((offset_x, offset_y, width, height, animation))
    if count:
        require(offsets[0] == headers_size, f"ICN 첫 데이터 offset이 잘못됐습니다: {label}")
    sprites: list[Sprite] = []
    for index, data_offset in enumerate(offsets):
        data_end = offsets[index + 1] if index + 1 < count else total_size
        require(data_offset <= data_end <= total_size, f"ICN 데이터 범위가 잘못됐습니다: {label}:{index}")
        start = ICN_HEADER_SIZE + data_offset
        end = ICN_HEADER_SIZE + data_end
        sprites.append(Sprite(*headers[index], raw[start:end]))
    return IcnArchive(tuple(sprites))


def pack_icn(sprites: Sequence[Sprite]) -> bytes:
    require(0 < len(sprites) <= 0xFFFF, "ICN sprite 수가 범위를 벗어났습니다")
    offset = len(sprites) * ICN_SPRITE_HEADER_SIZE
    offsets: list[int] = []
    for sprite in sprites:
        require(0 <= sprite.width <= 0xFFFF and 0 <= sprite.height <= 0xFFFF, "ICN sprite 크기가 범위를 벗어났습니다")
        offsets.append(offset)
        offset += len(sprite.payload)
        require(offset <= 0xFFFFFFFF, "ICN 전체 크기가 범위를 벗어났습니다")
    output = bytearray(struct.pack("<HI", len(sprites), offset))
    for sprite, data_offset in zip(sprites, offsets):
        output.extend(
            struct.pack(
                "<hhHHBI",
                sprite.offset_x,
                sprite.offset_y,
                sprite.width,
                sprite.height,
                sprite.animation,
                data_offset,
            )
        )
    for sprite in sprites:
        output.extend(sprite.payload)
    return bytes(output)


def _localize_recruit_cost_label(
    source_raw: bytes,
    small_font_sprites: Sequence[Sprite],
    *,
    label: str,
    canonical_raster_identities: bool = True,
) -> bytes:
    """Render the approved Korean cost label into the pristine recruit background."""

    require(
        len(source_raw) == RECRUIT_COST_SOURCE_SIZE
        and sha256_bytes(source_raw) == RECRUIT_COST_SOURCE_SHA256,
        f"순정 {RECRUIT_COST_RESOURCE_NAME} identity가 다릅니다: {label}",
    )
    source = parse_icn(source_raw, label=f"{label}:source")
    require(len(source.sprites) == 2, f"{RECRUIT_COST_RESOURCE_NAME} sprite 수가 다릅니다: {label}")
    background_sprite = source.sprites[0]
    require(
        (
            background_sprite.offset_x,
            background_sprite.offset_y,
            background_sprite.width,
            background_sprite.height,
            background_sprite.animation,
        )
        == (16, 0, 321, 304, 0),
        f"{RECRUIT_COST_RESOURCE_NAME}:0 layout이 다릅니다: {label}",
    )
    require(
        "".join(character for character, _, _ in RECRUIT_COST_GLYPHS) == RECRUIT_COST_LABEL,
        "모집 비용 문구 glyph 계약이 다릅니다",
    )
    require(
        all(0 <= index < len(small_font_sprites) for _, index, _ in RECRUIT_COST_GLYPHS),
        "모집 비용 문구 glyph index가 글꼴 범위를 넘었습니다",
    )

    decoded_background = _decode_sprite(background_sprite, label=f"{label}:background")
    decoded_glyphs = tuple(
        _decode_sprite(small_font_sprites[index], label=f"{label}:glyph:{character}")
        for character, index, _ in RECRUIT_COST_GLYPHS
    )
    total_width = sum(glyph.width for glyph in decoded_glyphs) + len(decoded_glyphs) - 1
    maximum_height = max(glyph.height for glyph in decoded_glyphs)
    if canonical_raster_identities:
        require(
            (total_width, maximum_height) == RECRUIT_COST_GLYPH_BOX,
            f"모집 비용 문구 glyph 크기가 다릅니다: {label}: {(total_width, maximum_height)}",
        )

    x0, y0, width, height = RECRUIT_COST_ROI
    require(
        0 <= RECRUIT_COST_BACKGROUND_SAMPLE_X < x0
        and x0 + width <= decoded_background.width
        and y0 + height <= decoded_background.height,
        f"모집 비용 ROI가 배경 범위를 넘었습니다: {label}",
    )
    require(
        total_width <= width and maximum_height <= height,
        f"모집 비용 문구가 ROI에 맞지 않습니다: {label}: {(total_width, maximum_height)}",
    )
    pixels = bytearray(decoded_background.pixels)
    transform = bytearray(decoded_background.transform)
    for y in range(y0, y0 + height):
        sample = y * decoded_background.width + RECRUIT_COST_BACKGROUND_SAMPLE_X
        for x in range(x0, x0 + width):
            destination = y * decoded_background.width + x
            pixels[destination] = decoded_background.pixels[sample]
            transform[destination] = decoded_background.transform[sample]

    cursor = x0 + (width - total_width) // 2
    logical_top = y0 + (height - SMALL_CELL_HEIGHT) // 2 + RECRUIT_COST_TOP_ADJUST
    ink: list[tuple[int, int]] = []
    for (character, _, korean), glyph in zip(RECRUIT_COST_GLYPHS, decoded_glyphs):
        if character != " ":
            for offset, flag in enumerate(glyph.transform):
                if flag:
                    continue
                x = cursor + glyph.offset_x + offset % glyph.width
                y = logical_top + glyph.offset_y + offset // glyph.width
                require(
                    x0 <= x < x0 + width and y0 <= y < y0 + height,
                    f"모집 비용 문구가 ROI를 넘었습니다: {label}:{character}",
                )
                palette = glyph.pixels[offset]
                if korean:
                    require(
                        palette in {FOREGROUND_PALETTE_INDEX, SHADOW_PALETTE_INDEX},
                        f"한글 glyph palette가 다릅니다: {label}:{character}:{palette}",
                    )
                destination = y * decoded_background.width + x
                pixels[destination] = (
                    RECRUIT_COST_FOREGROUND_PALETTE_INDEX
                    if palette == FOREGROUND_PALETTE_INDEX
                    else RECRUIT_COST_SHADOW_PALETTE_INDEX
                )
                transform[destination] = 0
                ink.append((x, y))
        cursor += glyph.width + 1

    require(ink, f"모집 비용 문구 ink가 비었습니다: {label}")
    ink_bbox = (
        min(x for x, _ in ink),
        min(y for _, y in ink),
        max(x for x, _ in ink) + 1,
        max(y for _, y in ink) + 1,
    )
    if canonical_raster_identities:
        require(
            ink_bbox == RECRUIT_COST_INK_BBOX and len(ink) == RECRUIT_COST_INK_PIXEL_COUNT,
            f"모집 비용 문구 ink 계약이 다릅니다: {label}: {ink_bbox}/{len(ink)}",
        )

    localized_background = Sprite(
        decoded_background.offset_x,
        decoded_background.offset_y,
        decoded_background.width,
        decoded_background.height,
        decoded_background.animation,
        _encode_sprite_data(
            decoded_background.width,
            decoded_background.height,
            bytes(pixels),
            bytes(transform),
        ),
    )
    result = pack_icn((localized_background, *source.sprites[1:]))
    if canonical_raster_identities:
        require(
            len(result) == RECRUIT_COST_OUTPUT_SIZE and sha256_bytes(result) == RECRUIT_COST_OUTPUT_SHA256,
            f"생성된 {RECRUIT_COST_RESOURCE_NAME} identity가 다릅니다: {label}",
        )

    candidate = parse_icn(result, label=f"{label}:candidate")
    require(candidate.sprites[1:] == source.sprites[1:], f"{RECRUIT_COST_RESOURCE_NAME}:1이 바뀌었습니다: {label}")
    decoded_candidate = _decode_sprite(candidate.sprites[0], label=f"{label}:candidate-background")
    for y in range(decoded_background.height):
        for x in range(decoded_background.width):
            if x0 <= x < x0 + width and y0 <= y < y0 + height:
                continue
            offset = y * decoded_background.width + x
            require(
                decoded_candidate.pixels[offset] == decoded_background.pixels[offset]
                and decoded_candidate.transform[offset] == decoded_background.transform[offset],
                f"{RECRUIT_COST_RESOURCE_NAME}:0 ROI 밖 픽셀이 바뀌었습니다: {label}:{x},{y}",
            )
    return result


def _image_ui_glyph_index(character: str, mapping: Sequence[MappingRow]) -> int:
    codepoint = ord(character)
    if 0x20 <= codepoint <= 0x7E:
        return codepoint - 0x20
    matches = [row.index for row in mapping if row.character == character]
    require(len(matches) == 1, f"이미지 UI 문자가 매핑에 없거나 중복됐습니다: {character!r}")
    return matches[0]


def _require_outside_roi_exact(
    before: _DecodedSprite,
    after: _DecodedSprite,
    roi: tuple[int, int, int, int],
    *,
    label: str,
) -> None:
    require(
        (before.offset_x, before.offset_y, before.width, before.height, before.animation)
        == (after.offset_x, after.offset_y, after.width, after.height, after.animation),
        f"이미지 UI sprite layout이 바뀌었습니다: {label}",
    )
    x0, y0, width, height = roi
    for y in range(before.height):
        for x in range(before.width):
            if x0 <= x < x0 + width and y0 <= y < y0 + height:
                continue
            offset = y * before.width + x
            require(
                before.pixels[offset] == after.pixels[offset]
                and before.transform[offset] == after.transform[offset],
                f"이미지 UI ROI 밖 픽셀이 바뀌었습니다: {label}:{x},{y}",
            )


def _require_outside_rois_exact(
    before: _DecodedSprite,
    after: _DecodedSprite,
    rois: Sequence[tuple[int, int, int, int]],
    *,
    label: str,
) -> None:
    require(
        (before.offset_x, before.offset_y, before.width, before.height, before.animation)
        == (after.offset_x, after.offset_y, after.width, after.height, after.animation),
        f"이미지 UI sprite layout이 바뀌었습니다: {label}",
    )
    for y in range(before.height):
        for x in range(before.width):
            if any(rx <= x < rx + rw and ry <= y < ry + rh for rx, ry, rw, rh in rois):
                continue
            offset = y * before.width + x
            require(
                before.pixels[offset] == after.pixels[offset]
                and before.transform[offset] == after.transform[offset],
                f"이미지 UI ROI 밖 픽셀이 바뀌었습니다: {label}:{x},{y}",
            )


def _localize_image_ui_text_resource(
    source_raw: bytes,
    targets: Sequence[Mapping[str, Any]],
    normal_font_sprites: Sequence[Sprite],
    mapping: Sequence[MappingRow],
    background_donors: Mapping[tuple[str, int], _DecodedSprite],
    *,
    label: str,
) -> bytes:
    source = parse_icn(source_raw, label=f"{label}:source")
    sprites = list(source.sprites)
    changed_indices: set[int] = set()
    for target in targets:
        sprite_index = int(target["sprite"])
        require(0 <= sprite_index < len(sprites), f"이미지 UI sprite index가 범위를 넘었습니다: {label}:{sprite_index}")
        require(sprite_index not in changed_indices, f"이미지 UI sprite target이 중복됐습니다: {label}:{sprite_index}")
        changed_indices.add(sprite_index)
        base_sprite = source.sprites[sprite_index]
        decoded = _decode_sprite(base_sprite, label=f"{label}:{sprite_index}:before")
        x0, y0, width, height = (int(value) for value in target["roi"])
        require(
            x0 >= 0 and y0 >= 0 and x0 + width <= decoded.width and y0 + height <= decoded.height,
            f"이미지 UI ROI가 sprite 범위를 넘었습니다: {label}:{sprite_index}",
        )
        layout_x, layout_y, layout_width, layout_height = (
            int(value) for value in target.get("layout_roi", target["roi"])
        )
        require(
            x0 <= layout_x and y0 <= layout_y
            and layout_x + layout_width <= x0 + width
            and layout_y + layout_height <= y0 + height,
            f"이미지 UI layout ROI가 editable ROI를 넘었습니다: {label}:{sprite_index}",
        )
        clear_x, clear_y, clear_width, clear_height = (
            int(value) for value in target.get("clear_roi", target["roi"])
        )
        require(
            x0 <= clear_x and y0 <= clear_y
            and clear_x + clear_width <= x0 + width
            and clear_y + clear_height <= y0 + height,
            f"이미지 UI clear ROI가 editable ROI를 넘었습니다: {label}:{sprite_index}",
        )
        pixels = bytearray(decoded.pixels)
        transform = bytearray(decoded.transform)
        background = int(target["background"])
        clear_mode = str(target.get("clear_mode", "solid"))
        require(
            clear_mode in {"solid", "non_background", "palettes", "row_sample"},
            f"이미지 UI clear mode가 잘못됐습니다: {label}:{sprite_index}:{clear_mode}",
        )
        clear_palettes = {int(value) for value in target.get("clear_palettes", ())}
        require(
            (clear_mode == "palettes") == bool(clear_palettes),
            f"이미지 UI clear palette 계약이 잘못됐습니다: {label}:{sprite_index}",
        )
        background_sample_x = int(target.get("background_sample_x", -1))
        require(
            (clear_mode == "row_sample") == (0 <= background_sample_x < decoded.width),
            f"이미지 UI row sample 계약이 잘못됐습니다: {label}:{sprite_index}",
        )
        donor_fields = ("donor_resource", "donor_sprite", "donor_clear_roi")
        donor_field_count = sum(field in target for field in donor_fields)
        require(donor_field_count in {0, len(donor_fields)}, f"이미지 UI donor 지정이 불완전합니다: {label}:{sprite_index}")
        if donor_field_count:
            donor_key = (str(target["donor_resource"]), int(target["donor_sprite"]))
            require(donor_key in background_donors, f"이미지 UI donor가 없습니다: {label}:{sprite_index}:{donor_key}")
            donor = background_donors[donor_key]
            require(
                (donor.width, donor.height) == (decoded.width, decoded.height),
                f"이미지 UI donor layout이 다릅니다: {label}:{sprite_index}:{donor_key}",
            )
            donor_pixels = bytearray(donor.pixels)
            donor_transform = bytearray(donor.transform)
            donor_x, donor_y, donor_width, donor_height = (
                int(value) for value in target["donor_clear_roi"]
            )
            require(
                donor_x >= 0 and donor_y >= 0
                and donor_x + donor_width <= donor.width
                and donor_y + donor_height <= donor.height,
                f"이미지 UI donor clear ROI가 범위를 넘었습니다: {label}:{sprite_index}:{donor_key}",
            )
            donor_clear_mode = str(target.get("donor_clear_mode", "solid"))
            require(
                donor_clear_mode in {"solid", "none", "palettes"},
                f"이미지 UI donor clear mode가 잘못됐습니다: {label}:{sprite_index}:{donor_clear_mode}",
            )
            donor_clear_palettes = {int(value) for value in target.get("donor_clear_palettes", ())}
            require(
                (donor_clear_mode == "palettes") == bool(donor_clear_palettes),
                f"이미지 UI donor clear palette 계약이 잘못됐습니다: {label}:{sprite_index}",
            )
            if donor_clear_mode != "none":
                for y in range(donor_y, donor_y + donor_height):
                    for x in range(donor_x, donor_x + donor_width):
                        destination = y * donor.width + x
                        if (
                            donor_clear_mode == "palettes"
                            and (
                                donor_transform[destination] != 0
                                or donor_pixels[destination] not in donor_clear_palettes
                            )
                        ):
                            continue
                        donor_pixels[destination] = background
                        donor_transform[destination] = 0
            for y in range(clear_y, clear_y + clear_height):
                source_start = y * donor.width + clear_x
                destination_start = y * decoded.width + clear_x
                pixels[destination_start : destination_start + clear_width] = donor_pixels[
                    source_start : source_start + clear_width
                ]
                transform[destination_start : destination_start + clear_width] = donor_transform[
                    source_start : source_start + clear_width
                ]
        else:
            for y in range(clear_y, clear_y + clear_height):
                for x in range(clear_x, clear_x + clear_width):
                    destination = y * decoded.width + x
                    if (
                        clear_mode == "non_background"
                        and pixels[destination] == background
                        and transform[destination] == 0
                    ):
                        continue
                    if (
                        clear_mode == "palettes"
                        and (
                            transform[destination] != 0
                            or pixels[destination] not in clear_palettes
                        )
                    ):
                        continue
                    if clear_mode == "row_sample":
                        sample = y * decoded.width + background_sample_x
                        pixels[destination] = decoded.pixels[sample]
                        transform[destination] = decoded.transform[sample]
                    else:
                        pixels[destination] = background
                        transform[destination] = 0

        text = str(target["text"])
        text_lines = text.split("\n")
        require(text_lines and all(text_lines), f"이미지 UI 빈 text line이 있습니다: {label}:{sprite_index}")
        interglyph = 1
        line_layouts: list[dict[str, Any]] = []
        for line in text_lines:
            glyph_indices = tuple(_image_ui_glyph_index(character, mapping) for character in line)
            require(
                all(0 <= index < len(normal_font_sprites) for index in glyph_indices),
                f"이미지 UI glyph index가 글꼴 범위를 넘었습니다: {label}:{sprite_index}",
            )
            glyphs = tuple(
                _decode_sprite(normal_font_sprites[index], label=f"{label}:{sprite_index}:glyph:{character}")
                for character, index in zip(line, glyph_indices)
            )
            glyph_origins: list[int] = []
            logical_cursor = 0
            composite_ink: list[tuple[int, int]] = []
            for character, glyph in zip(line, glyphs):
                glyph_origins.append(logical_cursor)
                if character != " ":
                    for offset, flag in enumerate(glyph.transform):
                        if flag:
                            continue
                        composite_ink.append(
                            (
                                logical_cursor + glyph.offset_x + offset % glyph.width,
                                glyph.offset_y + offset // glyph.width,
                            )
                        )
                logical_cursor += glyph.width + interglyph
            require(composite_ink, f"이미지 UI glyph ink가 비었습니다: {label}:{sprite_index}:{line!r}")
            ink_left = min(x for x, _ in composite_ink)
            ink_top = min(y for _, y in composite_ink)
            ink_right = max(x for x, _ in composite_ink) + 1
            ink_bottom = max(y for _, y in composite_ink) + 1
            line_layouts.append(
                {
                    "text": line,
                    "glyphs": glyphs,
                    "glyph_origins": tuple(glyph_origins),
                    "ink_left": ink_left,
                    "ink_top": ink_top,
                    "ink_width": ink_right - ink_left,
                    "ink_height": ink_bottom - ink_top,
                }
            )
        pressed_dx, pressed_dy = (1, 1) if target["state"] == "pressed" else (0, 0)
        line_gap = int(target.get("line_gap", 1))
        require(line_gap >= 0, f"이미지 UI line gap이 음수입니다: {label}:{sprite_index}")
        block_height = sum(int(line["ink_height"]) for line in line_layouts) + line_gap * (len(line_layouts) - 1)
        require(
            block_height <= layout_height,
            f"이미지 UI 글자 높이가 layout ROI를 넘었습니다: {label}:{sprite_index}",
        )
        line_top = min(
            layout_y + (layout_height - block_height) // 2 + pressed_dy,
            layout_y + layout_height - block_height,
        )
        palette_key = f"{target['interface']}_{target['state']}"
        palette_map = IMAGE_UI_PALETTE_MAPS[palette_key]
        ink_count = 0
        for line in line_layouts:
            ink_width = int(line["ink_width"])
            require(
                ink_width <= layout_width,
                f"이미지 UI 글자 폭이 layout ROI를 넘었습니다: {label}:{sprite_index}",
            )
            ink_x = min(
                layout_x + (layout_width - ink_width) // 2 + pressed_dx,
                layout_x + layout_width - ink_width,
            )
            origin_x = ink_x - int(line["ink_left"])
            origin_y = line_top - int(line["ink_top"])
            for character, glyph, glyph_origin in zip(line["text"], line["glyphs"], line["glyph_origins"]):
                if character == " ":
                    continue
                opaque_palettes = {pixel for pixel, flag in zip(glyph.pixels, glyph.transform) if flag == 0}
                is_ascii = 0x20 <= ord(character) <= 0x7E
                if not is_ascii:
                    require(
                        opaque_palettes <= set(palette_map) and opaque_palettes,
                        f"이미지 UI glyph palette가 다릅니다: {label}:{sprite_index}:{character}",
                    )
                for offset, flag in enumerate(glyph.transform):
                    if flag:
                        continue
                    x = origin_x + glyph_origin + glyph.offset_x + offset % glyph.width
                    y = origin_y + glyph.offset_y + offset // glyph.width
                    require(
                        x0 <= x < x0 + width and y0 <= y < y0 + height,
                        f"이미지 UI 글자가 ROI를 넘었습니다: {label}:{sprite_index}:{character}",
                    )
                    mask_palette = (
                        glyph.pixels[offset]
                        if not is_ascii
                        else FOREGROUND_PALETTE_INDEX
                        if glyph.pixels[offset] <= 20
                        else SHADOW_PALETTE_INDEX
                    )
                    if bool(target.get("skip_shadow", False)) and mask_palette == SHADOW_PALETTE_INDEX:
                        continue
                    destination = y * decoded.width + x
                    pixels[destination] = palette_map[mask_palette]
                    transform[destination] = 0
                    ink_count += 1
            line_top += int(line["ink_height"]) + line_gap
        require(ink_count > 0, f"이미지 UI 렌더링 결과가 비었습니다: {label}:{sprite_index}")

        localized = Sprite(
            decoded.offset_x,
            decoded.offset_y,
            decoded.width,
            decoded.height,
            decoded.animation,
            _encode_sprite_data(decoded.width, decoded.height, bytes(pixels), bytes(transform)),
        )
        localized_decoded = _decode_sprite(localized, label=f"{label}:{sprite_index}:after")
        _require_outside_roi_exact(decoded, localized_decoded, (x0, y0, width, height), label=f"{label}:{sprite_index}")
        sprites[sprite_index] = localized

    result = pack_icn(tuple(sprites))
    candidate = parse_icn(result, label=f"{label}:candidate")
    for index, (before, after) in enumerate(zip(source.sprites, candidate.sprites)):
        if index not in changed_indices:
            require(after == before, f"이미지 UI non-target sprite가 바뀌었습니다: {label}:{index}")
    return result


def _localize_well_background_mirror(
    source_raw: bytes,
    localized_wellxtra_raw: bytes,
    *,
    label: str,
) -> bytes:
    spec = IMAGE_UI_WELL_MIRROR
    source = parse_icn(source_raw, label=f"{label}:source")
    mirror = parse_icn(localized_wellxtra_raw, label=f"{label}:mirror-source")
    target_index = int(spec["target_sprite"])
    mirror_index = int(spec["source_sprite"])
    require(target_index < len(source.sprites) and mirror_index < len(mirror.sprites), f"우물 mirror sprite가 없습니다: {label}")
    before = _decode_sprite(source.sprites[target_index], label=f"{label}:before")
    donor = _decode_sprite(mirror.sprites[mirror_index], label=f"{label}:donor")
    sx, sy, sw, sh = (int(value) for value in spec["source_roi"])
    tx, ty, tw, th = (int(value) for value in spec["target_roi"])
    require((sw, sh) == (tw, th), f"우물 mirror ROI 크기가 다릅니다: {label}")
    require(
        sx >= 0 and sy >= 0 and sx + sw <= donor.width and sy + sh <= donor.height
        and tx >= 0 and ty >= 0 and tx + tw <= before.width and ty + th <= before.height,
        f"우물 mirror ROI가 sprite 범위를 넘었습니다: {label}",
    )
    pixels = bytearray(before.pixels)
    transform = bytearray(before.transform)
    for row in range(sh):
        donor_start = (sy + row) * donor.width + sx
        target_start = (ty + row) * before.width + tx
        pixels[target_start : target_start + sw] = donor.pixels[donor_start : donor_start + sw]
        transform[target_start : target_start + sw] = donor.transform[donor_start : donor_start + sw]
    localized = Sprite(
        before.offset_x,
        before.offset_y,
        before.width,
        before.height,
        before.animation,
        _encode_sprite_data(before.width, before.height, bytes(pixels), bytes(transform)),
    )
    after = _decode_sprite(localized, label=f"{label}:after")
    _require_outside_roi_exact(before, after, (tx, ty, tw, th), label=label)
    sprites = list(source.sprites)
    sprites[target_index] = localized
    result = pack_icn(tuple(sprites))
    candidate = parse_icn(result, label=f"{label}:candidate")
    for index, (old, new) in enumerate(zip(source.sprites, candidate.sprites)):
        if index != target_index:
            require(new == old, f"우물 mirror non-target sprite가 바뀌었습니다: {label}:{index}")
    return result


def _localize_image_ui_resources(
    base: "AggArchive",
    normal_font_sprites: Sequence[Sprite],
    mapping: Sequence[MappingRow],
    *,
    label: str,
    canonical_raster_identities: bool = True,
) -> dict[str, bytes]:
    available = {entry.name.upper() for entry in base.entries}
    expected = set(IMAGE_UI_RESOURCE_SOURCE_IDENTITIES)
    require(
        set(IMAGE_UI_RESOURCE_OUTPUT_IDENTITIES) == expected,
        f"이미지 UI 출력 identity 집합이 source와 다릅니다: {label}",
    )
    target_keys = tuple(
        (str(target["resource"]).upper(), int(target["sprite"]))
        for target in IMAGE_UI_TEXT_TARGETS
    )
    require(len(target_keys) == 52 and len(set(target_keys)) == len(target_keys), f"이미지 UI text target 계약이 잘못됐습니다: {label}")
    require(all(resource != "HSBTNS.ICN" for resource, _ in target_keys), f"보존 대상 HSBTNS.ICN이 이미지 UI target에 들어갔습니다: {label}")
    mirror_source = str(IMAGE_UI_WELL_MIRROR["source_resource"]).upper()
    mirror_target = str(IMAGE_UI_WELL_MIRROR["target_resource"]).upper()
    require(
        {resource for resource, _ in target_keys} == expected - {mirror_target}
        and mirror_source in {resource for resource, _ in target_keys}
        and mirror_target in expected,
        f"이미지 UI text/mirror 리소스 계약이 잘못됐습니다: {label}",
    )
    present = available & expected
    if not present:
        return {}
    require(present == expected, f"이미지 UI 리소스 집합이 불완전합니다: {label}: {sorted(expected - present)}")
    require(mapping, f"이미지 UI 렌더링에 글자 매핑이 없습니다: {label}")

    source_payloads: dict[str, bytes] = {}
    for resource_name, source_identity in IMAGE_UI_RESOURCE_SOURCE_IDENTITIES.items():
        source_raw = base.get(resource_name).payload
        require(
            (len(source_raw), sha256_bytes(source_raw)) == source_identity,
            f"순정 이미지 UI 리소스 identity가 다릅니다: {label}:{resource_name}",
        )
        source_payloads[resource_name] = source_raw

    targets_by_resource: dict[str, list[Mapping[str, Any]]] = {}
    for target in IMAGE_UI_TEXT_TARGETS:
        targets_by_resource.setdefault(str(target["resource"]), []).append(target)
    background_donors: dict[tuple[str, int], _DecodedSprite] = {}
    for target in IMAGE_UI_TEXT_TARGETS:
        if "donor_resource" not in target:
            continue
        donor_resource = str(target["donor_resource"])
        donor_index = int(target["donor_sprite"])
        require(donor_resource in source_payloads, f"이미지 UI donor 리소스가 source 집합에 없습니다: {label}:{donor_resource}")
        donor_icn = parse_icn(source_payloads[donor_resource], label=f"{label}:donor:{donor_resource}")
        require(0 <= donor_index < len(donor_icn.sprites), f"이미지 UI donor index가 범위를 넘었습니다: {label}:{donor_resource}:{donor_index}")
        background_donors[(donor_resource, donor_index)] = _decode_sprite(
            donor_icn.sprites[donor_index],
            label=f"{label}:donor:{donor_resource}:{donor_index}",
        )
    replacements: dict[str, bytes] = {}
    for resource_name, targets in targets_by_resource.items():
        source_raw = source_payloads[resource_name]
        replacements[resource_name] = _localize_image_ui_text_resource(
            source_raw,
            targets,
            normal_font_sprites,
            mapping,
            background_donors,
            label=f"{label}:{resource_name}",
        )

    replacements[mirror_target] = _localize_well_background_mirror(
        source_payloads[mirror_target],
        replacements[mirror_source],
        label=f"{label}:{mirror_target}",
    )
    require(set(replacements) == expected, f"이미지 UI 교체 집합이 잘못됐습니다: {label}")
    if canonical_raster_identities:
        for resource_name, payload in replacements.items():
            require(
                (len(payload), sha256_bytes(payload)) == IMAGE_UI_RESOURCE_OUTPUT_IDENTITIES[resource_name],
                f"이미지 UI 출력 identity가 다릅니다: {label}:{resource_name}",
            )
    return replacements


def _localize_menu132_resources(
    base: "AggArchive",
    normal_font_sprites: Sequence[Sprite],
    mapping: Sequence[MappingRow],
    *,
    label: str,
    canonical_raster_identities: bool = True,
) -> dict[str, bytes]:
    expected = set(MENU132_RESOURCE_SOURCE_IDENTITIES)
    available = {entry.name.upper() for entry in base.entries}
    present = available & expected
    if not present:
        return {}
    require(present == expected, f"132x62 메뉴 버튼 리소스 집합이 불완전합니다: {label}: {sorted(expected - present)}")
    require(mapping, f"132x62 메뉴 버튼 렌더링에 글자 매핑이 없습니다: {label}")

    target_keys = tuple(
        (str(target["resource"]).upper(), int(target["sprite"]))
        for target in MENU132_TEXT_TARGETS
    )
    require(
        len(target_keys) == 70
        and len(set(target_keys)) == len(target_keys)
        and {resource for resource, _ in target_keys} == expected,
        f"132x62 메뉴 버튼 target 계약이 잘못됐습니다: {label}",
    )
    source_payloads: dict[str, bytes] = {}
    for resource_name, source_identity in MENU132_RESOURCE_SOURCE_IDENTITIES.items():
        source_raw = base.get(resource_name).payload
        require(
            (len(source_raw), sha256_bytes(source_raw)) == source_identity,
            f"순정 132x62 메뉴 버튼 identity가 다릅니다: {label}:{resource_name}",
        )
        source_payloads[resource_name] = source_raw

    donor_resource = "BTNCOM.ICN"
    donor_icn = parse_icn(source_payloads[donor_resource], label=f"{label}:menu132-donor")
    background_donors = {
        (donor_resource, donor_index): _decode_sprite(
            donor_icn.sprites[donor_index],
            label=f"{label}:menu132-donor:{donor_index}",
        )
        for donor_index in (0, 1)
    }
    targets_by_resource: dict[str, list[Mapping[str, Any]]] = {}
    for target in MENU132_TEXT_TARGETS:
        targets_by_resource.setdefault(str(target["resource"]), []).append(target)
    replacements = {
        resource_name: _localize_image_ui_text_resource(
            source_payloads[resource_name],
            targets,
            normal_font_sprites,
            mapping,
            background_donors,
            label=f"{label}:{resource_name}",
        )
        for resource_name, targets in targets_by_resource.items()
    }
    require(set(replacements) == expected, f"132x62 메뉴 버튼 교체 집합이 잘못됐습니다: {label}")
    require(
        set(MENU132_RESOURCE_OUTPUT_IDENTITIES) == expected,
        f"132x62 메뉴 버튼 출력 identity 집합이 source와 다릅니다: {label}",
    )
    if canonical_raster_identities:
        for resource_name, payload in replacements.items():
            require(
                (len(payload), sha256_bytes(payload)) == MENU132_RESOURCE_OUTPUT_IDENTITIES[resource_name],
                f"132x62 메뉴 버튼 출력 identity가 다릅니다: {label}:{resource_name}",
            )
    return replacements


def _localize_campaign_button_resources(
    base: "AggArchive",
    normal_font_sprites: Sequence[Sprite],
    mapping: Sequence[MappingRow],
    *,
    label: str,
    canonical_raster_identities: bool = True,
) -> dict[str, bytes]:
    expected = set(CAMPAIGN_BUTTON_RESOURCE_SOURCE_IDENTITIES)
    available = {entry.name.upper() for entry in base.entries}
    present = available & expected
    if not present:
        return {}
    require(
        frozenset(present) in CAMPAIGN_BUTTON_ARCHIVE_RESOURCE_SETS,
        f"캠페인 버튼 리소스 집합이 잘못됐습니다: {label}: {sorted(present)}",
    )
    require(mapping, f"캠페인 버튼 렌더링에 글자 매핑이 없습니다: {label}")
    require(
        set(CAMPAIGN_BUTTON_RESOURCE_OUTPUT_IDENTITIES) == expected,
        f"캠페인 버튼 출력 identity 집합이 source와 다릅니다: {label}",
    )

    targets = tuple(
        target
        for target in CAMPAIGN_BUTTON_TEXT_TARGETS
        if str(target["resource"]).upper() in present
    )
    target_keys = tuple((str(target["resource"]).upper(), int(target["sprite"])) for target in targets)
    require(
        len(target_keys) == len(present) * 8
        and len(set(target_keys)) == len(target_keys)
        and {resource for resource, _ in target_keys} == present,
        f"캠페인 버튼 target 계약이 잘못됐습니다: {label}",
    )

    source_payloads: dict[str, bytes] = {}
    for resource_name in sorted(present):
        source_raw = base.get(resource_name).payload
        require(
            (len(source_raw), sha256_bytes(source_raw))
            == CAMPAIGN_BUTTON_RESOURCE_SOURCE_IDENTITIES[resource_name],
            f"순정 캠페인 버튼 identity가 다릅니다: {label}:{resource_name}",
        )
        source_payloads[resource_name] = source_raw
    targets_by_resource: dict[str, list[Mapping[str, Any]]] = {}
    for target in targets:
        targets_by_resource.setdefault(str(target["resource"]), []).append(target)
    replacements = {
        resource_name: _localize_image_ui_text_resource(
            source_payloads[resource_name],
            resource_targets,
            normal_font_sprites,
            mapping,
            {},
            label=f"{label}:{resource_name}",
        )
        for resource_name, resource_targets in targets_by_resource.items()
    }
    require(set(replacements) == present, f"캠페인 버튼 교체 집합이 잘못됐습니다: {label}")
    if canonical_raster_identities:
        for resource_name, payload in replacements.items():
            require(
                (len(payload), sha256_bytes(payload))
                == CAMPAIGN_BUTTON_RESOURCE_OUTPUT_IDENTITIES[resource_name],
                f"캠페인 버튼 출력 identity가 다릅니다: {label}:{resource_name}",
            )
    return replacements


def _camp_progress_inside(x: int, y: int, roi: Sequence[int]) -> bool:
    x0, y0, width, height = (int(value) for value in roi)
    return x0 <= x < x0 + width and y0 <= y < y0 + height


def _camp_progress_seed_matches(palette_index: int, kind: str) -> bool:
    if kind == "gold":
        return palette_index == 10 or 108 <= palette_index <= 129 or palette_index == 210
    if kind == "light":
        return 10 <= palette_index <= 26
    raise FontBuildError(f"캠페인 진행 배경 seed 종류가 잘못됐습니다: {kind}")


def _camp_progress_english_mask(
    decoded: _DecodedSprite,
    spec: Mapping[str, Any],
    *,
    label: str,
) -> set[tuple[int, int]]:
    mask_roi = tuple(int(value) for value in spec["mask_roi"])
    x0, y0, width, height = mask_roi
    require(
        x0 >= 0 and y0 >= 0
        and x0 + width <= decoded.width
        and y0 + height <= decoded.height,
        f"캠페인 진행 배경 mask ROI가 범위를 넘었습니다: {label}",
    )
    mask = {
        (x, y)
        for y in range(y0, y0 + height)
        for x in range(x0, x0 + width)
        if decoded.transform[y * decoded.width + x] == 0
        and _camp_progress_seed_matches(
            decoded.pixels[y * decoded.width + x],
            str(spec["seed"]),
        )
    }
    dilate = int(spec["dilate"])
    require(dilate >= 0, f"캠페인 진행 배경 dilation이 음수입니다: {label}")
    for _ in range(dilate):
        expanded = set(mask)
        for x, y in mask:
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    target_x, target_y = x + dx, y + dy
                    if (
                        _camp_progress_inside(target_x, target_y, mask_roi)
                        and decoded.transform[target_y * decoded.width + target_x] == 0
                    ):
                        expanded.add((target_x, target_y))
        mask = expanded
    if "forced_mask" in spec:
        forced = tuple(int(value) for value in spec["forced_mask"])
        forced_x, forced_y, forced_width, forced_height = forced
        require(
            forced_x >= 0 and forced_y >= 0
            and forced_x + forced_width <= decoded.width
            and forced_y + forced_height <= decoded.height,
            f"캠페인 진행 배경 forced mask가 범위를 넘었습니다: {label}",
        )
        mask.update(
            (x, y)
            for y in range(forced_y, forced_y + forced_height)
            for x in range(forced_x, forced_x + forced_width)
            if decoded.transform[y * decoded.width + x] == 0
        )
    require(mask, f"캠페인 진행 배경 영문 mask가 비었습니다: {label}")
    return mask


def _camp_progress_clone_source(
    x: int,
    y: int,
    clone: Sequence[Any],
    *,
    label: str,
) -> tuple[int, int]:
    kind = str(clone[0])
    if kind == "offset":
        require(len(clone) == 2, f"캠페인 진행 배경 offset clone 계약이 잘못됐습니다: {label}")
        dx, dy = (int(value) for value in clone[1])
        return x + dx, y + dy
    if kind == "same_y_bands":
        require(len(clone) == 3, f"캠페인 진행 배경 band clone 계약이 잘못됐습니다: {label}")
        bands = tuple(tuple(int(value) for value in band) for band in clone[1])
        require(bands, f"캠페인 진행 배경 clone band가 비었습니다: {label}")
        salt = int(clone[2])
        block_x = x // 4
        block_y = y // 4
        selector = (
            block_x * 73_856_093
            ^ block_y * 19_349_663
            ^ salt * 83_492_791
        ) & 0xFFFFFFFF
        left, right = bands[selector % len(bands)]
        patch_width = 4
        require(right - left >= patch_width, f"캠페인 진행 배경 clone band가 너무 좁습니다: {label}")
        span = max(1, right - left - patch_width + 1)
        patch_left = left + ((selector >> 5) % span)
        return patch_left + (x & (patch_width - 1)), y
    raise FontBuildError(f"캠페인 진행 배경 clone 종류가 잘못됐습니다: {label}:{kind}")


def _camp_progress_restore_texture(
    decoded: _DecodedSprite,
    pixels: bytearray,
    mask: set[tuple[int, int]],
    spec: Mapping[str, Any],
    *,
    label: str,
) -> None:
    clone = tuple(spec["clone"])
    for x, y in sorted(mask, key=lambda point: (point[1], point[0])):
        source_x, source_y = _camp_progress_clone_source(
            x,
            y,
            clone,
            label=label,
        )
        require(
            0 <= source_x < decoded.width and 0 <= source_y < decoded.height,
            f"캠페인 진행 배경 clone donor가 범위를 넘었습니다: {label}:{source_x},{source_y}",
        )
        source = source_y * decoded.width + source_x
        require(
            decoded.transform[source] == 0,
            f"캠페인 진행 배경 clone donor가 투명합니다: {label}:{source_x},{source_y}",
        )
        pixels[y * decoded.width + x] = decoded.pixels[source]


def _camp_progress_glyph_line(
    font_sprites: Sequence[Sprite],
    mapping: Sequence[MappingRow],
    text: str,
    *,
    space_advance: int,
    label: str,
) -> tuple[tuple[tuple[int, int, int], ...], tuple[int, int]]:
    points: list[tuple[int, int, int]] = []
    cursor = 0
    for character in text:
        if character == " ":
            cursor += space_advance
            continue
        glyph_index = _image_ui_glyph_index(character, mapping)
        require(
            0 <= glyph_index < len(font_sprites),
            f"캠페인 진행 배경 glyph index가 범위를 넘었습니다: {label}:{character!r}",
        )
        glyph = _decode_sprite(
            font_sprites[glyph_index],
            label=f"{label}:glyph:{character}",
        )
        for offset, flag in enumerate(glyph.transform):
            if flag == 0:
                points.append(
                    (
                        cursor + glyph.offset_x + offset % glyph.width,
                        glyph.offset_y + offset // glyph.width,
                        glyph.pixels[offset],
                    )
                )
        cursor += glyph.width + 1
    require(points, f"캠페인 진행 배경 glyph ink가 비었습니다: {label}:{text!r}")
    left = min(x for x, _, _ in points)
    top = min(y for _, y, _ in points)
    right = max(x for x, _, _ in points) + 1
    bottom = max(y for _, y, _ in points) + 1
    return (
        tuple((x - left, y - top, palette) for x, y, palette in points),
        (right - left, bottom - top),
    )


def _camp_progress_overlay(
    decoded: _DecodedSprite,
    pixels: bytearray,
    spec: Mapping[str, Any],
    theme: str,
    normal_font_sprites: Sequence[Sprite],
    small_font_sprites: Sequence[Sprite],
    mapping: Sequence[MappingRow],
    *,
    label: str,
) -> set[tuple[int, int]]:
    font_kind = str(spec["font"])
    require(
        font_kind in {"normal", "small"},
        f"캠페인 진행 배경 font 종류가 잘못됐습니다: {label}:{font_kind}",
    )
    font_sprites = normal_font_sprites if font_kind == "normal" else small_font_sprites
    points, (ink_width, ink_height) = _camp_progress_glyph_line(
        font_sprites,
        mapping,
        str(spec["text"]),
        space_advance=6 if font_kind == "normal" else 4,
        label=label,
    )
    scale = int(spec["scale"])
    require(scale > 0, f"캠페인 진행 배경 scale이 잘못됐습니다: {label}:{scale}")
    layout_roi = tuple(int(value) for value in spec["layout_roi"])
    layout_x, layout_y, layout_width, layout_height = layout_roi
    require(
        layout_x >= 0 and layout_y >= 0
        and layout_x + layout_width <= decoded.width
        and layout_y + layout_height <= decoded.height,
        f"캠페인 진행 배경 layout ROI가 범위를 넘었습니다: {label}",
    )
    rendered_width, rendered_height = ink_width * scale, ink_height * scale
    left = layout_x + (layout_width - rendered_width) // 2
    top = layout_y + (layout_height - rendered_height) // 2
    require(
        theme in CAMP_PROGRESS_PALETTE_MAPS,
        f"캠페인 진행 배경 theme이 잘못됐습니다: {label}:{theme}",
    )
    palette_map = CAMP_PROGRESS_PALETTE_MAPS[theme]
    ink: set[tuple[int, int]] = set()
    for x, y, source_palette in points:
        require(
            source_palette in palette_map,
            f"캠페인 진행 배경 glyph palette가 다릅니다: {label}:{source_palette}",
        )
        target_palette = palette_map[source_palette]
        for target_y in range(top + y * scale, top + (y + 1) * scale):
            for target_x in range(left + x * scale, left + (x + 1) * scale):
                require(
                    _camp_progress_inside(target_x, target_y, layout_roi),
                    f"캠페인 진행 배경 glyph가 layout ROI를 넘었습니다: {label}:{target_x},{target_y}",
                )
                destination = target_y * decoded.width + target_x
                require(
                    decoded.transform[destination] == 0,
                    f"캠페인 진행 배경 glyph가 투명 영역과 겹칩니다: {label}:{target_x},{target_y}",
                )
                pixels[destination] = target_palette
                ink.add((target_x, target_y))
    require(ink, f"캠페인 진행 배경 한글 ink가 비었습니다: {label}")
    return ink


def _render_camp_progress_resource(
    source_raw: bytes,
    resource_name: str,
    normal_font_sprites: Sequence[Sprite],
    small_font_sprites: Sequence[Sprite],
    mapping: Sequence[MappingRow],
    *,
    label: str,
) -> bytes:
    require(
        resource_name in CAMP_PROGRESS_SPECS,
        f"캠페인 진행 배경 spec이 없습니다: {label}:{resource_name}",
    )
    source = parse_icn(source_raw, label=f"{label}:source")
    require(len(source.sprites) == 1, f"캠페인 진행 배경 sprite 수가 다릅니다: {label}")
    source_sprite = source.sprites[0]
    decoded = _decode_sprite(source_sprite, label=f"{label}:source:0")
    require(
        (
            decoded.offset_x,
            decoded.offset_y,
            decoded.width,
            decoded.height,
            decoded.animation,
        )
        == (0, 0, 640, 480, 0)
        and not any(decoded.transform),
        f"캠페인 진행 배경 geometry/transform이 다릅니다: {label}",
    )
    resource_spec = CAMP_PROGRESS_SPECS[resource_name]
    theme = str(resource_spec["theme"])
    text_specs = tuple(resource_spec["texts"])
    require(
        len(text_specs) == (4 if resource_name == "X_CMPBKG.ICN" else 5),
        f"캠페인 진행 배경 문구 수가 다릅니다: {label}",
    )
    pixels = bytearray(decoded.pixels)
    editable_rois: list[tuple[int, int, int, int]] = []
    for text_spec in text_specs:
        key = str(text_spec["key"])
        mask = _camp_progress_english_mask(
            decoded,
            text_spec,
            label=f"{label}:{key}",
        )
        _camp_progress_restore_texture(
            decoded,
            pixels,
            mask,
            text_spec,
            label=f"{label}:{key}",
        )
        _camp_progress_overlay(
            decoded,
            pixels,
            text_spec,
            theme,
            normal_font_sprites,
            small_font_sprites,
            mapping,
            label=f"{label}:{key}",
        )
        editable_rois.extend(
            (
                tuple(int(value) for value in text_spec["mask_roi"]),
                tuple(int(value) for value in text_spec["layout_roi"]),
            )
        )
    localized = Sprite(
        decoded.offset_x,
        decoded.offset_y,
        decoded.width,
        decoded.height,
        decoded.animation,
        _encode_sprite_data(
            decoded.width,
            decoded.height,
            bytes(pixels),
            decoded.transform,
        ),
    )
    result = pack_icn((localized,))
    candidate = _decode_sprite(localized, label=f"{label}:candidate:0")
    require(
        candidate.transform == decoded.transform,
        f"캠페인 진행 배경 transform이 바뀌었습니다: {label}",
    )
    _require_outside_rois_exact(
        decoded,
        candidate,
        editable_rois,
        label=label,
    )
    return result


def _localize_camp_progress_resources(
    base: "AggArchive",
    normal_font_sprites: Sequence[Sprite],
    small_font_sprites: Sequence[Sprite],
    mapping: Sequence[MappingRow],
    *,
    label: str,
) -> dict[str, bytes]:
    expected = set(CAMP_PROGRESS_RESOURCE_SOURCE_IDENTITIES)
    available = {entry.name.upper() for entry in base.entries}
    present = available & expected
    if not present:
        return {}
    require(
        frozenset(present) in CAMP_PROGRESS_ARCHIVE_RESOURCE_SETS,
        f"캠페인 진행 배경 리소스 집합이 잘못됐습니다: {label}: {sorted(present)}",
    )
    require(mapping, f"캠페인 진행 배경 렌더링에 글자 매핑이 없습니다: {label}")
    require(
        set(CAMP_PROGRESS_RESOURCE_OUTPUT_IDENTITIES) == expected
        and set(CAMP_PROGRESS_SPECS) == expected,
        f"캠페인 진행 배경 output/spec 집합이 source와 다릅니다: {label}",
    )
    replacements: dict[str, bytes] = {}
    for resource_name in sorted(present):
        source_raw = base.get(resource_name).payload
        require(
            (len(source_raw), sha256_bytes(source_raw))
            == CAMP_PROGRESS_RESOURCE_SOURCE_IDENTITIES[resource_name],
            f"순정 캠페인 진행 배경 identity가 다릅니다: {label}:{resource_name}",
        )
        output = _render_camp_progress_resource(
            source_raw,
            resource_name,
            normal_font_sprites,
            small_font_sprites,
            mapping,
            label=f"{label}:{resource_name}",
        )
        require(
            (len(output), sha256_bytes(output))
            == CAMP_PROGRESS_RESOURCE_OUTPUT_IDENTITIES[resource_name],
            f"캠페인 진행 배경 출력 identity가 다릅니다: {label}:{resource_name}",
        )
        replacements[resource_name] = output
    require(set(replacements) == present, f"캠페인 진행 배경 교체 집합이 잘못됐습니다: {label}")
    return replacements


def _localize_game_button_resources(
    base: "AggArchive",
    normal_font_sprites: Sequence[Sprite],
    mapping: Sequence[MappingRow],
    *,
    label: str,
    canonical_raster_identities: bool = True,
) -> dict[str, bytes]:
    expected = set(GAME_BUTTON_RESOURCE_SOURCE_IDENTITIES)
    available = {entry.name.upper() for entry in base.entries}
    present = available & expected
    if not present:
        return {}
    require(present == expected, f"게임 버튼 리소스 집합이 불완전합니다: {label}: {sorted(expected - present)}")
    require(mapping, f"게임 버튼 렌더링에 글자 매핑이 없습니다: {label}")
    require(
        set(GAME_BUTTON_RESOURCE_OUTPUT_IDENTITIES) == expected,
        f"게임 버튼 출력 identity 집합이 source와 다릅니다: {label}",
    )
    target_keys = tuple(
        (str(target["resource"]).upper(), int(target["sprite"]))
        for target in GAME_BUTTON_TEXT_TARGETS
    )
    require(
        len(target_keys) == 80
        and len(set(target_keys)) == len(target_keys)
        and {resource for resource, _ in target_keys} == expected,
        f"게임 버튼 target 계약이 잘못됐습니다: {label}",
    )
    source_payloads: dict[str, bytes] = {}
    for resource_name, source_identity in GAME_BUTTON_RESOURCE_SOURCE_IDENTITIES.items():
        source_raw = base.get(resource_name).payload
        require(
            (len(source_raw), sha256_bytes(source_raw)) == source_identity,
            f"순정 게임 버튼 identity가 다릅니다: {label}:{resource_name}",
        )
        source_payloads[resource_name] = source_raw
    targets_by_resource: dict[str, list[Mapping[str, Any]]] = {}
    for target in GAME_BUTTON_TEXT_TARGETS:
        targets_by_resource.setdefault(str(target["resource"]), []).append(target)
    replacements = {
        resource_name: _localize_image_ui_text_resource(
            source_payloads[resource_name],
            resource_targets,
            normal_font_sprites,
            mapping,
            {},
            label=f"{label}:{resource_name}",
        )
        for resource_name, resource_targets in targets_by_resource.items()
    }
    require(set(replacements) == expected, f"게임 버튼 교체 집합이 잘못됐습니다: {label}")
    if canonical_raster_identities:
        for resource_name, payload in replacements.items():
            require(
                (len(payload), sha256_bytes(payload)) == GAME_BUTTON_RESOURCE_OUTPUT_IDENTITIES[resource_name],
                f"게임 버튼 출력 identity가 다릅니다: {label}:{resource_name}",
            )
    return replacements


def _localize_expansion_menu_resources(
    base: "AggArchive",
    normal_font_sprites: Sequence[Sprite],
    mapping: Sequence[MappingRow],
    *,
    label: str,
    canonical_raster_identities: bool = True,
) -> dict[str, bytes]:
    expected = set(EXPANSION_MENU_RESOURCE_SOURCE_IDENTITIES)
    available = {entry.name.upper() for entry in base.entries}
    present = available & expected
    if not present:
        return {}
    require(present == expected, f"확장 메뉴 리소스 집합이 불완전합니다: {label}: {sorted(expected - present)}")
    require(mapping, f"확장 메뉴 렌더링에 글자 매핑이 없습니다: {label}")
    require(
        set(EXPANSION_MENU_RESOURCE_OUTPUT_IDENTITIES) == expected,
        f"확장 메뉴 출력 identity 집합이 source와 다릅니다: {label}",
    )
    target_keys = tuple(
        (str(target["resource"]).upper(), int(target["sprite"]))
        for target in EXPANSION_MENU_TEXT_TARGETS
    )
    require(
        len(target_keys) == 19
        and len(set(target_keys)) == len(target_keys)
        and {resource for resource, _ in target_keys} == expected,
        f"확장 메뉴 target 계약이 잘못됐습니다: {label}",
    )
    source_payloads: dict[str, bytes] = {}
    for resource_name, source_identity in EXPANSION_MENU_RESOURCE_SOURCE_IDENTITIES.items():
        source_raw = base.get(resource_name).payload
        require(
            (len(source_raw), sha256_bytes(source_raw)) == source_identity,
            f"순정 확장 메뉴 identity가 다릅니다: {label}:{resource_name}",
        )
        source_payloads[resource_name] = source_raw
    targets_by_resource: dict[str, list[Mapping[str, Any]]] = {}
    for target in EXPANSION_MENU_TEXT_TARGETS:
        targets_by_resource.setdefault(str(target["resource"]), []).append(target)
    donor_resource = "X_NEWCMP.ICN"
    donor_icn = parse_icn(source_payloads[donor_resource], label=f"{label}:expansion-menu-donor")
    background_donors = {
        (donor_resource, donor_index): _decode_sprite(
            donor_icn.sprites[donor_index],
            label=f"{label}:expansion-menu-donor:{donor_index}",
        )
        for donor_index in (0, 1)
    }
    replacements = {
        resource_name: _localize_image_ui_text_resource(
            source_payloads[resource_name],
            resource_targets,
            normal_font_sprites,
            mapping,
            background_donors,
            label=f"{label}:{resource_name}",
        )
        for resource_name, resource_targets in targets_by_resource.items()
    }
    require(set(replacements) == expected, f"확장 메뉴 교체 집합이 잘못됐습니다: {label}")
    if canonical_raster_identities:
        for resource_name, payload in replacements.items():
            require(
                (len(payload), sha256_bytes(payload)) == EXPANSION_MENU_RESOURCE_OUTPUT_IDENTITIES[resource_name],
                f"확장 메뉴 출력 identity가 다릅니다: {label}:{resource_name}",
            )
    return replacements


def _localize_embedded_mirror_resource(
    source_raw: bytes,
    specs: Sequence[Mapping[str, Any]],
    localized_resources: Mapping[str, bytes],
    *,
    label: str,
) -> bytes:
    source = parse_icn(source_raw, label=f"{label}:source")
    sprites = list(source.sprites)
    specs_by_sprite: dict[int, list[Mapping[str, Any]]] = {}
    for mirror in specs:
        specs_by_sprite.setdefault(int(mirror["target_sprite"]), []).append(mirror)
    decoded_source_cache: dict[tuple[str, int], _DecodedSprite] = {}
    for sprite_index, sprite_specs in specs_by_sprite.items():
        require(0 <= sprite_index < len(sprites), f"내장 UI target sprite가 범위를 넘었습니다: {label}:{sprite_index}")
        before = _decode_sprite(source.sprites[sprite_index], label=f"{label}:{sprite_index}:before")
        pixels = bytearray(before.pixels)
        transform = bytearray(before.transform)
        target_rois: list[tuple[int, int, int, int]] = []
        for mirror in sprite_specs:
            source_resource = str(mirror["source_resource"])
            source_index = int(mirror["source_sprite"])
            require(source_resource in localized_resources, f"내장 UI mirror source가 없습니다: {label}:{source_resource}")
            cache_key = (source_resource, source_index)
            if cache_key not in decoded_source_cache:
                source_icn = parse_icn(localized_resources[source_resource], label=f"{label}:mirror:{source_resource}")
                require(0 <= source_index < len(source_icn.sprites), f"내장 UI mirror sprite가 범위를 넘었습니다: {label}:{cache_key}")
                decoded_source_cache[cache_key] = _decode_sprite(
                    source_icn.sprites[source_index],
                    label=f"{label}:mirror:{source_resource}:{source_index}",
                )
            donor = decoded_source_cache[cache_key]
            sx, sy, sw, sh = (int(value) for value in mirror["source_roi"])
            tx, ty, tw, th = (int(value) for value in mirror["target_roi"])
            require(
                (sw, sh) == (tw, th)
                and sx >= 0 and sy >= 0 and sx + sw <= donor.width and sy + sh <= donor.height
                and tx >= 0 and ty >= 0 and tx + tw <= before.width and ty + th <= before.height,
                f"내장 UI mirror ROI가 잘못됐습니다: {label}:{source_resource}:{source_index}",
            )
            require(
                all(
                    tx + tw <= ox or ox + ow <= tx or ty + th <= oy or oy + oh <= ty
                    for ox, oy, ow, oh in target_rois
                ),
                f"내장 UI target ROI가 겹칩니다: {label}:{sprite_index}:{tx},{ty}",
            )
            for row in range(sh):
                source_start = (sy + row) * donor.width + sx
                target_start = (ty + row) * before.width + tx
                pixels[target_start : target_start + tw] = donor.pixels[source_start : source_start + sw]
                transform[target_start : target_start + tw] = donor.transform[source_start : source_start + sw]
            target_rois.append((tx, ty, tw, th))
        localized = Sprite(
            before.offset_x,
            before.offset_y,
            before.width,
            before.height,
            before.animation,
            _encode_sprite_data(before.width, before.height, bytes(pixels), bytes(transform)),
        )
        after = _decode_sprite(localized, label=f"{label}:{sprite_index}:after")
        _require_outside_rois_exact(before, after, target_rois, label=f"{label}:{sprite_index}")
        sprites[sprite_index] = localized
    result = pack_icn(tuple(sprites))
    candidate = parse_icn(result, label=f"{label}:candidate")
    for sprite_index, (before_sprite, after_sprite) in enumerate(zip(source.sprites, candidate.sprites)):
        if sprite_index not in specs_by_sprite:
            require(after_sprite == before_sprite, f"내장 UI non-target sprite가 바뀌었습니다: {label}:{sprite_index}")
    return result


def _localize_embedded_ui_resources(
    base: "AggArchive",
    localized_resources: Mapping[str, bytes],
    normal_font_sprites: Sequence[Sprite],
    mapping: Sequence[MappingRow],
    *,
    label: str,
    canonical_raster_identities: bool = True,
) -> dict[str, bytes]:
    expected = set(EMBEDDED_UI_RESOURCE_SOURCE_IDENTITIES)
    available = {entry.name.upper() for entry in base.entries}
    present = available & expected
    if not present:
        return {}
    require(present == expected, f"내장 UI 리소스 집합이 불완전합니다: {label}: {sorted(expected - present)}")
    require(
        set(EMBEDDED_UI_RESOURCE_OUTPUT_IDENTITIES) == expected,
        f"내장 UI 출력 identity 집합이 source와 다릅니다: {label}",
    )
    require(len(EMBEDDED_UI_MIRRORS) == 41, f"내장 UI mirror 계약 수가 잘못됐습니다: {label}")
    mirror_targets = {str(spec["target_resource"]).upper() for spec in EMBEDDED_UI_MIRRORS}
    direct_targets = {str(target["resource"]).upper() for target in EMBEDDED_UI_TEXT_TARGETS}
    require(
        mirror_targets.isdisjoint(direct_targets)
        and mirror_targets | direct_targets == expected
        and direct_targets == {"WINLOSEE.ICN"},
        f"내장 UI target 집합이 잘못됐습니다: {label}",
    )
    for resource_name, source_identity in EMBEDDED_UI_RESOURCE_SOURCE_IDENTITIES.items():
        source_raw = base.get(resource_name).payload
        require(
            (len(source_raw), sha256_bytes(source_raw)) == source_identity,
            f"순정 내장 UI identity가 다릅니다: {label}:{resource_name}",
        )
    specs_by_resource: dict[str, list[Mapping[str, Any]]] = {}
    for mirror in EMBEDDED_UI_MIRRORS:
        specs_by_resource.setdefault(str(mirror["target_resource"]), []).append(mirror)
    replacements = {
        resource_name: _localize_embedded_mirror_resource(
            base.get(resource_name).payload,
            specs,
            localized_resources,
            label=f"{label}:{resource_name}",
        )
        for resource_name, specs in specs_by_resource.items()
    }
    for resource_name in direct_targets:
        resource_targets = [target for target in EMBEDDED_UI_TEXT_TARGETS if target["resource"] == resource_name]
        replacements[resource_name] = _localize_image_ui_text_resource(
            base.get(resource_name).payload,
            resource_targets,
            normal_font_sprites,
            mapping,
            {},
            label=f"{label}:{resource_name}",
        )
    require(set(replacements) == expected, f"내장 UI 교체 집합이 잘못됐습니다: {label}")
    if canonical_raster_identities:
        for resource_name, payload in replacements.items():
            require(
                (len(payload), sha256_bytes(payload)) == EMBEDDED_UI_RESOURCE_OUTPUT_IDENTITIES[resource_name],
                f"내장 UI 출력 identity가 다릅니다: {label}:{resource_name}",
            )
    return replacements


def _localize_townwind_resource(
    base: "AggArchive",
    normal_font_sprites: Sequence[Sprite],
    small_font_sprites: Sequence[Sprite],
    mapping: Sequence[MappingRow],
    *,
    label: str,
    canonical_raster_identities: bool = True,
) -> dict[str, bytes]:
    available = {entry.name.upper() for entry in base.entries}
    if TOWNWIND_RESOURCE_NAME not in available:
        return {}
    source_raw = base.get(TOWNWIND_RESOURCE_NAME).payload
    require(
        (len(source_raw), sha256_bytes(source_raw)) == TOWNWIND_SOURCE_IDENTITY,
        f"순정 TOWNWIND identity가 다릅니다: {label}",
    )
    require(mapping, f"TOWNWIND 렌더링에 글자 매핑이 없습니다: {label}")
    cost_localized = _localize_image_ui_text_resource(
        source_raw,
        TOWNWIND_COST_TARGETS,
        small_font_sprites,
        mapping,
        {},
        label=f"{label}:{TOWNWIND_RESOURCE_NAME}:cost",
    )
    result = _localize_image_ui_text_resource(
        cost_localized,
        TOWNWIND_BUTTON_TARGETS,
        normal_font_sprites,
        mapping,
        {},
        label=f"{label}:{TOWNWIND_RESOURCE_NAME}:buttons",
    )
    if canonical_raster_identities:
        require(
            (len(result), sha256_bytes(result)) == TOWNWIND_OUTPUT_IDENTITY,
            f"TOWNWIND 출력 identity가 다릅니다: {label}",
        )
    return {TOWNWIND_RESOURCE_NAME: result}


def _localize_textbar_resource(
    base: "AggArchive",
    small_font_sprites: Sequence[Sprite],
    mapping: Sequence[MappingRow],
    *,
    label: str,
    canonical_raster_identities: bool = True,
) -> dict[str, bytes]:
    available = {entry.name.upper() for entry in base.entries}
    if TEXTBAR_RESOURCE_NAME not in available:
        return {}
    source_raw = base.get(TEXTBAR_RESOURCE_NAME).payload
    require(
        (len(source_raw), sha256_bytes(source_raw)) == TEXTBAR_SOURCE_IDENTITY,
        f"순정 TEXTBAR identity가 다릅니다: {label}",
    )
    require(mapping, f"TEXTBAR 렌더링에 글자 매핑이 없습니다: {label}")
    result = _localize_image_ui_text_resource(
        source_raw,
        TEXTBAR_TARGETS,
        small_font_sprites,
        mapping,
        {},
        label=f"{label}:{TEXTBAR_RESOURCE_NAME}",
    )
    if canonical_raster_identities:
        require(
            (len(result), sha256_bytes(result)) == TEXTBAR_OUTPUT_IDENTITY,
            f"TEXTBAR 출력 identity가 다릅니다: {label}",
        )
    return {TEXTBAR_RESOURCE_NAME: result}


@dataclass(frozen=True)
class FancyMainMenuDonors:
    button_identity: tuple[int, str]
    sprites: tuple[Sprite, ...]


def _fancy_main_menu_inside_box(x: int, y: int, box: tuple[int, int, int, int]) -> bool:
    x0, y0, width, height = box
    return x0 <= x < x0 + width and y0 <= y < y0 + height


def _fancy_main_menu_editable_roi(spec: Mapping[str, Any]) -> tuple[int, int, int, int]:
    boxes = tuple(tuple(int(value) for value in box) for box in spec["mask_boxes"])
    layout = tuple(int(value) for value in spec["layout_roi"])
    all_boxes = (*boxes, layout)
    left = min(box[0] for box in all_boxes)
    top = min(box[1] for box in all_boxes)
    right = max(box[0] + box[2] for box in all_boxes)
    bottom = max(box[1] + box[3] for box in all_boxes)
    return left, top, right - left, bottom - top


def _fancy_main_menu_english_mask(
    states: Sequence[_DecodedSprite],
    boxes: Sequence[tuple[int, int, int, int]],
    *,
    label: str,
) -> set[tuple[int, int]]:
    require(len(states) == 4, f"장식 메인 메뉴 상태 수가 다릅니다: {label}")
    width, height = states[0].width, states[0].height
    require(
        all(state.width == width for state in states),
        f"장식 메인 메뉴 상태 폭이 다릅니다: {label}",
    )
    mask: set[tuple[int, int]] = set()
    for state in states:
        for y in range(state.height):
            for x in range(state.width):
                if not any(_fancy_main_menu_inside_box(x, y, box) for box in boxes):
                    continue
                offset = y * state.width + x
                palette_index = state.pixels[offset]
                if state.transform[offset] == 0 and (
                    108 <= palette_index <= 130 or 198 <= palette_index <= 213
                ):
                    mask.add((x, y))
    dilated: set[tuple[int, int]] = set()
    for x, y in mask:
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                target_x, target_y = x + dx, y + dy
                if 0 <= target_x < width and 0 <= target_y < height:
                    dilated.add((target_x, target_y))
    result = {
        (x, y)
        for x, y in dilated
        if any(_fancy_main_menu_inside_box(x, y, box) for box in boxes)
        and states[0].transform[y * width + x] == 0
    }
    require(result, f"장식 메인 메뉴 영문 mask가 비었습니다: {label}")
    return result


def _fancy_main_menu_inpaint(
    decoded: _DecodedSprite,
    mask: set[tuple[int, int]],
    color_distance: Sequence[Sequence[int]],
    boxes: Sequence[tuple[int, int, int, int]],
    *,
    label: str,
) -> bytes:
    require(
        len(color_distance) == 256 and all(len(row) == 256 for row in color_distance),
        f"장식 메인 메뉴 color distance 수가 다릅니다: {label}",
    )
    pixels = bytearray(decoded.pixels)
    remaining = set(mask)
    original_known = {
        (x, y)
        for y in range(decoded.height)
        for x in range(decoded.width)
        if decoded.transform[y * decoded.width + x] == 0 and (x, y) not in remaining
    }
    donor_left = max(0, min(box[0] for box in boxes) - 6)
    donor_top = max(0, min(box[1] for box in boxes) - 6)
    donor_right = min(decoded.width, max(box[0] + box[2] for box in boxes) + 6)
    donor_bottom = min(decoded.height, max(box[1] + box[3] for box in boxes) + 6)
    candidates = [
        (x, y)
        for y in range(donor_top + 1, donor_bottom - 1)
        for x in range(donor_left + 1, donor_right - 1)
        if (x - donor_left) % 3 == 0
        and (y - donor_top) % 3 == 0
        and all(
            (x + dx, y + dy) in original_known
            for dy in (-1, 0, 1)
            for dx in (-1, 0, 1)
        )
    ]
    require(candidates, f"장식 메인 메뉴 texture donor가 없습니다: {label}")

    def context(x: int, y: int) -> list[tuple[int, int]]:
        return [
            (dx, dy)
            for dy in (-1, 0, 1)
            for dx in (-1, 0, 1)
            if (dx != 0 or dy != 0)
            and 0 <= x + dx < decoded.width
            and 0 <= y + dy < decoded.height
            and (x + dx, y + dy) not in remaining
            and decoded.transform[(y + dy) * decoded.width + x + dx] == 0
        ]

    boundary: list[tuple[int, int, int]] = []
    for x, y in remaining:
        adjacent = context(x, y)
        if adjacent:
            heapq.heappush(boundary, (-len(adjacent), y, x))
    while remaining:
        require(boundary, f"장식 메인 메뉴 texture mask를 채울 수 없습니다: {label}")
        priority, y, x = heapq.heappop(boundary)
        if (x, y) not in remaining:
            continue
        adjacent = context(x, y)
        current_priority = -len(adjacent)
        if priority != current_priority:
            heapq.heappush(boundary, (current_priority, y, x))
            continue
        require(adjacent, f"장식 메인 메뉴 texture context가 비었습니다: {label}:{x},{y}")
        best: tuple[tuple[int, int, int], int] | None = None
        for source_x, source_y in candidates:
            score = (abs(source_x - x) + abs(source_y - y)) * 96
            for dx, dy in adjacent:
                target_palette = pixels[(y + dy) * decoded.width + x + dx]
                source_palette = decoded.pixels[(source_y + dy) * decoded.width + source_x + dx]
                score += color_distance[target_palette][source_palette]
            key = (score, source_y, source_x)
            if best is None or key < best[0]:
                best = (key, decoded.pixels[source_y * decoded.width + source_x])
        require(best is not None, f"장식 메인 메뉴 texture match가 실패했습니다: {label}:{x},{y}")
        pixels[y * decoded.width + x] = best[1]
        remaining.remove((x, y))
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                neighbor = (x + dx, y + dy)
                if neighbor not in remaining:
                    continue
                neighbor_context = context(*neighbor)
                if neighbor_context:
                    heapq.heappush(
                        boundary,
                        (-len(neighbor_context), neighbor[1], neighbor[0]),
                    )
    return bytes(pixels)


def _fancy_main_menu_glyph_line(
    small_font_sprites: Sequence[Sprite],
    mapping: Sequence[MappingRow],
    text: str,
    *,
    label: str,
) -> tuple[tuple[tuple[int, int, int], ...], tuple[int, int]]:
    glyphs = tuple(
        _decode_sprite(
            small_font_sprites[_image_ui_glyph_index(character, mapping)],
            label=f"{label}:glyph:{character}",
        )
        for character in text
    )
    points: list[tuple[int, int, int]] = []
    cursor = 0
    for glyph in glyphs:
        for offset, flag in enumerate(glyph.transform):
            if flag == 0:
                points.append(
                    (
                        cursor + glyph.offset_x + offset % glyph.width,
                        glyph.offset_y + offset // glyph.width,
                        glyph.pixels[offset],
                    )
                )
        cursor += glyph.width + 1
    require(points, f"장식 메인 메뉴 glyph ink가 비었습니다: {label}:{text!r}")
    left = min(x for x, _, _ in points)
    top = min(y for _, y, _ in points)
    right = max(x for x, _, _ in points) + 1
    bottom = max(y for _, y, _ in points) + 1
    return (
        tuple((x - left, y - top, palette) for x, y, palette in points),
        (right - left, bottom - top),
    )


def _fancy_main_menu_overlay(
    decoded: _DecodedSprite,
    base_pixels: bytes,
    spec: Mapping[str, Any],
    state_index: int,
    small_font_sprites: Sequence[Sprite],
    mapping: Sequence[MappingRow],
    *,
    label: str,
) -> bytes:
    text_lines = str(spec["text"]).split("\n")
    require(text_lines and all(text_lines), f"장식 메인 메뉴 문구가 비었습니다: {label}")
    lines = tuple(
        _fancy_main_menu_glyph_line(
            small_font_sprites,
            mapping,
            text,
            label=label,
        )
        for text in text_lines
    )
    scaled_sizes = tuple((size[0] * 2, size[1] * 2) for _, size in lines)
    layout_x, layout_y, layout_width, layout_height = (
        int(value) for value in spec["layout_roi"]
    )
    gap = 0 if len(lines) == 2 and layout_height <= 44 else 2
    block_height = sum(height for _, height in scaled_sizes) + gap * (len(lines) - 1)
    top = layout_y + (layout_height - block_height) // 2
    output = bytearray(base_pixels)
    palette_map = FANCY_MAIN_MENU_STATE_PALETTES[state_index]
    ink_count = 0
    for (points, _), (line_width, line_height) in zip(lines, scaled_sizes):
        left = layout_x + (layout_width - line_width) // 2
        for x, y, palette_index in points:
            require(
                palette_index in palette_map,
                f"장식 메인 메뉴 glyph palette가 다릅니다: {label}:{palette_index}",
            )
            for target_y in range(top + y * 2, top + y * 2 + 2):
                for target_x in range(left + x * 2, left + x * 2 + 2):
                    require(
                        0 <= target_x < decoded.width
                        and 0 <= target_y < decoded.height,
                        f"장식 메인 메뉴 glyph가 sprite를 넘었습니다: {label}:{target_x},{target_y}",
                    )
                    destination = target_y * decoded.width + target_x
                    require(
                        decoded.transform[destination] == 0,
                        f"장식 메인 메뉴 glyph가 투명 영역과 겹칩니다: {label}:{target_x},{target_y}",
                    )
                    output[destination] = palette_map[palette_index]
                    ink_count += 1
        top += line_height + gap
    require(ink_count, f"장식 메인 메뉴 한글 ink가 비었습니다: {label}")
    return bytes(output)


def _fancy_main_menu_palette(raw: bytes, *, label: str) -> tuple[tuple[int, int, int], ...]:
    require(
        (len(raw), sha256_bytes(raw)) == FANCY_MAIN_MENU_PALETTE_IDENTITY,
        f"장식 메인 메뉴 palette identity가 다릅니다: {label}",
    )
    return tuple(
        tuple((value << 2) | (value >> 4) for value in raw[index * 3 : index * 3 + 3])
        for index in range(256)
    )


def _render_fancy_main_menu_buttons(
    source_raw: bytes,
    palette_raw: bytes,
    small_font_sprites: Sequence[Sprite],
    mapping: Sequence[MappingRow],
    *,
    label: str,
) -> bytes:
    require(
        (len(source_raw), sha256_bytes(source_raw)) == FANCY_MAIN_MENU_BUTTON_SOURCE_IDENTITY,
        f"순정 장식 메인 메뉴 버튼 identity가 다릅니다: {label}",
    )
    source = parse_icn(source_raw, label=f"{label}:source")
    target_indices = tuple(
        int(sprite_index)
        for spec in FANCY_MAIN_MENU_SPECS
        for sprite_index in spec["sprites"]
    )
    require(
        len(source.sprites) == 20
        and len(target_indices) == 20
        and set(target_indices) == set(range(20)),
        f"장식 메인 메뉴 버튼 target 계약이 다릅니다: {label}",
    )
    palette = _fancy_main_menu_palette(palette_raw, label=label)
    color_distance = tuple(
        tuple(
            sum(
                (int(left[channel]) - int(right[channel])) ** 2
                for channel in range(3)
            )
            for right in palette
        )
        for left in palette
    )
    decoded = tuple(
        _decode_sprite(sprite, label=f"{label}:source:{index}")
        for index, sprite in enumerate(source.sprites)
    )
    output = list(source.sprites)
    for spec in FANCY_MAIN_MENU_SPECS:
        indices = tuple(int(value) for value in spec["sprites"])
        states = tuple(decoded[index] for index in indices)
        mask_boxes = tuple(tuple(int(value) for value in box) for box in spec["mask_boxes"])
        mask = _fancy_main_menu_english_mask(
            states,
            mask_boxes,
            label=f"{label}:{spec['key']}",
        )
        editable_roi = _fancy_main_menu_editable_roi(spec)
        for state_index, sprite_index in enumerate(indices):
            state = states[state_index]
            restored = _fancy_main_menu_inpaint(
                state,
                mask,
                color_distance,
                mask_boxes,
                label=f"{label}:{spec['key']}:{state_index}",
            )
            localized_pixels = _fancy_main_menu_overlay(
                state,
                restored,
                spec,
                state_index,
                small_font_sprites,
                mapping,
                label=f"{label}:{spec['key']}:{state_index}",
            )
            localized = Sprite(
                state.offset_x,
                state.offset_y,
                state.width,
                state.height,
                state.animation,
                _encode_sprite_data(
                    state.width,
                    state.height,
                    localized_pixels,
                    state.transform,
                ),
            )
            localized_decoded = _decode_sprite(
                localized,
                label=f"{label}:candidate:{sprite_index}",
            )
            _require_outside_roi_exact(
                state,
                localized_decoded,
                editable_roi,
                label=f"{label}:{sprite_index}",
            )
            output[sprite_index] = localized
    return pack_icn(tuple(output))


def _fancy_main_menu_donors_from_button_payload(
    payload: bytes,
    *,
    label: str,
) -> FancyMainMenuDonors:
    identity = (len(payload), sha256_bytes(payload))
    localized = parse_icn(payload, label=label)
    require(len(localized.sprites) == 20, f"장식 메인 메뉴 donor sprite 수가 다릅니다: {label}")
    sprites = tuple(
        localized.sprites[int(spec["sprites"][0])]
        for spec in FANCY_MAIN_MENU_SPECS
    )
    return FancyMainMenuDonors(identity, sprites)


def extract_fancy_main_menu_donors(
    localized_main_raw: bytes,
    *,
    label: str,
) -> FancyMainMenuDonors:
    archive = parse_agg(localized_main_raw, label=f"{label}:archive")
    payload = archive.get(FANCY_MAIN_MENU_BUTTON_RESOURCE_NAME).payload
    require(
        (len(payload), sha256_bytes(payload)) == FANCY_MAIN_MENU_BUTTON_OUTPUT_IDENTITY,
        f"장식 메인 메뉴 donor identity가 다릅니다: {label}",
    )
    return _fancy_main_menu_donors_from_button_payload(payload, label=f"{label}:buttons")


def _render_fancy_main_menu_heroes(
    source_raw: bytes,
    donors: FancyMainMenuDonors,
    *,
    label: str,
) -> bytes:
    require(
        donors.button_identity == FANCY_MAIN_MENU_BUTTON_OUTPUT_IDENTITY
        and len(donors.sprites) == len(FANCY_MAIN_MENU_SPECS),
        f"장식 메인 메뉴 HEROES donor 계약이 다릅니다: {label}",
    )
    source = parse_icn(source_raw, label=f"{label}:source")
    require(len(source.sprites) == 1, f"HEROES sprite 수가 다릅니다: {label}")
    background = _decode_sprite(source.sprites[0], label=f"{label}:background")
    require(
        (background.offset_x, background.offset_y, background.width, background.height, background.animation)
        == (0, 0, 640, 480, 0),
        f"HEROES 배경 layout이 다릅니다: {label}",
    )
    pixels = bytearray(background.pixels)
    transform = bytearray(background.transform)
    global_rois: list[tuple[int, int, int, int]] = []
    for spec, donor_sprite in zip(FANCY_MAIN_MENU_SPECS, donors.sprites):
        donor = _decode_sprite(donor_sprite, label=f"{label}:donor:{spec['key']}")
        x0, y0, width, height = _fancy_main_menu_editable_roi(spec)
        require(
            x0 >= 0 and y0 >= 0
            and x0 + width <= donor.width
            and y0 + height <= donor.height,
            f"장식 메인 메뉴 donor ROI가 범위를 넘었습니다: {label}:{spec['key']}",
        )
        global_roi = (donor.offset_x + x0, donor.offset_y + y0, width, height)
        require(
            global_roi[0] >= 0 and global_roi[1] >= 0
            and global_roi[0] + width <= background.width
            and global_roi[1] + height <= background.height,
            f"장식 메인 메뉴 HEROES ROI가 범위를 넘었습니다: {label}:{spec['key']}",
        )
        global_rois.append(global_roi)
        for y in range(y0, y0 + height):
            for x in range(x0, x0 + width):
                donor_offset = y * donor.width + x
                if donor.transform[donor_offset] != 0:
                    continue
                target_x = donor.offset_x + x
                target_y = donor.offset_y + y
                destination = target_y * background.width + target_x
                pixels[destination] = donor.pixels[donor_offset]
                transform[destination] = 0
    localized_background = Sprite(
        background.offset_x,
        background.offset_y,
        background.width,
        background.height,
        background.animation,
        _encode_sprite_data(
            background.width,
            background.height,
            bytes(pixels),
            bytes(transform),
        ),
    )
    result = pack_icn((localized_background,))
    candidate = _decode_sprite(localized_background, label=f"{label}:candidate")
    _require_outside_rois_exact(
        background,
        candidate,
        global_rois,
        label=label,
    )
    return result


def _localize_fancy_main_menu_resources(
    base: "AggArchive",
    small_font_sprites: Sequence[Sprite],
    mapping: Sequence[MappingRow],
    external_donors: FancyMainMenuDonors | None,
    *,
    label: str,
) -> dict[str, bytes]:
    available = {entry.name.upper() for entry in base.entries}
    has_buttons = FANCY_MAIN_MENU_BUTTON_RESOURCE_NAME in available
    has_heroes = FANCY_MAIN_MENU_HEROES_RESOURCE_NAME in available
    if not has_heroes:
        require(not has_buttons, f"장식 메인 메뉴 HEROES 리소스가 없습니다: {label}")
        return {}

    replacements: dict[str, bytes] = {}
    donors = external_donors
    if has_buttons:
        require(
            external_donors is None
            and FANCY_MAIN_MENU_PALETTE_RESOURCE_NAME in available,
            f"장식 메인 메뉴 base donor/palette 계약이 다릅니다: {label}",
        )
        button_payload = _render_fancy_main_menu_buttons(
            base.get(FANCY_MAIN_MENU_BUTTON_RESOURCE_NAME).payload,
            base.get(FANCY_MAIN_MENU_PALETTE_RESOURCE_NAME).payload,
            small_font_sprites,
            mapping,
            label=f"{label}:{FANCY_MAIN_MENU_BUTTON_RESOURCE_NAME}",
        )
        require(
            (len(button_payload), sha256_bytes(button_payload))
            == FANCY_MAIN_MENU_BUTTON_OUTPUT_IDENTITY,
            f"장식 메인 메뉴 버튼 출력 identity가 다릅니다: {label}",
        )
        replacements[FANCY_MAIN_MENU_BUTTON_RESOURCE_NAME] = button_payload
        donors = _fancy_main_menu_donors_from_button_payload(
            button_payload,
            label=f"{label}:localized-buttons",
        )
    elif donors is None:
        # Direct expansion-only API calls intentionally keep HEROES pristine.
        # The installer passes donors extracted from the rebuilt base archive.
        return {}

    require(donors is not None, f"장식 메인 메뉴 donor가 없습니다: {label}")
    source_heroes = base.get(FANCY_MAIN_MENU_HEROES_RESOURCE_NAME).payload
    source_identity = (len(source_heroes), sha256_bytes(source_heroes))
    variants = [
        variant
        for variant, identity in FANCY_MAIN_MENU_HEROES_SOURCE_IDENTITIES.items()
        if identity == source_identity
    ]
    require(len(variants) == 1, f"순정 HEROES identity가 다릅니다: {label}")
    variant = variants[0]
    if not has_buttons:
        require(variant == "expansion", f"외부 donor가 base HEROES에 전달됐습니다: {label}")
    heroes_payload = _render_fancy_main_menu_heroes(
        source_heroes,
        donors,
        label=f"{label}:{FANCY_MAIN_MENU_HEROES_RESOURCE_NAME}",
    )
    require(
        (len(heroes_payload), sha256_bytes(heroes_payload))
        == FANCY_MAIN_MENU_HEROES_OUTPUT_IDENTITIES[variant],
        f"장식 메인 메뉴 HEROES 출력 identity가 다릅니다: {label}:{variant}",
    )
    replacements[FANCY_MAIN_MENU_HEROES_RESOURCE_NAME] = heroes_payload
    return replacements


@dataclass(frozen=True)
class AggEntry:
    index: int
    name: str
    name_slot: bytes
    hash_word: int
    payload: bytes


@dataclass(frozen=True)
class AggArchive:
    entries: tuple[AggEntry, ...]
    raw: bytes

    def get(self, name: str) -> AggEntry:
        folded = name.upper()
        for entry in self.entries:
            if entry.name.upper() == folded:
                return entry
        raise FontBuildError(f"AGG 리소스가 없습니다: {name}")


def parse_agg(raw: bytes, *, label: str) -> AggArchive:
    require(len(raw) >= 2, f"AGG가 너무 짧습니다: {label}")
    count = struct.unpack_from("<H", raw, 0)[0]
    table_end = 2 + count * AGG_ENTRY_SIZE
    names_start = len(raw) - count * AGG_NAME_SIZE
    require(table_end <= names_start, f"AGG 테이블과 이름 영역이 겹칩니다: {label}")
    expected_offset = table_end
    seen: set[str] = set()
    entries: list[AggEntry] = []
    for index in range(count):
        hash_word, offset, size = struct.unpack_from("<III", raw, 2 + index * AGG_ENTRY_SIZE)
        require(offset == expected_offset and offset + size <= names_start, f"AGG 데이터 범위가 잘못됐습니다: {label}:{index}")
        slot = raw[names_start + index * AGG_NAME_SIZE : names_start + (index + 1) * AGG_NAME_SIZE]
        nul = slot.find(b"\0")
        try:
            name = slot[: AGG_NAME_SIZE if nul < 0 else nul].decode("ascii")
        except UnicodeDecodeError as exc:
            raise FontBuildError(f"AGG 이름이 ASCII가 아닙니다: {label}:{index}") from exc
        folded = name.upper()
        require(name and folded not in seen, f"AGG 이름이 비었거나 중복됐습니다: {label}:{index}")
        require(hash_word == agg_filename_hash(name), f"AGG 이름 hash가 맞지 않습니다: {label}:{name}")
        seen.add(folded)
        entries.append(AggEntry(index, name, slot, hash_word, raw[offset : offset + size]))
        expected_offset = offset + size
    require(expected_offset == names_start, f"AGG 데이터와 이름 영역 사이에 빈 공간이 있습니다: {label}")
    return AggArchive(tuple(entries), raw)


def repack_agg(archive: AggArchive, replacements: Mapping[str, bytes]) -> bytes:
    folded = {name.upper(): payload for name, payload in replacements.items()}
    known = {entry.name.upper() for entry in archive.entries}
    require(not (set(folded) - known), f"AGG에 없는 리소스 교체 요청입니다: {sorted(set(folded) - known)}")
    payloads = [folded.get(entry.name.upper(), entry.payload) for entry in archive.entries]
    offset = 2 + len(archive.entries) * AGG_ENTRY_SIZE
    offsets: list[int] = []
    for payload in payloads:
        offsets.append(offset)
        offset += len(payload)
        require(offset <= 0xFFFFFFFF, "AGG 전체 크기가 범위를 벗어났습니다")
    output = bytearray(struct.pack("<H", len(archive.entries)))
    for entry, data_offset, payload in zip(archive.entries, offsets, payloads):
        output.extend(struct.pack("<III", entry.hash_word, data_offset, len(payload)))
    for payload in payloads:
        output.extend(payload)
    for entry in archive.entries:
        output.extend(entry.name_slot)
    return bytes(output)


def changed_agg_resources(left_raw: bytes, right_raw: bytes, *, label: str) -> tuple[str, ...]:
    left = parse_agg(left_raw, label=f"{label}:left")
    right = parse_agg(right_raw, label=f"{label}:right")
    require(len(left.entries) == len(right.entries), f"AGG 리소스 수가 다릅니다: {label}")
    changed: list[str] = []
    for a, b in zip(left.entries, right.entries):
        require(
            (a.index, a.name, a.name_slot, a.hash_word) == (b.index, b.name, b.name_slot, b.hash_word),
            f"AGG 리소스 목록이 다릅니다: {label}:{a.index}",
        )
        if a.payload != b.payload:
            changed.append(a.name)
    return tuple(changed)


def make_localized_font_base(
    original_raw: bytes,
    patched_raw: bytes,
    *,
    keep_localized_resources: Iterable[str],
    expected_patched_changes: Iterable[str],
    label: str,
) -> bytes:
    original = parse_agg(original_raw, label=f"{label}:original")
    patched = parse_agg(patched_raw, label=f"{label}:patched")
    actual_changes = {name.upper() for name in changed_agg_resources(original_raw, patched_raw, label=label)}
    expected = {name.upper() for name in expected_patched_changes}
    require(actual_changes == expected, f"활성 AGG 변경 리소스 집합이 예상과 다릅니다: {label}: {sorted(actual_changes)}")
    keep = {name.upper() for name in keep_localized_resources}
    require(keep <= actual_changes, f"유지할 AGG 리소스가 활성 변경 집합에 없습니다: {label}: {sorted(keep - actual_changes)}")
    patched_by_name = {entry.name.upper(): entry.payload for entry in patched.entries}
    replacements = {entry.name: patched_by_name[entry.name.upper()] for entry in original.entries if entry.name.upper() in keep}
    result = repack_agg(original, replacements)
    result_changes = {name.upper() for name in changed_agg_resources(original_raw, result, label=f"{label}:base")}
    require(result_changes == keep, f"font/raster-free AGG 변경 집합이 잘못됐습니다: {label}: {sorted(result_changes)}")
    return result


def rebuild_agg_fonts(
    base_raw: bytes,
    rendered: RenderedFont,
    *,
    label: str,
    fancy_main_menu_donors: FancyMainMenuDonors | None = None,
) -> bytes:
    base = parse_agg(base_raw, label=f"{label}:base")
    rendered_mode = rendered.metadata.get("mode")
    require(
        rendered_mode in {None, "default", "custom"},
        f"렌더링 글꼴 모드가 잘못됐습니다: {label}:{rendered_mode!r}",
    )
    # Legacy/synthetic RenderedFont fixtures predate full face metadata and
    # retain the canonical contract.  Exact raster constants describe the old
    # Nanum default only; the bundled Iropke default and arbitrary user fonts
    # receive the same structural/ROI validation and record their output
    # identities transactionally instead.
    primary_metadata = rendered.metadata.get("primary")
    canonical_raster_identities = (
        rendered_mode is None
        or (
            rendered_mode == "default"
            and (
                not isinstance(primary_metadata, Mapping)
                or primary_metadata.get("sha256") == CANONICAL_RASTER_PRIMARY_SHA256
            )
        )
    )
    replacements: dict[str, bytes] = {}
    rebuilt_font_sprites: dict[str, tuple[Sprite, ...]] = {}
    for resource_name, additions in (("FONT.ICN", rendered.normal), ("SMALFONT.ICN", rendered.small)):
        resource = base.get(resource_name)
        legacy = parse_icn(resource.payload, label=f"{label}:{resource_name}")
        require(
            len(legacy.sprites) == LEGACY_SPRITE_COUNT,
            f"원본 {resource_name} sprite 수가 {LEGACY_SPRITE_COUNT}이 아닙니다: {len(legacy.sprites)}",
        )
        legacy_sprites = list(legacy.sprites)
        blank_at_sign = Sprite(0, 0, 1, 1, 0, b"\x81\x00\x80")
        _validate_sprite_payload(blank_at_sign)
        legacy_sprites[AT_SIGN_SPRITE_INDEX] = blank_at_sign
        filler = (legacy.sprites[0],) * FILLER_SPRITE_COUNT
        sprites = tuple(legacy_sprites) + filler + additions
        require(len(sprites) == FINAL_SPRITE_COUNT, f"최종 {resource_name} sprite 수가 맞지 않습니다")
        replacements[resource_name] = pack_icn(sprites)
        rebuilt_font_sprites[resource_name] = sprites

    recruit_entries = [entry for entry in base.entries if entry.name.upper() == RECRUIT_COST_RESOURCE_NAME]
    require(len(recruit_entries) <= 1, f"{RECRUIT_COST_RESOURCE_NAME}가 중복됐습니다: {label}")
    if recruit_entries:
        recruit = recruit_entries[0]
        replacements[recruit.name] = _localize_recruit_cost_label(
            recruit.payload,
            rebuilt_font_sprites["SMALFONT.ICN"],
            label=f"{label}:{recruit.name}",
            canonical_raster_identities=canonical_raster_identities,
        )

    replacements.update(
        _localize_image_ui_resources(
            base,
            rebuilt_font_sprites["FONT.ICN"],
            rendered.mapping,
            label=label,
            canonical_raster_identities=canonical_raster_identities,
        )
    )
    replacements.update(
        _localize_menu132_resources(
            base,
            rebuilt_font_sprites["FONT.ICN"],
            rendered.mapping,
            label=label,
            canonical_raster_identities=canonical_raster_identities,
        )
    )
    replacements.update(
        _localize_campaign_button_resources(
            base,
            rebuilt_font_sprites["FONT.ICN"],
            rendered.mapping,
            label=label,
            canonical_raster_identities=canonical_raster_identities,
        )
    )
    replacements.update(
        _localize_game_button_resources(
            base,
            rebuilt_font_sprites["FONT.ICN"],
            rendered.mapping,
            label=label,
            canonical_raster_identities=canonical_raster_identities,
        )
    )
    replacements.update(
        _localize_expansion_menu_resources(
            base,
            rebuilt_font_sprites["FONT.ICN"],
            rendered.mapping,
            label=label,
            canonical_raster_identities=canonical_raster_identities,
        )
    )
    replacements.update(
        _localize_embedded_ui_resources(
            base,
            replacements,
            rebuilt_font_sprites["FONT.ICN"],
            rendered.mapping,
            label=label,
            canonical_raster_identities=canonical_raster_identities,
        )
    )
    replacements.update(
        _localize_townwind_resource(
            base,
            rebuilt_font_sprites["FONT.ICN"],
            rebuilt_font_sprites["SMALFONT.ICN"],
            rendered.mapping,
            label=label,
            canonical_raster_identities=canonical_raster_identities,
        )
    )
    replacements.update(
        _localize_textbar_resource(
            base,
            rebuilt_font_sprites["SMALFONT.ICN"],
            rendered.mapping,
            label=label,
            canonical_raster_identities=canonical_raster_identities,
        )
    )
    output = repack_agg(base, replacements)
    candidate = parse_agg(output, label=f"{label}:candidate")
    changed = {name.upper() for name in changed_agg_resources(base_raw, output, label=f"{label}:font-rebuild")}
    expected_changes = {name.upper() for name in FONT_RESOURCE_NAMES}
    expected_changes.update(name.upper() for name in IMAGE_UI_RESOURCE_SOURCE_IDENTITIES if name in replacements)
    expected_changes.update(name.upper() for name in MENU132_RESOURCE_SOURCE_IDENTITIES if name in replacements)
    expected_changes.update(name.upper() for name in CAMPAIGN_BUTTON_RESOURCE_SOURCE_IDENTITIES if name in replacements)
    expected_changes.update(name.upper() for name in GAME_BUTTON_RESOURCE_SOURCE_IDENTITIES if name in replacements)
    expected_changes.update(name.upper() for name in EXPANSION_MENU_RESOURCE_SOURCE_IDENTITIES if name in replacements)
    expected_changes.update(name.upper() for name in EMBEDDED_UI_RESOURCE_SOURCE_IDENTITIES if name in replacements)
    if recruit_entries:
        expected_changes.add(RECRUIT_COST_RESOURCE_NAME)
    if TOWNWIND_RESOURCE_NAME in replacements:
        expected_changes.add(TOWNWIND_RESOURCE_NAME)
    if TEXTBAR_RESOURCE_NAME in replacements:
        expected_changes.add(TEXTBAR_RESOURCE_NAME)
    require(
        changed == expected_changes,
        f"허용된 폰트/버튼 외 AGG 리소스가 바뀌었습니다: {label}: {sorted(changed)}",
    )
    for resource_name in FONT_RESOURCE_NAMES:
        before = parse_icn(base.get(resource_name).payload, label=f"{label}:before:{resource_name}")
        after = parse_icn(candidate.get(resource_name).payload, label=f"{label}:after:{resource_name}")
        require(len(after.sprites) == FINAL_SPRITE_COUNT, f"생성된 {resource_name} sprite 수가 맞지 않습니다")
        require(
            after.sprites[:AT_SIGN_SPRITE_INDEX] == before.sprites[:AT_SIGN_SPRITE_INDEX]
            and after.sprites[AT_SIGN_SPRITE_INDEX + 1 : LEGACY_SPRITE_COUNT]
            == before.sprites[AT_SIGN_SPRITE_INDEX + 1 :],
            f"기존 {resource_name} sprite가 @ 칸 외에서 바뀌었습니다",
        )
        require(
            after.sprites[AT_SIGN_SPRITE_INDEX] == Sprite(0, 0, 1, 1, 0, b"\x81\x00\x80"),
            f"{resource_name}의 @ 칸이 투명 글리프가 아닙니다",
        )
        require(
            all(sprite == before.sprites[0] for sprite in after.sprites[LEGACY_SPRITE_COUNT:KOREAN_FIRST_INDEX]),
            f"{resource_name} filler가 원본 sprite 0과 다릅니다",
        )
    if canonical_raster_identities:
        for resource_name, expected_output in IMAGE_UI_RESOURCE_OUTPUT_IDENTITIES.items():
            if resource_name not in replacements:
                continue
            payload = candidate.get(resource_name).payload
            require(
                (len(payload), sha256_bytes(payload)) == expected_output,
                f"생성된 이미지 UI 리소스 검증이 실패했습니다: {label}:{resource_name}",
            )
        for resource_name, expected_output in CAMPAIGN_BUTTON_RESOURCE_OUTPUT_IDENTITIES.items():
            if resource_name not in replacements:
                continue
            payload = candidate.get(resource_name).payload
            require(
                (len(payload), sha256_bytes(payload)) == expected_output,
                f"생성된 캠페인 버튼 리소스 검증이 실패했습니다: {label}:{resource_name}",
            )
        for resource_name, expected_output in GAME_BUTTON_RESOURCE_OUTPUT_IDENTITIES.items():
            if resource_name not in replacements:
                continue
            payload = candidate.get(resource_name).payload
            require(
                (len(payload), sha256_bytes(payload)) == expected_output,
                f"생성된 게임 버튼 리소스 검증이 실패했습니다: {label}:{resource_name}",
            )
        for resource_name, expected_output in EXPANSION_MENU_RESOURCE_OUTPUT_IDENTITIES.items():
            if resource_name not in replacements:
                continue
            payload = candidate.get(resource_name).payload
            require(
                (len(payload), sha256_bytes(payload)) == expected_output,
                f"생성된 확장 메뉴 리소스 검증이 실패했습니다: {label}:{resource_name}",
            )
        for resource_name, expected_output in EMBEDDED_UI_RESOURCE_OUTPUT_IDENTITIES.items():
            if resource_name not in replacements:
                continue
            payload = candidate.get(resource_name).payload
            require(
                (len(payload), sha256_bytes(payload)) == expected_output,
                f"생성된 내장 UI 리소스 검증이 실패했습니다: {label}:{resource_name}",
            )
        if recruit_entries:
            payload = candidate.get(RECRUIT_COST_RESOURCE_NAME).payload
            require(
                (len(payload), sha256_bytes(payload))
                == (RECRUIT_COST_OUTPUT_SIZE, RECRUIT_COST_OUTPUT_SHA256),
                f"생성된 {RECRUIT_COST_RESOURCE_NAME} 검증이 실패했습니다: {label}",
            )
        if TOWNWIND_RESOURCE_NAME in replacements:
            payload = candidate.get(TOWNWIND_RESOURCE_NAME).payload
            require(
                (len(payload), sha256_bytes(payload)) == TOWNWIND_OUTPUT_IDENTITY,
                f"생성된 TOWNWIND 리소스 검증이 실패했습니다: {label}",
            )
        if TEXTBAR_RESOURCE_NAME in replacements:
            payload = candidate.get(TEXTBAR_RESOURCE_NAME).payload
            require(
                (len(payload), sha256_bytes(payload)) == TEXTBAR_OUTPUT_IDENTITY,
                f"생성된 TEXTBAR 리소스 검증이 실패했습니다: {label}",
            )
    return output
