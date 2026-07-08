"""Build-probe tests — every assertion is derived from an explicit statement
in PRAMANA_DESIGN_SPEC.md v1.2 or PRAMANA_INTERFACE_DEFINITIONS.md.
Doc references given per test.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models import units
from models.hashing import identity, leaf_id, set_hash, set_id
from models.spec import (
    Application,
    Dynamic,
    Experiment,
    ExperimentSet,
    Impair,
    NodeDecl,
    Pin,
    Quantity,
    Queue,
    Static,
    Telemetry,
    Tolerance,
    Verify,
)

# ---------------------------------------------------------------- builders


def q(value, unit):
    return Quantity(value=value, unit=unit)


def make_static(**over):
    kw = dict(
        capacity_down=q(10.0, "mbps"),
        capacity_up=q(10.0, "mbps"),
        latency=q(10.0, "ms"),
        queue=Queue(qdisc="codel", args=""),
        cca="cubic",
    )
    kw.update(over)
    return Static(**kw)


def make_experiment(**over):
    kw = dict(
        id="e_00000000",
        static=make_static(),
        application=Application(
            workflow="wget@sha256:aa11",
            params={"duration": q(30.0, "s"), "url": "https://example.com/f"},
        ),
        dynamic=Dynamic(mode="replay", ctp=["c001"]),
        iterations=1,
        telemetry=Telemetry(),
        verify=Verify(tolerance=Tolerance()),
    )
    kw.update(over)
    return Experiment(**kw)


PIN = Pin(
    version="2.4.0",
    url="https://example.com/netgent.yaml",
    sha256="deadbeef",
    pinned_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
)


def make_set(**over):
    kw = dict(
        id="es_intent_00000000",
        capability_pins={"netgent": PIN},
        nodes=[NodeDecl(name="pool", kind="pool", pipeline=["wget"])],
        mapping={"pool": "local_docker"},
        experiments=[make_experiment()],
    )
    kw.update(over)
    return ExperimentSet(**kw)


# ---------------------------------------------------------------- §4.2 units
# "rate(kbps|mbps|gbps→mbps) · time(ms|s|min→ms) · pct"


class TestUnits:
    def test_parse_example_from_interface_defs(self):
        # §1.5: parse("10mbps") -> Quantity(10.0,"mbps")
        got = units.parse("10mbps")
        assert got.value == 10.0 and got.unit == "mbps"

    def test_rate_canonicalization_kbps_equals_mbps(self):
        # task-mandated: 10mbps == 10000kbps canonically
        assert units.parse("10000kbps") == units.parse("10mbps")
        assert units.format(units.parse("10000kbps")) == "10mbps"

    def test_gbps_to_mbps(self):
        assert units.parse("2.5gbps") == q(2500.0, "mbps")

    def test_time_canonicalization_to_ms(self):
        # §4.2: time(ms|s|min→ms)
        assert units.parse("30s") == q(30000.0, "ms")
        assert units.parse("1min") == q(60000.0, "ms")
        assert units.parse("100ms") == q(100.0, "ms")

    def test_pct(self):
        assert units.parse("5pct") == q(5.0, "pct")

    def test_trailing_zeros_stripped(self):
        # RT-1: "trailing zeros stripped"
        assert units.format(q(10.500000, "mbps")) == "10.5mbps"
        assert units.format(q(10.0, "mbps")) == "10mbps"

    def test_round_half_even_six_fractional_digits(self):
        # RT-1: "round-half-even to ≤ 6 fractional digits"
        assert units.render_number("0.0000015") == "0.000002"  # half -> even up
        assert units.render_number("0.0000025") == "0.000002"  # half -> even down
        assert units.render_number("1.23456789") == "1.234568"

    def test_no_exponent_notation(self):
        # RT-1: "no exponent notation"
        assert "e" not in units.render_number(10000000)
        assert units.render_number(10000000) == "10000000"
        assert units.render_number(0.0000001) == "0"

    def test_negative_zero_renders_as_zero(self):
        # RT-1: "negative zero rendered as 0"
        assert units.render_number(-0.0) == "0"
        assert units.format(units.parse("-0mbps")) == "0mbps"

    @pytest.mark.parametrize(
        "text", ["10mbps", "10000kbps", "0.5gbps", "30s", "1min", "12.25ms", "5pct"]
    )
    def test_parse_format_idempotent(self, text):
        # RT-1: "parse∘format idempotent"
        once = units.format(units.parse(text))
        assert units.format(units.parse(once)) == once

    @pytest.mark.parametrize("bad", ["10 furlongs", "mbps", "10", "", "10..5ms"])
    def test_unit_error(self, bad):
        with pytest.raises(units.UnitError):
            units.parse(bad)


# ------------------------------------------------------- §4.3 identity scope
# "Includes {workflow_sha, resolved params sans secret values, static,
#  dynamic.mode/ctp/load}. Excludes nodes, mapping, iterations, telemetry,
#  verify, attempts, provenance."


class TestIdentity:
    def test_identity_excludes_iterations(self):
        a = make_experiment(iterations=1)
        b = make_experiment(iterations=5)
        assert identity(a) == identity(b)

    def test_identity_excludes_telemetry_and_verify(self):
        a = make_experiment()
        b = make_experiment(
            telemetry=Telemetry(pcap=False, qtrace=True),
            verify=Verify(probe=False, tolerance=Tolerance(capacity_pct=50.0)),
        )
        assert identity(a) == identity(b)

    def test_identity_excludes_placement(self):
        # two specs differing ONLY in mapping (placement): leaves hash equal,
        # set_hash (full equality) differs.
        s1 = make_set(mapping={"pool": "local_docker"})
        s2 = make_set(mapping={"pool": "aws:research@us-west-2"})
        assert identity(s1.experiments[0]) == identity(s2.experiments[0])
        assert set_hash(s1) != set_hash(s2)

    def test_identity_includes_cca(self):
        # A5 template: "cca: cubic  # endpoint-applied; in identity"
        a = make_experiment(static=make_static(cca="cubic"))
        b = make_experiment(static=make_static(cca="bbr"))
        assert identity(a) != identity(b)

    def test_identity_includes_ctp(self):
        # A5 template: ctp "in identity"
        a = make_experiment(dynamic=Dynamic(mode="replay", ctp=["c001"]))
        b = make_experiment(dynamic=Dynamic(mode="replay", ctp=["c002"]))
        assert identity(a) != identity(b)

    def test_identity_includes_workflow_sha_and_params(self):
        a = make_experiment()
        b = make_experiment(
            application=Application(
                workflow="wget@sha256:bb22",
                params={"duration": q(30.0, "s"), "url": "https://example.com/f"},
            )
        )
        c = make_experiment(
            application=Application(
                workflow="wget@sha256:aa11",
                params={"duration": q(60.0, "s"), "url": "https://example.com/f"},
            )
        )
        assert identity(a) != identity(b)
        assert identity(a) != identity(c)

    def test_identity_includes_queue_args_as_is(self):
        # Queue.args "Participates in identity as-is"
        a = make_experiment(static=make_static(queue=Queue(qdisc="codel", args="")))
        b = make_experiment(
            static=make_static(queue=Queue(qdisc="codel", args="target 5ms"))
        )
        assert identity(a) != identity(b)

    def test_leaf_id_shape(self):
        # A5: id: e_<hash8> = identity-hash prefix
        e = make_experiment()
        lid = leaf_id(e)
        assert lid.startswith("e_") and len(lid) == 10
        assert lid == "e_" + identity(e)[:8]

    def test_canonical_numbers_hash_stable(self):
        # RT-1 exists so float noise never leaks into identity (§4.2 "no pint")
        a = make_experiment(static=make_static(capacity_down=q(10.0, "mbps")))
        b = make_experiment(
            static=make_static(capacity_down=q(10.0000000001, "mbps"))
        )
        assert identity(a) == identity(b)


# ---------------------------------------------------- RT2-11 mode validation
# "replay => ctp non-empty & load empty; load => load non-empty & ctp empty;
#  both => both non-empty; none => both empty. Anything else = 422."


LOAD = {"workflow": "iperf@sha256:cc33", "node": "pool", "params": {}}


class TestModeMatrix:
    @pytest.mark.parametrize(
        "kw",
        [
            dict(mode="replay", ctp=["c1"]),
            dict(mode="load", load=[LOAD]),
            dict(mode="both", ctp=["c1"], load=[LOAD]),
            dict(mode="none"),
        ],
    )
    def test_valid_rows(self, kw):
        Dynamic(**kw)  # must not raise

    @pytest.mark.parametrize(
        "kw",
        [
            dict(mode="replay"),  # ctp empty
            dict(mode="replay", ctp=["c1"], load=[LOAD]),  # load must be empty
            dict(mode="load"),  # load empty
            dict(mode="load", ctp=["c1"], load=[LOAD]),  # ctp must be empty
            dict(mode="both", ctp=["c1"]),  # load empty
            dict(mode="both", load=[LOAD]),  # ctp empty
            dict(mode="none", ctp=["c1"]),  # must be empty
            dict(mode="none", load=[LOAD]),  # must be empty
        ],
    )
    def test_rejected_rows(self, kw):
        with pytest.raises(ValidationError):
            Dynamic(**kw)

    def test_ctp_length_one_or_iterations(self):
        # A5: "len 1 => SAME profile...; len == iterations => i-th ↦ i-th"
        make_experiment(
            dynamic=Dynamic(mode="replay", ctp=["a", "b", "c"]), iterations=3
        )
        make_experiment(dynamic=Dynamic(mode="replay", ctp=["a"]), iterations=3)
        with pytest.raises(ValidationError):
            make_experiment(
                dynamic=Dynamic(mode="replay", ctp=["a", "b"]), iterations=3
            )


# -------------------------------------------------------- RT3-3/RT4-2 local_dir


class TestLocalDir:
    def test_required_iff_source_local_dir(self):
        with pytest.raises(ValidationError):
            Dynamic(mode="replay", ctp=["c1"], source="local_dir")

    def test_absolute_path_required(self):
        with pytest.raises(ValidationError):
            Dynamic(mode="replay", ctp=["c1"], source="local_dir", local_dir="rel/dir")

    def test_forbidden_when_source_ctp_service(self):
        with pytest.raises(ValidationError):
            Dynamic(mode="replay", ctp=["c1"], source="ctp_service", local_dir="/x")

    def test_accepted_on_t1(self):
        d = Dynamic(mode="replay", ctp=["c1"], source="local_dir", local_dir="/ctps")
        make_set(experiments=[make_experiment(dynamic=d)])  # local_docker mapping ok

    def test_rejected_on_t2_mapping(self):
        # RT4-2: "validators reject source=local_dir when the leaf's node maps
        # to any non-local_docker connector"
        d = Dynamic(mode="replay", ctp=["c1"], source="local_dir", local_dir="/ctps")
        with pytest.raises(ValidationError):
            make_set(
                experiments=[make_experiment(dynamic=d)],
                mapping={"pool": "aws"},
            )


# --------------------------------------------------- RT3-1 set_hash / set_id


class TestSetIdentity:
    def test_slug_is_display_only(self):
        # §1.5: "EQUALITY uses the full canonical hash alone, never the slug"
        s = make_set()
        a = set_id(s, "wget_cca_compare")
        b = set_id(s, "Totally Different Name!")
        assert a != b
        assert a.rsplit("_", 1)[1] == b.rsplit("_", 1)[1] == set_hash(s)[:8]

    def test_slug_charset_and_length(self):
        # "kebab of spec filename stem (or 'intent'), [a-z0-9-], <=24 chars"
        sid = set_id(make_set(), "My Spec File v2!!")
        slug = sid[len("es_"):-9]
        assert slug == "my-spec-file-v2"
        long = set_id(make_set(), "x" * 60)
        assert len(long[len("es_"):-9]) <= 24
        assert set_id(make_set()).startswith("es_intent_")

    def test_set_hash_ignores_id_field(self):
        # RT3-1: equality key covers {schema_version, nodes, mapping, secrets,
        # leaves} — not the id string
        assert set_hash(make_set(id="es_a_11111111")) == set_hash(
            make_set(id="es_b_22222222")
        )

    def test_set_hash_covers_mapping_and_secrets(self):
        base = make_set()
        assert set_hash(base) != set_hash(make_set(mapping={"pool": "aws"}))
        assert set_hash(base) != set_hash(make_set(secrets=["zoom_meeting_code"]))


# ------------------------------------------------ strict gate + field rules


class TestGateStrictness:
    def test_unknown_field_rejected_at_set_level(self):
        # §4: extra="forbid" at the compile gate
        with pytest.raises(ValidationError):
            ExperimentSet(
                id="es_x_00000000",
                capability_pins={},
                nodes=[],
                mapping={},
                experiments=[],
                surprise=True,
            )

    def test_unknown_field_rejected_in_nested_block(self):
        with pytest.raises(ValidationError):
            Static(
                capacity_down=q(10, "mbps"),
                capacity_up=q(10, "mbps"),
                latency=q(10, "ms"),
                queue=Queue(qdisc="codel"),
                cca="cubic",
                bogus_knob=1,
            )

    def test_tolerance_closed_key_set(self):
        # RT-6: "No other keys in v1 (extra='forbid')"
        with pytest.raises(ValidationError):
            Tolerance(capacity_pct=5.0, latency_ms=2.0, jitter_ms=1.0)

    def test_queue_args_regex(self):
        # RT-2/3: validated by regex ^[a-z0-9 ._%]*$ (no shell metachars)
        Queue(qdisc="codel", args="target 5ms interval 100ms")
        with pytest.raises(ValidationError):
            Queue(qdisc="codel", args="target 5ms; rm -rf /")

    def test_qdisc_closed_set(self):
        with pytest.raises(ValidationError):
            Queue(qdisc="sfq")

    def test_impair_ranges_and_reorder_delay_rule(self):
        # RT-4: 0..100; reorder requires latency > 0
        with pytest.raises(ValidationError):
            Impair(loss_pct=101.0)
        with pytest.raises(ValidationError):
            make_static(latency=q(0, "ms"), impair=Impair(reorder_pct=1.0))
        make_static(latency=q(10, "ms"), impair=Impair(reorder_pct=1.0))

    def test_service_node_single_pipeline(self):
        # RT3-9: v1 REQUIRES len(pipeline) == 1 for kind: service
        NodeDecl(name="b", kind="service", pipeline=["zoom_server"])
        with pytest.raises(ValidationError):
            NodeDecl(name="b", kind="service", pipeline=["a", "b"])

    def test_load_entry_node_must_be_declared_with_workflow_in_pipeline(self):
        # RT-5: node "must name a declared node whose pipeline contains this
        # workflow id"
        d = Dynamic(
            mode="load",
            load=[{"workflow": "iperf@sha256:cc33", "node": "ghost", "params": {}}],
        )
        with pytest.raises(ValidationError):
            make_set(experiments=[make_experiment(dynamic=d)])
        d2 = Dynamic(
            mode="load",
            load=[{"workflow": "iperf@sha256:cc33", "node": "pool", "params": {}}],
        )
        with pytest.raises(ValidationError):  # 'iperf' not in pool's pipeline
            make_set(experiments=[make_experiment(dynamic=d2)])
        ok_nodes = [NodeDecl(name="pool", kind="pool", pipeline=["wget", "iperf"])]
        make_set(nodes=ok_nodes, experiments=[make_experiment(dynamic=d2)])
