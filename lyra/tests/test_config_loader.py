"""自定义配置目录不能替换默认配置或污染其他目录。"""

import tempfile
import unittest
from pathlib import Path

from lyra.config_loader import get_config_loader


class ConfigLoaderTests(unittest.TestCase):
    def test_cache_is_scoped_to_resolved_config_directory(self):
        default = get_config_loader()
        original_features = default.features
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            loaders = []
            for name, bit in (("first", 1), ("second", 2)):
                folder = root / name
                folder.mkdir()
                (folder / "features.toml").write_text(
                    f'[[features]]\nid = "{name}"\nbit = {bit}\n', encoding="utf-8"
                )
                loader = get_config_loader(folder)
                loaders.append(loader)
                self.assertEqual(loader.features[0].id, name)
                self.assertEqual(loader.features[0].name, "")
                self.assertIs(loader, get_config_loader(folder / "."))
                self.assertIs(loader.features, loader.features)
            self.assertIsNot(loaders[0], loaders[1])
            self.assertIs(get_config_loader(), default)
            self.assertIs(get_config_loader().features, original_features)
