import unittest

from onec_mcp_toolkit_proxy.test_client_contract import valid_request
from onec_mcp_toolkit_proxy.test_client_operations import normalize


class CommandInterfaceContract(unittest.TestCase):
    def arguments(self, action, **kwargs):
        return dict(request_id='menu-request', session_id='session', action=action,
                    window={'id': 'window'}, params={}, **kwargs)

    def test_scopes_and_limits(self):
        for scope in ('command_interface', 'command_bars'):
            args = self.arguments(scope)
            self.assertTrue(valid_request('test_inspect', args))
            normalized = normalize('test_inspect', args)
            self.assertEqual(normalized['params'], {'depth': 8, 'max_nodes': 1000})
            self.assertTrue(valid_request('test_inspect', normalized))
            args['params'] = {'max_nodes': 5001}
            self.assertFalse(valid_request('test_inspect', args))

    def test_native_targets_keep_exact_scope_and_path(self):
        for action, target_type in (('click', 'command_button'), ('expand', 'command_group'), ('collapse', 'command_group')):
            target = {'selector': {'type': target_type, 'title': 'МВП проверка',
                                  'scope': 'command_interface', 'path': ['Разделы']}}
            args = self.arguments(action, element=target)
            self.assertTrue(valid_request('test_action', args))
            self.assertEqual(normalize('test_action', args)['element'], target)
            args['element']['selector']['scope'] = 'all'
            self.assertFalse(valid_request('test_action', args))

    def test_panel_buttons_and_existing_form_buttons(self):
        for selector in ({'name': 'Записать', 'type': 'button'},
                         {'name': 'Записать', 'type': 'button', 'scope': 'command_bars'}):
            self.assertTrue(valid_request('test_action', self.arguments('click', element={'selector': selector})))
        self.assertFalse(valid_request('test_action', self.arguments('expand')))

    def test_typed_number_and_iso_date_are_explicit(self):
        target = {'selector': {'name': 'Поле', 'type': 'field'}}
        for action, value in [('number', 12.5), ('date', '2026-11-17'), ('date', '2026-11-17T09:30:00')]:
            args = self.arguments(action, element=target)
            args['params'] = {'value': value}
            self.assertTrue(valid_request('test_input', args))
        for action, value in [('number', '12,50'), ('number', True), ('number', 1e20), ('date', '17.11.2026'), ('date', '2026-11-17Z')]:
            args = self.arguments(action, element=target)
            args['params'] = {'value': value}
            self.assertFalse(valid_request('test_input', args))


if __name__ == '__main__':
    unittest.main()
