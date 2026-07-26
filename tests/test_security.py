"""Security behavior for mutating Flask routes."""

import os
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import app as trending_app


class WriteRouteSecurityTests(unittest.TestCase):
    write_routes = ("/api/save", "/api/auto-save")

    def setUp(self):
        self.client = trending_app.app.test_client()
        self.environ = patch.dict(
            os.environ,
            {
                "TRENDING_REPO_LOCAL_MODE": "1",
                "TRENDING_REPO_WRITE_TOKEN": "test-write-token",
            },
            clear=False,
        )
        self.environ.start()

    def tearDown(self):
        self.environ.stop()

    def test_write_routes_are_disabled_without_explicit_local_mode(self):
        with patch.dict(os.environ, {}, clear=True):
            for route in self.write_routes:
                with self.subTest(route=route):
                    response = self.client.post(route, json={})
                    self.assertEqual(response.status_code, 404)

    def test_write_routes_require_authentication(self):
        for route in self.write_routes:
            with self.subTest(route=route):
                response = self.client.post(route, json={})
                self.assertEqual(response.status_code, 401)

    def test_write_routes_require_csrf_token_after_authentication(self):
        for route in self.write_routes:
            with self.subTest(route=route):
                response = self.client.post(
                    route,
                    json={},
                    headers={"X-Write-Token": "test-write-token"},
                )
                self.assertEqual(response.status_code, 403)

    def test_non_post_methods_keep_normal_flask_semantics(self):
        headers = {"X-Write-Token": "test-write-token"}
        for route in self.write_routes:
            self.assertEqual(self.client.get(route, headers=headers).status_code, 405)
            self.assertEqual(self.client.put(route, headers=headers).status_code, 405)
            self.assertEqual(self.client.delete(route, headers=headers).status_code, 405)
            self.assertEqual(self.client.options(route, headers=headers).status_code, 200)

    def test_authenticated_csrf_protected_save_is_allowed(self):
        headers = {"X-Write-Token": "test-write-token"}
        csrf_response = self.client.get("/api/write-csrf", headers=headers)
        self.assertEqual(csrf_response.status_code, 200)
        csrf_token = csrf_response.get_json()["csrf_token"]
        with patch.object(trending_app, "_get_trending_cached", return_value=[]), patch.object(
            trending_app, "_save_snapshot", return_value=pathlib.Path("/tmp/snapshot.json")
        ):
            response = self.client.post(
                "/api/save",
                json={},
                headers={**headers, "X-CSRF-Token": csrf_token},
            )
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
