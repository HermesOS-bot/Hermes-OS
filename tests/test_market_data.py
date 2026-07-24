import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from core.models import Candle
from download_market_data import validate_candles
from infrastructure.tbank_market_data import quotation_to_float


class QuotationTests(unittest.TestCase):
    def test_converts_units_and_nano(self):
        self.assertAlmostEqual(
            quotation_to_float({"units": "64193", "nano": 200_000_000}),
            64193.2,
        )


class CandleValidationTests(unittest.TestCase):
    def test_sorts_valid_candles(self):
        later = Candle(
            timestamp=datetime(2026, 7, 24, 11, tzinfo=timezone.utc),
            open=101,
            high=103,
            low=100,
            close=102,
            volume=10,
        )
        earlier = Candle(
            timestamp=datetime(2026, 7, 24, 10, tzinfo=timezone.utc),
            open=100,
            high=102,
            low=99,
            close=101,
            volume=12,
        )
        self.assertEqual(validate_candles([later, earlier]), [earlier, later])

    def test_rejects_duplicate_timestamps(self):
        candle = Candle(
            timestamp=datetime(2026, 7, 24, 10, tzinfo=timezone.utc),
            open=100,
            high=102,
            low=99,
            close=101,
            volume=12,
        )
        with self.assertRaises(ValueError):
            validate_candles([candle, candle])


if __name__ == "__main__":
    unittest.main()
