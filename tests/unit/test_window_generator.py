import unittest

from core.simulation.historical.window_generator import generate_windows
from tests.market_data_test_fixtures import small_dataset


class GenerateWindowsTest(unittest.TestCase):
    def test_generates_all_fitting_start_years(self) -> None:
        # データセットは2001-2004年（4年分）。window_length=2なら開始年は2001,2002,2003の3通り。
        windows = generate_windows(small_dataset(), window_length=2)
        self.assertEqual(windows, [2001, 2002, 2003])

    def test_window_length_equal_to_dataset_length_yields_single_window(self) -> None:
        windows = generate_windows(small_dataset(), window_length=4)
        self.assertEqual(windows, [2001])

    def test_window_longer_than_dataset_yields_no_windows(self) -> None:
        windows = generate_windows(small_dataset(), window_length=5)
        self.assertEqual(windows, [])


if __name__ == "__main__":
    unittest.main()
