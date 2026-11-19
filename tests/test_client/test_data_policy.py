import copy
import unittest

from onec_mcp_toolkit_proxy.anonymizer.anonymizer import Anonymizer
from onec_mcp_toolkit_proxy.anonymizer.dictionary_matcher import DictionaryMatcher
from onec_mcp_toolkit_proxy.anonymizer.test_client_data import TEST_CLIENT_TOOLS, TECHNICAL_KEYS


class DataPolicyTests(unittest.TestCase):
    def test_existing_dictionary_applies_to_ui_text_not_ids(self):
        anon = Anonymizer()
        matcher = DictionaryMatcher()
        matcher.build({"SyntheticFixtureCompany": "ORG"})
        anon.set_dict_matcher(matcher)
        result = anon.anonymize_response({"data": {"element_id": "SyntheticFixtureCompany",
            "value": "SyntheticFixtureCompany", "messages": [{"text": "SyntheticFixtureCompany"}]}}, "test_inspect")
        self.assertEqual(result["data"]["element_id"], "SyntheticFixtureCompany")
        self.assertNotEqual(result["data"]["value"], "SyntheticFixtureCompany")
        self.assertNotEqual(result["data"]["messages"][0]["text"], "SyntheticFixtureCompany")

    def test_nested_text_errors_and_ids(self):
        for tool in TEST_CLIENT_TOOLS:
            with self.subTest(tool=tool):
                anon = Anonymizer()
                email = "fixture.person@example.org"
                response = {"success": False, "request_id": email, "data": {
                    "windows": [{"window_id": email, "title": email, "children": [
                        {"element_id": email, "value": email}]}],
                    "snapshot_id": email}, "error": {"message": email}, "messages": [{"text": email}]}
                before = copy.deepcopy(response)
                result = anon.anonymize_response(response, tool)
                self.assertEqual(response, before)
                self.assertEqual(result["request_id"], email)
                self.assertEqual(result["data"]["windows"][0]["window_id"], email)
                self.assertEqual(result["data"]["windows"][0]["children"][0]["element_id"], email)
                self.assertNotEqual(result["data"]["windows"][0]["title"], email)
                self.assertNotEqual(result["error"]["message"], email)
                self.assertNotEqual(result["messages"][0]["text"], email)
                self.assertNotEqual(result["data"]["windows"][0]["children"][0]["value"], email)

    def test_technical_scalars_do_not_exempt_subtrees_or_business_id(self):
        anon = Anonymizer()
        email = "fixture.person@example.org"
        for key in TECHNICAL_KEYS:
            self.assertEqual(anon.anonymize_response({key: email}, "test_inspect")[key], email)
        result = anon.anonymize_response({"data": {"id": email, "session_id": {"text": email}}}, "test_inspect")
        self.assertNotEqual(result["data"]["id"], email)
        self.assertNotEqual(result["data"]["session_id"]["text"], email)

    def test_restore_text_without_rewriting_ids_or_metadata(self):
        anon = Anonymizer()
        token = anon.mapper.tokenize("Original text", "STR")
        request = {"request_id": token, "session_id": token, "window": {"id": token},
                   "element": {"selector": {"name": token, "title": token, "path": [token]}},
                   "params": {"row": {"id": token, "snapshot_id": token},
                              "values": [{"column": token, "text": token}],
                              "condition": {"property": "value", "value": token}}}
        before = copy.deepcopy(request)
        result = anon.detokenize_params_for_tool(request, "test_input")
        self.assertEqual(request, before)
        self.assertEqual(result["request_id"], token)
        self.assertEqual(result["session_id"], token)
        self.assertEqual(result["window"]["id"], token)
        self.assertEqual(result["element"]["selector"]["name"], token)
        self.assertEqual(result["element"]["selector"]["path"], [token])
        self.assertEqual(result["element"]["selector"]["title"], "Original text")
        self.assertEqual(result["params"]["row"], request["params"]["row"])
        self.assertEqual(result["params"]["values"], [{"column": token, "text": "Original text"}])
        self.assertEqual(result["params"]["condition"]["value"], "Original text")

    def test_secrets_are_removed_even_when_error_anonymization_is_disabled(self):
        anon = Anonymizer(include_errors=False)
        result = anon.anonymize_response({"error": {"message": "unchanged", "Password": "DO_NOT_ECHO"},
            "data": [{"connection_string": "DO_NOT_ECHO"}, {"nested": {"access_token": "DO_NOT_ECHO"}}]}, "test_session")
        self.assertNotIn("DO_NOT_ECHO", str(result))
        self.assertEqual(result["error"]["message"], "unchanged")

    def test_existing_tools_keep_their_policy(self):
        anon = Anonymizer()
        email = "fixture.person@example.org"
        self.assertNotEqual(anon.anonymize_response({"data": {"session_id": email}}, "execute_code")["data"]["session_id"], email)
        token = anon.mapper.tokenize("Original", "STR")
        self.assertEqual(anon.detokenize_params_for_tool({"session_id": token}, "get_metadata"), {"session_id": "Original"})


if __name__ == "__main__":
    unittest.main()
