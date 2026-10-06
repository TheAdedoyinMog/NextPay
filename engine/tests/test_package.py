import nextpay_engine


def test_engine_exposes_version() -> None:
    assert nextpay_engine.ENGINE_VERSION == "0.1.0"
