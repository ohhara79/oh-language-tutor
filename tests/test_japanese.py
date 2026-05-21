"""Tests for ``tutor.japanese`` — shinjitai ↔ kyūjitai conversion."""

from __future__ import annotations

from tutor.japanese import _TABLE, relevant_kyujitai_mappings, to_kyujitai_template


def test_table_excludes_meta_keys() -> None:
    assert all(not k.startswith('_') for k in _TABLE)
    assert _TABLE


def test_table_keys_are_single_characters() -> None:
    assert all(len(k) == 1 for k in _TABLE)


def test_table_values_are_non_empty_lists() -> None:
    assert all(isinstance(v, list) and v for v in _TABLE.values())


def test_to_kyujitai_unambiguous_substitution() -> None:
    assert to_kyujitai_template('学校') == '學校'


def test_to_kyujitai_long_tail_kanji() -> None:
    # The Tōyō simplifications the model is least reliable about.
    assert to_kyujitai_template('渋い') == '澁い'
    assert to_kyujitai_template('缶') == '罐'
    assert to_kyujitai_template('芸術') == '藝術'
    assert to_kyujitai_template('観光') == '觀光'


def test_to_kyujitai_ambiguous_emits_brackets() -> None:
    # 弁 maps to 4 different kyūjitai by meaning.
    assert to_kyujitai_template('弁護士') == '[辨|瓣|辯|辮]護士'
    assert to_kyujitai_template('花弁') == '花[辨|瓣|辯|辮]'


def test_to_kyujitai_preserves_unmapped_characters() -> None:
    # Kana and non-shinjitai kanji pass through verbatim.
    assert to_kyujitai_template('学校に行きます') == '學校に行きます'


def test_to_kyujitai_returns_none_when_nothing_converts() -> None:
    assert to_kyujitai_template('こんにちは') is None
    assert to_kyujitai_template('カタカナ') is None
    # Pure kanji line whose characters have no kyūjitai variant.
    assert to_kyujitai_template('人山川') is None


def test_to_kyujitai_empty_string() -> None:
    assert to_kyujitai_template('') is None


# Pinned regression guard: a curated set of well-attested Tōyō/Jōyō
# simplifications that future edits must not silently drop. Add to this
# list when new entries are added to the JSON.
_PINNED_ENTRIES: list[tuple[str, str]] = [
    ('学', '學'),
    ('国', '國'),
    ('体', '體'),
    ('当', '當'),
    ('会', '會'),
    ('関', '關'),
    ('経', '經'),
    ('売', '賣'),
    ('読', '讀'),
    ('観', '觀'),
    ('図', '圖'),
    ('楽', '樂'),
    ('数', '數'),
    ('万', '萬'),
    ('円', '圓'),
    ('来', '來'),
    ('内', '內'),
    ('広', '廣'),
    ('変', '變'),
    ('舎', '舍'),
    ('真', '眞'),
    ('単', '單'),
    ('将', '將'),
    ('徴', '徵'),
    ('殻', '殼'),
    ('厨', '廚'),
    ('即', '卽'),
    ('既', '旣'),
    ('堕', '墮'),
    ('青', '靑'),
    ('隷', '隸'),
    ('窓', '窗'),
    ('寛', '寬'),
    ('済', '濟'),
    ('温', '溫'),
    ('砕', '碎'),
    ('継', '繼'),
    ('縁', '緣'),
    ('渋', '澁'),
    ('缶', '罐'),
    ('芸', '藝'),
    ('観', '觀'),
    ('関', '關'),
    ('経', '經'),
    ('戦', '戰'),
    ('党', '黨'),
    ('体', '體'),
    # Second-pass audit additions:
    ('参', '參'),
    ('鴎', '鷗'),
    ('鴬', '鶯'),
    ('鯵', '鰺'),
    ('嘱', '囑'),
    ('醗', '醱'),
    ('賎', '賤'),
    ('晋', '晉'),
    ('壷', '壺'),
    ('屏', '屛'),
    ('掴', '摑'),
    ('掻', '搔'),
    ('剥', '剝'),
    ('遥', '遙'),
    # Third-pass audit additions (jōyō kanji whose Kangxi form lives at a
    # distinct Unicode code point; the 2010 jōyō appendix and one
    # original-jōyō miss surfaced these):
    ('没', '沒'),
    ('頬', '頰'),
    ('餅', '餠'),
    ('痩', '瘦'),
    ('嘘', '噓'),
    ('喩', '喻'),
    ('填', '塡'),
    ('挿', '插'),
    # Fourth-pass audit additions (hyōgai 表外漢字字体表 簡易慣用字体 and
    # two non-list jinmeiyō/jōyō-adjacent pairs common in subtitles):
    ('唖', '啞'),
    ('焔', '焰'),
    ('噛', '嚙'),
    ('侠', '俠'),
    ('躯', '軀'),
    ('鹸', '鹼'),
    ('麹', '麴'),
    ('桧', '檜'),
    ('醤', '醬'),
    ('蝋', '蠟'),
    ('砿', '礦'),
    ('蕊', '蘂'),
    ('騨', '驒'),
    ('弯', '彎'),
    ('繍', '繡'),
    ('撹', '攪'),
    ('諌', '諫'),
    ('凛', '凜'),
    ('篭', '籠'),
]


def test_table_contains_pinned_common_entries() -> None:
    missing = [(s, k) for s, k in _PINNED_ENTRIES if _TABLE.get(s) != [k] and k not in (_TABLE.get(s) or [])]
    assert not missing, f'pinned shinjitai→kyūjitai entries are missing or have changed: {missing}'


def test_to_kyujitai_newly_added_entries() -> None:
    # Spot-check the kanji that previously dropped from the Variant row.
    assert to_kyujitai_template('来年') == '來年'
    assert to_kyujitai_template('広島') == '廣島'
    assert to_kyujitai_template('変化') == '變化'
    assert to_kyujitai_template('真実') == '眞實'
    assert to_kyujitai_template('単純') == '單純'
    assert to_kyujitai_template('将棋') == '將棋'
    assert to_kyujitai_template('温度') == '溫度'
    assert to_kyujitai_template('国内') == '國內'
    # Second-pass audit spot-checks.
    assert to_kyujitai_template('参加') == '參加'
    assert to_kyujitai_template('鴎外') == '鷗外'
    # Third-pass audit spot-checks.
    assert to_kyujitai_template('没頭') == '沒頭'
    assert to_kyujitai_template('頬骨') == '頰骨'
    assert to_kyujitai_template('煎餅') == '煎餠'
    assert to_kyujitai_template('痩身') == '瘦身'
    assert to_kyujitai_template('嘘つき') == '噓つき'
    assert to_kyujitai_template('比喩') == '比喻'
    assert to_kyujitai_template('補填') == '補塡'
    assert to_kyujitai_template('挿入') == '插入'
    # Fourth-pass audit spot-checks (hyōgai 表外漢字字体表 additions).
    assert to_kyujitai_template('蝋燭') == '蠟燭'
    assert to_kyujitai_template('石鹸') == '石鹼'
    assert to_kyujitai_template('飛騨') == '飛驒'
    assert to_kyujitai_template('刺繍') == '刺繡'
    assert to_kyujitai_template('醤油') == '醬油'
    assert to_kyujitai_template('撹拌') == '攪拌'
    assert to_kyujitai_template('任侠') == '任俠'
    # 台 maps to 臺 elsewhere in the table, so the whole phrase rewrites.
    assert to_kyujitai_template('桧舞台') == '檜舞臺'


def test_relevant_kyujitai_mappings_filters_by_input() -> None:
    mappings = relevant_kyujitai_mappings('学校に行きます')
    assert mappings == {'学': ['學']}


def test_relevant_kyujitai_mappings_preserves_multi_candidates() -> None:
    mappings = relevant_kyujitai_mappings('弁護士')
    assert mappings == {'弁': ['辨', '瓣', '辯', '辮']}


def test_relevant_kyujitai_mappings_deduplicates() -> None:
    # Repeated shinjitai → one entry, in first-appearance order.
    mappings = relevant_kyujitai_mappings('学校で学ぶ')
    assert list(mappings) == ['学']


def test_relevant_kyujitai_mappings_preserves_first_appearance_order() -> None:
    mappings = relevant_kyujitai_mappings('国家学園')
    assert list(mappings) == ['国', '学']


def test_relevant_kyujitai_mappings_empty_for_no_match() -> None:
    assert relevant_kyujitai_mappings('こんにちは') == {}
    assert relevant_kyujitai_mappings('人山川') == {}
    assert relevant_kyujitai_mappings('') == {}
