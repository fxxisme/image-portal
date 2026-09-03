import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas import OpenAIModerationRequest
from app.services.moderation import MODERATION_CATEGORIES, UpstreamError, _parse_results


class ModerationParsingTests(unittest.TestCase):
    def _completion(self, result: dict) -> dict:
        return {"choices": [{"text": json.dumps({"results": [result]})}]}

    def test_normalizes_a_valid_completion(self) -> None:
        categories = {name: False for name in MODERATION_CATEGORIES}
        categories["violence"] = True
        result = _parse_results(
            self._completion(
                {
                    "categories": categories,
                    "category_scores": {name: 0.2 for name in MODERATION_CATEGORIES},
                }
            ),
            1,
        )

        self.assertTrue(result[0]["flagged"])
        self.assertTrue(result[0]["categories"]["violence"])
        self.assertEqual(result[0]["category_scores"]["violence"], 0.2)

    def test_rejects_incomplete_categories(self) -> None:
        with self.assertRaises(UpstreamError):
            _parse_results(
                self._completion(
                    {
                        "categories": {"violence": False},
                        "category_scores": {"violence": 0.0},
                    }
                ),
                1,
            )

    def test_accepts_text_batch_and_rejects_empty_item(self) -> None:
        self.assertEqual(OpenAIModerationRequest(input=["a", "b"]).input_items(), ["a", "b"])
        with self.assertRaises(ValueError):
            OpenAIModerationRequest(input=["a", ""])


if __name__ == "__main__":
    unittest.main()
