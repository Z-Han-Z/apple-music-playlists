"""Offline release contracts: installed surfaces and CI must match, never access accounts."""
import json
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch

import am_paths
import netease_mcp_server as nc

ROOT = Path(__file__).resolve().parent.parent


class Release160Tests(unittest.TestCase):
    def container_assertion(self):
        workflow = (ROOT / '.github/workflows/container.yml').read_text(encoding='utf-8')
        match = re.search(r"NC_RESPONSE=.*python -c '([^']+)'", workflow)
        self.assertIsNotNone(match)
        return compile(match.group(1), '<container-ci-contract>', 'exec')

    def test_container_checks_actual_server_tools(self):
        assertion = self.container_assertion()
        rows = [{'result': {'serverInfo': {'version': am_paths.VERSION}}},
                {'result': {'tools': nc.TOOLS}}]
        with patch.dict(os.environ, {'NC_RESPONSE': '\n'.join(map(json.dumps, rows))}):
            exec(assertion, {})

    def test_container_rejects_old_18_tool_surface(self):
        assertion = self.container_assertion()
        rows = [{'result': {'serverInfo': {'version': am_paths.VERSION}}},
                {'result': {'tools': nc.TOOLS[:18]}}]
        with patch.dict(os.environ, {'NC_RESPONSE': '\n'.join(map(json.dumps, rows))}):
            with self.assertRaises(AssertionError):
                exec(assertion, {})

    def test_public_docs_no_longer_claim_unpublished_beta(self):
        files = list(ROOT.glob('README*.md')) + [ROOT / 'docs/netease-port.md',
                    ROOT / 'docs/client-setup.md', ROOT / 'docs/client-setup.zh-CN.md',
                    ROOT / 'beta/START_HERE_EN.md', ROOT / 'beta/START_HERE_ZH_CN.txt']
        for path in files:
            with self.subTest(path=path.name):
                self.assertNotIn('1.6.0b1', path.read_text(encoding='utf-8'))

    def test_stable_package_and_registry_versions_match(self):
        self.assertRegex(am_paths.VERSION, r'^\d+\.\d+\.\d+$')
        registry = json.loads((ROOT / 'server.json').read_text(encoding='utf-8'))
        self.assertEqual(registry['version'], am_paths.VERSION)
        self.assertEqual({p['version'] for p in registry['packages']}, {am_paths.VERSION})
        self.assertEqual(registry['packages'][0]['packageArguments'][0]['value'], 'am-mcp')


if __name__ == '__main__':
    unittest.main()
