import unittest
from unittest.mock import Mock, patch

from config import LiveResponseText


class LiveResponseTextTests(unittest.TestCase):
    def test_stops_live_indicator_and_prints_each_delta_verbatim(self) -> None:
        live = Mock()
        display = LiveResponseText(live)

        with patch("config.console.print") as print_text:
            display.write_delta("# large ")
            display.write_delta("response")
            display.finish()

        live.stop.assert_called_once_with()
        self.assertEqual(
            [call.args for call in print_text.call_args_list],
            [
                ("# large ",),
                ("response",),
                (),
            ],
        )
        self.assertEqual(
            print_text.call_args_list[0].kwargs,
            {"end": "", "markup": False, "highlight": False},
        )

    def test_finish_does_not_print_for_empty_response(self) -> None:
        live = Mock()
        display = LiveResponseText(live)

        with patch("config.console.print") as print_text:
            display.finish()

        live.stop.assert_not_called()
        print_text.assert_not_called()


if __name__ == "__main__":
    unittest.main()
