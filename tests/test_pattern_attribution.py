from smartmoney_cub_harness.trader.patterns import attribute_patterns


def toy_trip(**extra):
    return {"round_trip_id": "RT-TOY", "account_id": "toy-account", "symbol": "TOY",
            "entry_time": "2026-08-03T10:00:00+00:00", "exit_time": "2026-08-03T10:10:00+00:00",
            "holding_days": 0, "entry_price": 31, "side": "LONG", "currency": "USD",
            "matched_lots": [{"lot_fill_id": "TOY-BUY", "quantity": 1}], **extra}


def test_orders_alone_show_horizon_but_do_not_invent_a_trend_strategy():
    result = attribute_patterns({"round_trips": [toy_trip()]}, trades=[])
    labels = {c["label"] for c in result["candidates"]}
    assert "brief_intraday" in labels
    assert "unknown_entry_shape" in labels
    assert "trend_following" not in labels
    assert result["profile"]["data_quality"] == "small_sample"
    assert all(c["status"] != "confirmed" for c in result["candidates"])


def test_missing_time_does_not_become_scalping():
    trip = toy_trip(entry_time="2026-08-03", exit_time="2026-08-03")
    result = attribute_patterns({"round_trips": [trip]}, trades=[])
    labels = {c["label"] for c in result["candidates"]}
    assert "intraday" in labels
    assert "brief_intraday" not in labels


def test_verified_pre_entry_context_can_support_a_candidate_but_never_confirms():
    context = {"data_source": "toy_point_in_time_archive", "data_quality": "point_in_time",
               "available_at": "2026-08-03T09:59:00+00:00",
               "decision_time": "2026-08-03T10:00:00+00:00",
               "bars": [{"available_at": f"2026-07-{i + 1:02d}T21:00:00+00:00", "close": 10 + i, "high": 10.5 + i, "low": 9.5 + i}
                        for i in range(20)]}
    raw = {"trade_id": "TOY-BUY", "provenance": {"entry_context": context}}
    result = attribute_patterns({"round_trips": [toy_trip()]}, trades=[raw])
    candidates = [c for c in result["candidates"] if c["axis"] == "entry_shape"]
    assert {c["label"] for c in candidates} >= {"trend_following", "breakout"}
    assert all(c["status"] == "inferred" for c in candidates)
    assert all(c["evidence"] for c in candidates)
    context["available_at"] = "2026-08-04T00:00:00+00:00"
    refused = attribute_patterns({"round_trips": [toy_trip()]}, trades=[raw])
    assert {c["label"] for c in refused["candidates"] if c["axis"] == "entry_shape"} == {"unknown_entry_shape"}
    assert any("future" in " ".join(c["missing_data"]) for c in refused["candidates"])


def test_candidates_are_stable_and_contain_observation_provenance():
    first = attribute_patterns({"round_trips": [toy_trip()]}, trades=[])
    second = attribute_patterns({"round_trips": [toy_trip()]}, trades=[])
    assert [c["pattern_id"] for c in first["candidates"]] == [c["pattern_id"] for c in second["candidates"]]
    for candidate in first["candidates"]:
        for key in ("invalidation", "time_stop", "give_up", "data_source", "available_at", "data_quality", "version"):
            assert candidate[key]
