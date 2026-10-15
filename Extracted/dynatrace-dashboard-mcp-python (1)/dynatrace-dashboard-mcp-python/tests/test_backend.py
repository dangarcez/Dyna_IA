import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import backend

BASE = {
    "id": "test-dashboard-123", "name": "Painel em produção", "type": "dashboard",
    "content": {
        "version": 21, "variables": [],
        "tiles": {
            "1": {"type": "markdown", "content": "# Meu painel"},
            "2": {
                "type": "data", "title": "CPU", "query": "timeseries x=avg(dt.host.cpu.usage)",
                "visualization": "lineChart",
                "visualizationSettings": {
                    "legend": {"showLegend": True, "position": "auto"},
                    "axes": {"yAxis": {"showLabel": False}},
                }, "querySettings": {},
            },
        },
        "layouts": {
            "1": {"x": 0, "y": 0, "w": 24, "h": 2},
            "2": {"x": 0, "y": 2, "w": 24, "h": 8},
        },
    },
}


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.current = copy.deepcopy(BASE)

        def fake_dtctl(args, *, json_output=False, timeout=120):
            self.calls.append(list(args))
            if args[:2] == ["get", "dashboard"]:
                return json.dumps(self.current)
            if args[:2] == ["apply", "-f"]:
                self.last_sent = json.loads(Path(args[2]).read_text(encoding="utf-8"))
                return "DRY RUN" if "--dry-run" in args else "DEPLOYED"
            raise AssertionError(f"Unexpected command: {args}")
        self.run_patch = patch("backend.run_dtctl", side_effect=fake_dtctl)
        self.run_patch.start()
        self.addCleanup(self.run_patch.stop)
        self.backup_temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.backup_temp.cleanup)
        self.env_patch = patch.dict(os.environ, {
            "DTCTL_ALLOW_WRITE": "0", "DTCTL_BACKUP_DIR": self.backup_temp.name,
        })
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def test_visualization_patch_preserves_untouched_items(self):
        result = backend.update_tile_visualization(
            "test-dashboard-123", "2",
            settings_patch={"legend": {"showLegend": False}, "axes": {"yAxis": {"label": "CPU (%)"}}},
            confirm=False,
        )
        self.assertEqual(result["status"], "PREVIA_SEM_PUBLICAR")
        self.assertEqual(self.last_sent["content"]["tiles"]["1"], BASE["content"]["tiles"]["1"])
        conf = self.last_sent["content"]["tiles"]["2"]["visualizationSettings"]
        self.assertFalse(conf["legend"]["showLegend"])
        self.assertEqual(conf["legend"]["position"], "auto")
        self.assertEqual(conf["axes"]["yAxis"]["showLabel"], False)
        self.assertEqual(conf["axes"]["yAxis"]["label"], "CPU (%)")
        self.assertIn("showLegend", result["diff"])
        self.assertEqual(sum("--dry-run" not in c for c in self.calls if c[0] == "apply"), 0)

    def test_switch_viz_requires_replace(self):
        with self.assertRaisesRegex(backend.DynatraceError, "replace"):
            backend.update_tile_visualization("test-dashboard-123", "2", visualization="areaChart")
        result = backend.update_tile_visualization(
            "test-dashboard-123", "2", visualization="areaChart",
            settings_patch={"legend": {"showLegend": True}}, mode="replace",
        )
        self.assertEqual(result["visualization"], "areaChart")
        self.assertEqual(result["visualizationSettings"], {"legend": {"showLegend": True}})

    def test_publish_blocked_without_env(self):
        result = backend.update_tile_visualization(
            "test-dashboard-123", "2", settings_patch={"legend": {"showLegend": False}}, confirm=True,
        )
        self.assertEqual(result["status"], "BLOQUEADO_SEM_PERMISSAO_DE_ESCRITA")
        self.assertFalse(list(Path(self.backup_temp.name).glob("*.json")))

    def test_publish_makes_backup(self):
        os.environ["DTCTL_ALLOW_WRITE"] = "1"
        result = backend.update_tile_visualization(
            "test-dashboard-123", "2", settings_patch={"legend": {"showLegend": False}}, confirm=True,
        )
        self.assertEqual(result["status"], "PUBLICADO")
        backup = json.loads(Path(result["backup"]).read_text(encoding="utf-8"))
        self.assertEqual(backup, BASE)
        self.assertEqual(self.calls[-1][0], "apply")
        self.assertNotIn("--dry-run", self.calls[-1])

    def test_upsert_new_tile_with_visualization_settings(self):
        result = backend.upsert_dashboard_tile(
            "test-dashboard-123", title="Erros", query="fetch logs | limit 5",
            visualization="table", visualization_settings={"table": {"rowDensity": "condensed"}}
        )
        self.assertEqual(result["tile_id"], "3")
        self.assertIn("3", self.last_sent["content"]["tiles"])
        self.assertEqual(self.last_sent["content"]["tiles"]["3"]["visualizationSettings"]["table"]["rowDensity"], "condensed")
        self.assertEqual(self.last_sent["content"]["layouts"]["3"]["y"], 10)

    def test_nonmatching_id_stops_update(self):
        self.current["id"] = "OTHER-ID"
        with self.assertRaisesRegex(backend.DynatraceError, "diferente"):
            backend.update_tile_visualization("test-dashboard-123", "2", title="Nova CPU")

    def test_create_preview_has_no_id(self):
        result = backend.create_dashboard("Painel de teste")
        self.assertEqual(result["status"], "PREVIA_SEM_PUBLICAR")
        self.assertNotIn("id", self.last_sent)
        self.assertEqual(self.last_sent["content"]["version"], 21)

    def test_missing_tile_does_not_publish(self):
        with self.assertRaisesRegex(backend.DynatraceError, "não encontrado"):
            backend.update_tile_visualization("test-dashboard-123", "999", title="A")


if __name__ == "__main__":
    unittest.main()
