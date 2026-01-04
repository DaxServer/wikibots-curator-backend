import json
from pathlib import Path

from curator.app.sdc_v2 import build_statements_from_sdc_v2


def _load_sdc_claim_fixtures():
    path = Path(__file__).resolve().parent / "fixtures" / "sdc_claims.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_build_statements_from_sdc_v2_matches_v1_fixtures():
    fixtures = _load_sdc_claim_fixtures()
    for fixture in fixtures:
        statements = build_statements_from_sdc_v2(fixture["sdc_v2"])
        dumped = [
            s.model_dump(mode="json", by_alias=True, exclude_none=True)
            for s in statements
        ]
        assert dumped == fixture["claims"]
