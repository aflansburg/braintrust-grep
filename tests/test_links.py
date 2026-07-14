from __future__ import annotations

from braintrust_grep.links import span_deeplink


def test_deeplink_uses_r_and_s():
    url = span_deeplink("FictionalAIOrg", "patient-document-processor", "PID", "ROOT", "SPAN")
    assert url.startswith(
        "https://www.braintrust.dev/app/FictionalAIOrg/p/patient-document-processor/trace?"
    )
    assert "r=ROOT" in url
    assert "s=SPAN" in url
    assert "object_id=PID" in url
    assert "tvt=trace" in url
