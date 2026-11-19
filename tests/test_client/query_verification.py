"""Harness integration of an independent baseline and an authorized query read.

The caller owns transport, provenance, data-policy handling and the pinned
baseline. This helper does not fetch data or retry a query.
"""
from decimal import Decimal
import json

from onec_mcp_toolkit_proxy.query_comparison import normalize_query_result, compare_query_results


def verify_document_response(response_text, *, contract, baseline, context):
    """Confirm one document only within the explicit query projection."""
    def unique_pairs(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('Duplicate JSON key')
            value[key] = item
        return value

    def invalid_number(value):
        raise ValueError('Non-finite JSON number')

    try:
        response = json.loads(response_text, parse_float=Decimal,
                              parse_constant=invalid_number, object_pairs_hook=unique_pairs)
    except (ValueError, TypeError):
        response = None
    actual = normalize_query_result(response, context, contract)
    comparison = compare_query_results(dict(version=1, contract=contract, expected=baseline, actual=actual))
    # A wire projection/ignored column is insufficient for this business gate.
    confirmed = (comparison['status'] == 'equal' and comparison['scope'] == 'query_result'
                 and comparison['counts']['expected'] == comparison['counts']['actual'] == 1
                 and any(cell.get('type') == 'reference'
                         and cell['value']['object_type'].startswith('ДокументСсылка.')
                         for cell in baseline['rows'][0]))
    return dict(business_confirmed=confirmed, verification_scope='one_document_query_projection',
                comparison=comparison)
