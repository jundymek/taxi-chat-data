from analysis.measure_partitioning import format_report


def test_format_report_shows_before_after_and_reduction():
    report = format_report(part_bytes=100_000_000, unpart_bytes=500_000_000)
    assert "500,000,000" in report          # unpartitioned (before)
    assert "100,000,000" in report          # partitioned (after)
    assert "80.0%" in report                # reduction = 1 - 100/500
