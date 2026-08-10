"""测试上游汉化版本检查逻辑。"""

import re
import unittest

from lyra.updater import check_chs_update


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data

    def raise_for_status(self):
        pass


class FakeSession:
    """按 URL 片段匹配的假 Session，便于注入响应或异常。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        for i, (fragment, value) in enumerate(self.responses):
            if fragment in url:
                del self.responses[i]
                if isinstance(value, Exception):
                    raise value
                return value
        raise AssertionError(f"意外的 URL: {url}")


class TestCheckChsUpdate(unittest.TestCase):
    SOURCE = "Eltirosto/Degrees-of-Lewdity-Chinese-Localization"
    OWNER = "YaleCheng404"
    REPO = "Lyra"

    def _session(self, origin_tag, lyra_tag, with_lyra=True):
        responses = [("Eltirosto", FakeResponse({"tag_name": origin_tag}))]
        if with_lyra:
            responses.append(("YaleCheng404", FakeResponse({"tag_name": lyra_tag})))
        else:
            responses.append(("YaleCheng404", RuntimeError("首次发布无 release")))
        return FakeSession(responses)

    def test_need_update_when_upstream_newer(self):
        session = self._session("v0.5.10.12-chs-1.0.8a", "v0.5.10.11-1.0.8a-0809")
        result = check_chs_update(self.SOURCE, self.OWNER, self.REPO, session=session)
        self.assertTrue(result["need_update"])
        self.assertEqual(result["game_ver"], "0.5.10.12")
        self.assertEqual(result["chs_ver"], "1.0.8a")
        self.assertTrue(result["new_tag"].startswith("v0.5.10.12-1.0.8a-"))

    def test_no_update_when_already_built(self):
        session = self._session("v0.5.10.12-chs-1.0.8a", "v0.5.10.12-1.0.8a-0810")
        result = check_chs_update(self.SOURCE, self.OWNER, self.REPO, session=session)
        self.assertFalse(result["need_update"])

    def test_first_release_triggers_update(self):
        session = self._session("v0.5.10.12-chs-1.0.8a", None, with_lyra=False)
        result = check_chs_update(self.SOURCE, self.OWNER, self.REPO, session=session)
        self.assertTrue(result["need_update"])
        self.assertEqual(result["lyra_tag"], "")

    def test_unparseable_upstream_tag_raises(self):
        session = FakeSession(
            [
                ("Eltirosto", FakeResponse({"tag_name": "release-999"})),
                ("YaleCheng404", FakeResponse({"tag_name": "v0.5.10.11-1.0.8a-0809"})),
            ]
        )
        with self.assertRaises(ValueError):
            check_chs_update(self.SOURCE, self.OWNER, self.REPO, session=session)

    def test_new_tag_matches_build_regex(self):
        # new_tag 必须能通过 build.yaml 的 release_tag 校验正则
        pattern = (
            r"^v[0-9]+(\.[0-9]+){3}-"
            r"[0-9]+(\.[0-9]+){2}[0-9A-Za-z]*-[0-9]{4}$"
        )
        session = self._session("v0.5.10.12-chs-1.0.8a", "v0.5.10.11-1.0.8a-0809")
        result = check_chs_update(self.SOURCE, self.OWNER, self.REPO, session=session)
        self.assertRegex(result["new_tag"], pattern)


if __name__ == "__main__":
    unittest.main()
