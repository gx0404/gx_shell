import unittest
from pathlib import Path

import gx_shell_build as build


class BuildDriverTests(unittest.TestCase):
    def test_safe_path_rejects_unsafe_paths(self):
        with self.assertRaises(build.BuildError):
            build.safe_path(Path("D:/gx build/run"))
        with self.assertRaises(build.BuildError):
            build.safe_path(Path("D:/gx/../run"))

    def test_power_shell_mapping_is_quoted(self):
        value = build.ps_map({"herdr": r"D:\gx\herdr", "ohmyzsh": r"D:\gx\ohmyzsh"})
        self.assertEqual(value, "@{herdr='D:\\gx\\herdr';ohmyzsh='D:\\gx\\ohmyzsh'}")

    def test_real_lock_has_three_independent_components(self):
        lock = build.read_lock(build.ROOT / "components.lock.json")
        self.assertEqual(set(lock["components"]), {"herdr", "ohmyzsh", "wezterm"})
        for name, entry in lock["components"].items():
            self.assertEqual(entry["repository"], "gx0404/" + name)
            self.assertEqual(entry["branch"], "gx")
            self.assertRegex(entry["revision"], r"^[0-9a-f]{40}$")

    def test_help_is_available_without_sources_or_tools(self):
        with self.assertRaises(SystemExit) as error:
            build.main(["--help"])
        self.assertEqual(error.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
