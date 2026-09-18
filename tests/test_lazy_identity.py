"""
Lazy DNS resolution of identities met as leaf values.

A product module that defines nothing but identities (e.g. atmos) never
shows up as a tree key: its SIDs only appear as identityref values, such as
the key of a list entry. These tests check that such a module is fetched on
demand, the way modules seen as keys already were — without any network
access: the DNS registry and the .sid repository are replaced by stubs.
"""

import unittest
from unittest import mock

import cbor2 as cbor

import pycoreconf
import pycoreconf.model as model_mod
from pycoreconf import sid_dns


def sid_file(module, entry_point, size, items, key_mapping=None):
    return {"ietf-sid-file:sid-file": {
        "module-name": module,
        "module-revision": "2026-01-01",
        "assignment-range": [{"entry-point": str(entry_point), "size": str(size)}],
        "item": items,
        "key-mapping": key_mapping or {},
    }}


# Structure module: a list keyed by an identityref.
DEMO = sid_file("demo", 1000, 100, [
    {"namespace": "module", "identifier": "demo", "sid": "1000"},
    {"namespace": "data", "identifier": "/demo:sensors", "sid": "1001"},
    {"namespace": "data", "identifier": "/demo:sensors/sensor", "sid": "1002"},
    {"namespace": "data", "identifier": "/demo:sensors/sensor/type", "sid": "1003",
     "type": "identityref"},
    {"namespace": "data", "identifier": "/demo:sensors/sensor/value", "sid": "1004",
     "type": "int64"},
], key_mapping={"1002": [1003]})

# Identity-only module, in the 10M range like atmos.
PROD = sid_file("prod", 10_000_000, 100, [
    {"namespace": "module", "identifier": "prod", "sid": "10000000"},
    {"namespace": "identity", "identifier": "temp", "sid": "10000001"},
    {"namespace": "identity", "identifier": "rain", "sid": "10000002"},
])

REPOSITORY = {"mem://demo": DEMO, "mem://prod": PROD}


def fake_query_sid(sid):
    if 1000 <= sid < 1100:
        return {"status": "registered", "fqdn": "demo",
                "fields": {"name": "demo", "repository": "mem://demo"}}
    if 10_000_000 <= sid < 10_000_100:
        return {"status": "registered", "fqdn": "prod",
                "fields": {"name": "prod", "repository": "mem://prod"}}
    return {"status": "not-registered", "fields": {}, "fqdn": None}


# {sensors: {sensor: [{type: <identity>, value: <int>}, ...]}}, delta-encoded.
def datastore(*entries):
    return cbor.dumps({1001: {1: [{1: t, 2: v} for t, v in entries]}})


class TestLazyIdentity(unittest.TestCase):

    def setUp(self):
        self.query = mock.patch.object(model_mod, "dns_query_sid",
                                       side_effect=fake_query_sid)
        self.fetch = mock.patch.object(model_mod, "fetch_sid_file",
                                       side_effect=REPOSITORY.get)
        self.query_mock = self.query.start()
        self.fetch.start()

    def tearDown(self):
        mock.patch.stopall()

    def decode(self, raw):
        model = pycoreconf.CORECONFModel()
        return model, model.decode(raw)

    def test_identity_module_fetched_from_a_value(self):
        model, data = self.decode(datastore((10000001, 42), (10000002, 7)))
        sensors = data["demo:sensors"]["sensor"]
        self.assertEqual([s["type"] for s in sensors], ["prod:temp", "prod:rain"])
        self.assertEqual([s["value"] for s in sensors], [42, 7])
        self.assertIn("prod:temp", model.sids)

    def test_identity_module_fetched_once(self):
        self.decode(datastore((10000001, 1), (10000002, 2), (10000001, 3)))
        queried = [c.args[0] for c in self.query_mock.call_args_list]
        self.assertEqual(sum(10_000_000 <= s < 10_000_100 for s in queried), 1)

    def test_unregistered_identity_keeps_its_sid(self):
        _, data = self.decode(datastore((10000001, 1), (10000099_0, 2)))
        types = [s["type"] for s in data["demo:sensors"]["sensor"]]
        self.assertEqual(types, ["prod:temp", 100000990])

    def test_union_does_not_query_dns_for_untagged_numbers(self):
        model = pycoreconf.CORECONFModel()
        self.query_mock.reset_mock()
        value = model._convert_leaf_value(4242, ["identityref", "uint32"], to_cbor=False)
        self.assertEqual(value, 4242)
        self.query_mock.assert_not_called()


class TestKnownZones(unittest.TestCase):

    def test_10m_range_is_resolved_in_afnic(self):
        self.assertEqual(sid_dns.detect_zone(10_000_001), ("afnic.sid.yt", False))
        self.assertEqual(sid_dns.detect_zone(10_999_999), ("afnic.sid.yt", False))

    def test_existing_ranges_unchanged(self):
        self.assertEqual(sid_dns.detect_zone(62057), ("ietf.sid.yt", False))
        self.assertEqual(sid_dns.detect_zone(5_000_001), ("afnic.sid.yt", False))
        self.assertEqual(sid_dns.detect_zone(9_999_999), (None, False))


if __name__ == "__main__":
    unittest.main()
