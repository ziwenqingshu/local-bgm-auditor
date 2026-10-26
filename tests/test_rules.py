"""README「审核规则」表和区间合并规则的逐条验证。"""

import pytest

from bgm_audit.models import Detection, EngineError
from bgm_audit.review import (
    CONFLICT_REASON,
    authorization_status,
    identity,
    merge_detections,
    overall_status,
    review_detections,
)

PURPOSE = "漫剧商业发布"
VERIFIED_LICENSE = dict(
    status="已登记授权",
    verified=True,
    coverage="覆盖已选用途",
    purposes=[PURPOSE],
    evidence="授权书.pdf",
)


def det(start=0.0, end=10.0, *, engine="audfprint", track="t1", title="星河", artist="甲", index=0, lic=None):
    return Detection(
        engine,
        track,
        title,
        artist,
        start,
        end,
        "估计",
        [dict(segment_index=index, window_start=start, window_end=end)],
        license_snapshot=dict(lic or {}),
    )


# ---------------------------------------------------------------- 授权规则表


@pytest.mark.parametrize(
    ("case", "detections", "errors", "expected"),
    [
        ("命中音乐，没有满足条件的授权材料", [det()], [], "待核验"),
        ("本地命中，已核实 + 依据 + 覆盖当前用途", [det(lic=VERIFIED_LICENSE)], [], "授权已核验"),
        (
            "登记的授权明确不覆盖当前使用",
            [det(lic=dict(VERIFIED_LICENSE, coverage="明确不覆盖"))],
            [],
            "不通过",
        ),
        ("成功扫描但没有命中", [], [], "未检出，仍需复核"),
        ("任意引擎异常", [], [EngineError("shazam", "网络失败", "离线")], "识别不完整"),
        ("曲库为空", [], [EngineError("audfprint", "曲库为空", "空")], "识别不完整"),
        (
            "不同引擎在重叠区间识别出不同歌曲",
            [det(lic=VERIFIED_LICENSE), det(2, 8, engine="shazam", track="k", title="远山")],
            [],
            "人工复审",
        ),
    ],
)
def test_readme_rules_table(case, detections, errors, expected):
    _, status = review_detections(detections, PURPOSE, errors)
    assert status == expected, case


def test_rejection_outranks_manual_review_and_errors():
    rejected = det(lic=dict(VERIFIED_LICENSE, coverage="明确不覆盖"))
    conflict = det(0, 10, engine="shazam", track="k", title="远山")
    reviewed, status = review_detections([rejected, conflict], PURPOSE, [EngineError("shazam", "超时", "x")])
    assert status == "不通过"
    # 明确拒绝不能被冲突降级成人工复审；另一方仍提示人工复审。
    assert reviewed[0].status == "不通过"
    assert reviewed[1].status == "人工复审" and reviewed[1].reason == CONFLICT_REASON


def test_manual_review_outranks_errors():
    pair = [det(), det(0, 5, engine="shazam", track="k", title="远山")]
    assert review_detections(pair, PURPOSE, [EngineError("shazam", "超时", "x")])[1] == "人工复审"


def test_errors_outrank_found_and_verified():
    assert review_detections([det(lic=VERIFIED_LICENSE)], PURPOSE, [EngineError("a", "b", "c")])[1] == ("识别不完整")


def test_mixed_verified_and_pending_is_pending():
    found = [det(lic=VERIFIED_LICENSE), det(12, 20, track="t2", title="远山")]
    assert review_detections(found, PURPOSE, [])[1] == "待核验"


def test_online_hits_never_count_as_verified():
    online = det(engine="shazam", lic=VERIFIED_LICENSE)
    reviewed, status = review_detections([online], PURPOSE, [])
    assert status == "待核验" and "在线识别" in reviewed[0].reason


def test_same_song_from_both_engines_is_not_a_conflict():
    local = det(title="星河 (Remix)", artist="甲")
    online = det(engine="shazam", track="k", title="星河 Remix", artist="甲")
    _, status = review_detections([local, online], PURPOSE, [])
    assert status == "待核验"
    assert identity(local) == identity(online)


def test_touching_but_not_overlapping_ranges_are_not_conflicts():
    found = [det(0, 10), det(10, 20, engine="shazam", track="k", title="远山")]
    assert review_detections(found, PURPOSE, [])[1] == "待核验"


def test_same_engine_overlapping_songs_are_reported_separately():
    found = [det(0, 10, track="t1"), det(5, 15, track="t2", title="远山")]
    reviewed, status = review_detections(found, PURPOSE, [])
    assert status == "待核验" and len(reviewed) == 2


def test_review_does_not_mutate_input():
    original = det()
    review_detections([original], PURPOSE, [])
    assert original.status == "待核验" and original.reason == "识别结果需与授权材料核对"


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({}, "授权已核验"),
        ({"verified": False}, "待核验"),
        ({"verified": "false"}, "待核验"),  # 手工编辑 JSON 的字符串不应被当成 True
        ({"evidence": "   "}, "待核验"),
        ({"status": "授权待核实"}, "待核验"),
        ({"coverage": "待核实"}, "待核验"),
        ({"purposes": ["电影发布"]}, "待核验"),
        ({"purposes": [" 漫剧商业发布 "]}, "授权已核验"),
        ({"coverage": "明确不覆盖", "verified": False}, "不通过"),
    ],
)
def test_authorization_status_conditions(change, expected):
    assert authorization_status(dict(VERIFIED_LICENSE, **change), PURPOSE)[0] == expected


def test_authorization_purpose_is_trimmed_but_otherwise_exact():
    assert authorization_status(VERIFIED_LICENSE, f"  {PURPOSE}\n")[0] == "授权已核验"
    assert authorization_status(VERIFIED_LICENSE, "漫剧商业")[0] == "待核验"
    assert authorization_status({}, PURPOSE)[0] == "待核验"


def test_overall_status_priority_order():
    assert overall_status({"不通过", "人工复审"}, True, True) == "不通过"
    assert overall_status({"人工复审", "授权已核验"}, True, True) == "人工复审"
    assert overall_status({"授权已核验"}, True, True) == "识别不完整"
    assert overall_status(set(), False, False) == "未检出，仍需复核"
    assert overall_status({"授权已核验"}, False, True) == "授权已核验"
    assert overall_status({"授权已核验", "待核验"}, False, True) == "待核验"


# ---------------------------------------------------------------- 合并规则


def test_merge_within_gap_tolerance_and_adjacent_windows():
    merged = merge_detections([det(0, 10, index=0), det(11.5, 20, index=1)], gap=1.5)
    assert [(d.start, d.end) for d in merged] == [(0, 20)]


def test_merge_respects_gap_boundary():
    assert len(merge_detections([det(0, 10, index=0), det(11.6, 20, index=1)], gap=1.5)) == 2
    assert len(merge_detections([det(0, 10, index=0), det(10, 20, index=1)], gap=0)) == 1


def test_merge_never_crosses_engines_or_tracks():
    found = [det(0, 10), det(5, 15, engine="shazam"), det(5, 15, track="t2", title="远山")]
    assert len(merge_detections(found)) == 3


def test_merge_sorts_unordered_input_and_keeps_all_evidence():
    found = [det(12, 24, index=2), det(0, 12, index=0), det(6, 18, index=1)]
    merged = merge_detections(found)
    assert len(merged) == 1
    assert [e["segment_index"] for e in merged[0].evidence] == [0, 1, 2]


def test_merge_does_not_bridge_a_missed_window():
    # 第 1 个窗口未命中（或失败），第 0 与第 2 窗口即使时间相接也不合并。
    assert len(merge_detections([det(0, 15, index=0), det(15, 30, index=2)])) == 2


def test_merge_repeated_song_after_long_gap_stays_separate():
    assert len(merge_detections([det(0, 10, index=0), det(40, 50, index=1)])) == 2


def test_merge_does_not_mutate_input():
    first, second = det(0, 10, index=0), det(9, 20, index=1)
    merge_detections([first, second])
    assert (first.end, len(first.evidence)) == (10, 1)


def test_merge_result_is_ordered_by_start():
    found = [det(30, 40, track="b", title="B"), det(0, 10, track="a", title="A")]
    assert [d.title for d in merge_detections(found)] == ["A", "B"]


def test_merge_empty():
    assert merge_detections([]) == []
