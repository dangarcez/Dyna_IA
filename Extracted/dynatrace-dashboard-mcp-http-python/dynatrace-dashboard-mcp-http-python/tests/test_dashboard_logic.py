import copy
import unittest
from dashboard_logic import (add_tile, deep_merge, default_dashboard, diff_json,
                             patch_visualization, pointer_update, validate_dashboard)


class DashboardLogicTests(unittest.TestCase):
    def setUp(self):
        self.doc = default_dashboard()
        self.doc['tiles']['2'] = {'type': 'data', 'title': 'CPU', 'query': 'timeseries cpu=avg(dt.host.cpu.usage)',
            'visualization': 'lineChart', 'visualizationSettings': {'legend': {'showLegend': True},
            'axes': {'yAxis': {'label': 'old'}}}, 'querySettings': {}}
        self.doc['layouts']['2'] = {'x': 0, 'y': 0, 'w': 24, 'h': 8}

    def test_default(self):
        validate_dashboard(default_dashboard())

    def test_merge_doesnt_mutate(self):
        original = {'a': {'x': 1, 'y': 2}}
        result = deep_merge(original, {'a': {'y': 9}})
        self.assertEqual(result, {'a': {'x': 1, 'y': 9}})
        self.assertEqual(original['a']['y'], 2)

    def test_visualization_merge_preserves_other_options(self):
        after = patch_visualization(self.doc, '2', settings_patch={'legend': {'showLegend': False}})
        self.assertFalse(after['tiles']['2']['visualizationSettings']['legend']['showLegend'])
        self.assertEqual(after['tiles']['2']['visualizationSettings']['axes']['yAxis']['label'], 'old')
        self.assertTrue(self.doc['tiles']['2']['visualizationSettings']['legend']['showLegend'])

    def test_visualization_replacement_required_on_type_change(self):
        with self.assertRaises(ValueError):
            patch_visualization(self.doc, '2', visualization='areaChart', mode='merge')
        result = patch_visualization(self.doc, '2', visualization='areaChart', mode='replace', settings_patch={})
        self.assertEqual(result['tiles']['2']['visualization'], 'areaChart')
        self.assertEqual(result['tiles']['2']['visualizationSettings'], {})

    def test_add_tile_and_layout(self):
        result, ident = add_tile(self.doc, {'type': 'markdown', 'content': '# Hello'})
        self.assertEqual(ident, '1')
        self.assertEqual(result['layouts'][ident]['y'], 8)
        self.assertEqual(result['layouts'][ident]['h'], 1)

    def test_missing_layout_rejected(self):
        clone = copy.deepcopy(self.doc)
        del clone['layouts']['2']
        with self.assertRaises(ValueError):
            validate_dashboard(clone)

    def test_pointer_nested_set(self):
        result = pointer_update(self.doc, '/tiles/2/visualizationSettings/axes/yAxis/label', operation='set', value='CPU (%)')
        self.assertEqual(result['tiles']['2']['visualizationSettings']['axes']['yAxis']['label'], 'CPU (%)')

    def test_pointer_array_append_and_remove(self):
        result = pointer_update(self.doc, '/variables/-', operation='set', value={'key': 'Env', 'type': 'text'})
        result = pointer_update(result, '/variables/0', operation='remove')
        self.assertEqual(result['variables'], [])

    def test_diff(self):
        changed = copy.deepcopy(self.doc)
        changed['tiles']['2']['title'] = 'CPU 2'
        self.assertIn('CPU 2', diff_json(self.doc, changed))


if __name__ == '__main__':
    unittest.main()
