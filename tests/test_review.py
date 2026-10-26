from bgm_audit.models import Detection, EngineError
from bgm_audit.review import authorization_status, merge_detections, review_detections


def hit(start=0, end=12, index=0, engine="shazam", title="星河"):
    return Detection(
        engine,
        "track-one",
        title,
        "创作者",
        start,
        end,
        "估计",
        [dict(segment_index=index, window_start=start, window_end=end)],
    )


def test_consecutive_slices_merge_and_keep_original_windows():
    merged = merge_detections([hit(), hit(6, 18, 1), hit(12, 24, 2)])
    assert len(merged) == 1
    assert (merged[0].start, merged[0].end) == (0, 24)
    assert [e["window_start"] for e in merged[0].evidence] == [0, 6, 12]
    assert merged[0].range_kind == "估计"


def test_nonconsecutive_same_song_does_not_bridge_failed_or_different_slice():
    assert len(merge_detections([hit(), hit(12, 24, 2)])) == 2
    assert len(merge_detections([hit(), hit(30, 42, 1)])) == 2


def test_authorization_requires_evidence_verified_and_exact_purpose():
    license_info = dict(
        status="已登记授权",
        verified=True,
        coverage="覆盖已选用途",
        purposes=["漫剧商业发布"],
        evidence="授权书.pdf",
    )
    assert authorization_status(license_info, "漫剧商业发布")[0] == "授权已核验"
    assert authorization_status(license_info, "电影发布")[0] == "待核验"
    assert authorization_status(dict(license_info, verified=False), "漫剧商业发布")[0] == "待核验"
    assert authorization_status(dict(license_info, evidence=""), "漫剧商业发布")[0] == "待核验"
    assert authorization_status(dict(license_info, coverage="明确不覆盖"), "漫剧商业发布")[0] == "不通过"


def test_cross_engine_conflict_requires_human_review():
    reviewed, status = review_detections([hit(engine="audfprint"), hit(title="远山")], "发布", [])
    assert status == "人工复审"
    assert all(d.status == "人工复审" for d in reviewed)


def test_unmatched_and_failed_are_different():
    assert review_detections([], "发布", [])[1] == "未检出，仍需复核"
    assert review_detections([], "发布", [EngineError("shazam", "网络失败", "离线")])[1] == "识别不完整"
