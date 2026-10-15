"""Testes de lógica independentes do tenant e do executável real dtctl."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import dashboard_logic as logic
import planner
import dtctl_client as cli


def sample():
    return {
        "id": "dash-123", "name": "API Produção", "type": "dashboard", "owner": "me",
        "content": {
            "version": 21, "variables": [{"key": "env", "type": "static", "value": "prod"}],
            "settings": {"defaultTimeframe": {"enabled": True}},
            "tiles": {
                "1": {"type": "markdown", "content": "# Apis"},
                "2": {"type": "data", "title": "Latência", "query": "fetch spans | limit 10",
                      "visualization": "lineChart",
                      "visualizationSettings": {"legend": {"showLegend": True, "position": "auto"}, "axes": {"x": {"showLabel": True}}},
                      "querySettings": {"maxResultRecords": 1000}},
            },
            "layouts": {"1": {"x": 0, "y": 0, "w": 24, "h": 1}, "2": {"x": 0, "y": 1, "w": 12, "h": 8}},
        },
    }


class DashboardLogicTests(unittest.TestCase):
    def test_default(self):
        logic.validate_dashboard(logic.default_dashboard())

    def test_missing_layout(self):
        c = sample()["content"]
        del c["layouts"]["2"]
        with self.assertRaises(ValueError):
            logic.validate_dashboard(c)

    def test_merge_preserves_siblings(self):
        merged = logic.deep_merge({"a": {"b": 1, "c": 2}}, {"a": {"b": 3}})
        self.assertEqual(merged, {"a": {"b": 3, "c": 2}})

    def test_add_tile_unique(self):
        updated, tile_id = logic.add_tile(sample()["content"], {"type": "markdown", "content": "oi"})
        self.assertEqual(tile_id, "3")
        self.assertEqual(set(updated["tiles"]), set(updated["layouts"]))

    def test_visualization_merge(self):
        updated = logic.patch_visualization(sample()["content"], "2", settings_patch={"legend": {"showLegend": False}})
        self.assertFalse(updated["tiles"]["2"]["visualizationSettings"]["legend"]["showLegend"])
        self.assertEqual(updated["tiles"]["2"]["visualizationSettings"]["legend"]["position"], "auto")

    def test_visualization_type_requires_replace(self):
        with self.assertRaises(ValueError):
            logic.patch_visualization(sample()["content"], "2", visualization="areaChart", mode="merge")

    def test_visualization_replace(self):
        updated = logic.patch_visualization(sample()["content"], "2", visualization="areaChart", mode="replace")
        self.assertEqual(updated["tiles"]["2"]["visualizationSettings"], {})

    def test_json_pointer_nested(self):
        updated = logic.pointer_update(sample()["content"], "/tiles/2/visualizationSettings/legend/showLegend", operation="set", value=False)
        self.assertFalse(updated["tiles"]["2"]["visualizationSettings"]["legend"]["showLegend"])

    def test_json_pointer_array(self):
        updated = logic.pointer_update(sample()["content"], "/variables/0/key", operation="set", value="space")
        self.assertEqual(updated["variables"][0]["key"], "space")

    def test_json_pointer_remove(self):
        updated = logic.pointer_update(sample()["content"], "/tiles/2/visualizationSettings/legend/position", operation="remove")
        self.assertNotIn("position", updated["tiles"]["2"]["visualizationSettings"]["legend"])

    def test_layout_bool_rejected(self):
        c = sample()["content"]
        c["layouts"]["2"]["x"] = True
        with self.assertRaises(ValueError):
            logic.validate_dashboard(c)


class PlannerTests(unittest.TestCase):
    def setUp(self):
        planner.PLANS.clear()
        self.remote = sample()
        self.getter = patch.object(cli, "get_dashboard", side_effect=lambda _id: copy.deepcopy(self.remote))
        self.apply = patch.object(planner, "_apply", return_value="dry-run OK")
        self.getter.start()
        self.apply_mock = self.apply.start()
        self.addCleanup(self.getter.stop)
        self.addCleanup(self.apply.stop)
        self.addCleanup(planner.PLANS.clear)

    def _candidate(self, plan):
        return planner.PLANS[plan["plan_id"]].new

    def test_visualization_only_target_changes(self):
        plan = planner.plan_visualization("dash-123", "2", settings_patch={"legend": {"showLegend": False}})
        new = self._candidate(plan)
        self.assertEqual(new["content"]["tiles"]["1"], self.remote["content"]["tiles"]["1"])
        self.assertEqual(new["content"]["tiles"]["2"]["query"], "fetch spans | limit 10")
        self.assertFalse(new["content"]["tiles"]["2"]["visualizationSettings"]["legend"]["showLegend"])
        self.assertEqual(plan["dtctl_dry_run"], "dry-run OK")

    def test_edit_query_preserves_viz(self):
        p = planner.plan_edit_tile_dql("dash-123", "2", "fetch logs | limit 30")
        new = self._candidate(p)
        self.assertEqual(new["content"]["tiles"]["2"]["visualization"], "lineChart")
        self.assertEqual(new["content"]["tiles"]["2"]["query"], "fetch logs | limit 30")

    def test_upsert_existing_merge(self):
        p = planner.plan_upsert_tile("dash-123", "2", {"title": "P95"})
        self.assertEqual(self._candidate(p)["content"]["tiles"]["2"]["visualization"], "lineChart")

    def test_upsert_new(self):
        p = planner.plan_upsert_tile("dash-123", "4", {"type": "markdown", "content": "# Teste"})
        self.assertIn("4", self._candidate(p)["content"]["layouts"])

    def test_layout(self):
        p = planner.plan_layout("dash-123", "2", {"x": 12, "w": 12})
        self.assertEqual(self._candidate(p)["content"]["layouts"]["2"]["y"], 1)
        self.assertEqual(self._candidate(p)["content"]["layouts"]["2"]["x"], 12)

    def test_invalid_layout(self):
        with self.assertRaises(ValueError):
            planner.plan_layout("dash-123", "2", {"x": 20, "w": 12})

    def test_delete_tile_removes_layout(self):
        p = planner.plan_remove_tile("dash-123", "2")
        self.assertNotIn("2", self._candidate(p)["content"]["tiles"])
        self.assertNotIn("2", self._candidate(p)["content"]["layouts"])

    def test_pointer(self):
        p = planner.plan_pointer("dash-123", "/tiles/2/visualizationSettings/legend/showLegend", False)
        self.assertFalse(self._candidate(p)["content"]["tiles"]["2"]["visualizationSettings"]["legend"]["showLegend"])

    def test_pointer_cannot_edit_id(self):
        with self.assertRaises(ValueError):
            planner.plan_pointer("dash-123", "/id", "hack")

    def test_batch_multiple_properties_one_plan(self):
        p = planner.plan_batch_patches("dash-123", [
            {"path": "/tiles/2/visualizationSettings/legend/showLegend", "operation": "set", "value": False},
            {"path": "/tiles/2/title", "operation": "set", "value": "P95"},
            {"path": "/layouts/2/w", "operation": "set", "value": 24},
        ])
        c = self._candidate(p)["content"]
        self.assertFalse(c["tiles"]["2"]["visualizationSettings"]["legend"]["showLegend"])
        self.assertEqual(c["tiles"]["2"]["title"], "P95")
        self.assertEqual(c["layouts"]["2"]["w"], 24)
        self.assertEqual(self.apply_mock.call_count, 1)

    def test_batch_disallows_document_metadata_patch(self):
        with self.assertRaises(ValueError):
            planner.plan_batch_patches("dash-123", [{"path": "/id", "value": "hack"}])

    def test_settings(self):
        p = planner.plan_settings("dash-123", {"defaultTimeframe": {"enabled": False}})
        self.assertFalse(self._candidate(p)["content"]["settings"]["defaultTimeframe"]["enabled"])

    def test_variables_add(self):
        p = planner.plan_variable("dash-123", "add", "team", {"key": "team", "type": "static", "value": "test"})
        self.assertEqual(len(self._candidate(p)["content"]["variables"]), 2)

    def test_variables_replace(self):
        p = planner.plan_variable("dash-123", "replace", "env", {"key": "env", "type": "static", "value": "dev"})
        self.assertEqual(self._candidate(p)["content"]["variables"][0]["value"], "dev")

    def test_variables_remove(self):
        p = planner.plan_variable("dash-123", "remove", "env")
        self.assertEqual(self._candidate(p)["content"]["variables"], [])

    def test_create_no_id(self):
        p = planner.plan_create_dashboard("Novo")
        self.assertNotIn("id", self._candidate(p))

    def test_diff_no_op_rejected(self):
        with self.assertRaises(ValueError):
            planner.plan_patch_tile("dash-123", "2", {"title": "Latência"})

    def test_review_and_discard(self):
        p = planner.plan_layout("dash-123", "2", {"h": 9})
        self.assertIn("diff", planner.review(p["plan_id"]))
        self.assertTrue(planner.discard(p["plan_id"])["discarded"])
        with self.assertRaises(ValueError):
            planner.review(p["plan_id"])

    def test_publish_needs_confirm(self):
        p = planner.plan_layout("dash-123", "2", {"h": 9})
        with self.assertRaises(PermissionError):
            planner.publish(p["plan_id"], False)
        self.assertEqual(self.apply_mock.call_count, 1)

    def test_publish_requires_env_write(self):
        p = planner.plan_layout("dash-123", "2", {"h": 9})
        with patch.dict(os.environ, {"DTCTL_ALLOW_WRITE": "0"}):
            with self.assertRaises(PermissionError):
                planner.publish(p["plan_id"], True)

    def test_publish_rejects_remote_change(self):
        p = planner.plan_layout("dash-123", "2", {"h": 9})
        self.remote["content"]["tiles"]["2"]["title"] = "Alguém editou"
        with patch.dict(os.environ, {"DTCTL_ALLOW_WRITE": "1"}):
            with self.assertRaises(RuntimeError):
                planner.publish(p["plan_id"], True)
        self.assertEqual(self.apply_mock.call_count, 1)

    def test_publish_backup_then_apply(self):
        p = planner.plan_layout("dash-123", "2", {"h": 9})
        with tempfile.TemporaryDirectory() as backup_dir:
            with patch.dict(os.environ, {"DTCTL_ALLOW_WRITE": "1", "DTCTL_BACKUP_DIR": backup_dir}):
                result = planner.publish(p["plan_id"], True)
            self.assertTrue(result["published"])
            self.assertTrue(Path(result["backup_file"]).exists())
            self.assertEqual(json.loads(Path(result["backup_file"]).read_text(encoding="utf-8")), self.remote)
        self.assertEqual(self.apply_mock.call_count, 3)  # plan dry run, pre-write dry run, write apply
        self.assertNotIn(p["plan_id"], planner.PLANS)

    def test_publish_backup_failure_blocks(self):
        p = planner.plan_layout("dash-123", "2", {"h": 9})
        with patch.dict(os.environ, {"DTCTL_ALLOW_WRITE": "1"}):
            with patch.object(planner, "_backup", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    planner.publish(p["plan_id"], True)
        self.assertEqual(self.apply_mock.call_count, 1)


class DtctlClientTests(unittest.TestCase):
    @patch("dtctl_client.resolve_binary", return_value="dtctl")
    @patch("dtctl_client.subprocess.run")
    def test_flags_avoid_shell_and_agent(self, runner, resolve):
        runner.return_value.returncode = 0
        runner.return_value.stdout = "{}"
        runner.return_value.stderr = ""
        with patch.dict(os.environ, {"DTCTL_CONTEXT": "test"}):
            cli.call(["get", "dashboards", "-o", "json"])
        kwargs = runner.call_args.kwargs
        args = runner.call_args.args[0]
        self.assertFalse(kwargs["shell"])
        self.assertIn("--no-agent", args)
        self.assertEqual(args[:3], ["dtctl", "--context", "test"])

    @patch("dtctl_client.call", return_value='{"id":"dash-123","type":"dashboard","content":{}}')
    def test_read_dashboard(self, fake_call):
        response = cli.get_dashboard("dash-123")
        self.assertEqual(response["id"], "dash-123")

    @patch("dtctl_client.call", return_value='{"ok":true,"result":[{"id":"x"}]}')
    def test_agent_envelope_compat(self, fake_call):
        self.assertEqual(cli.call_json(["get", "dashboards"]), [{"id": "x"}])


if __name__ == "__main__":
    unittest.main()
