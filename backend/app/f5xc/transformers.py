"""Transform F5 XC object JSON shapes into DB-ready dicts.

Notes on F5 XC quirks:
  - `certificate_url` uses `string:///<base64-PEM>` URI form for inline certs.
  - Auto-certs expose expiry at `spec.auto_cert_info.auto_cert_expiry` (ISO-8601).
  - HTTP LB advertise mode is a protobuf oneof: `advertise_on_public_default_vip`,
    `advertise_custom`, `advertise_on_public`, `do_not_advertise`.
  - HTTPS mode is a oneof on the spec: `http`, `https`, `https_auto_cert`.
  - Origin servers use a oneof for address: `public_ip`, `private_ip`, `public_name`,
    `private_name`, `k8s_service`, `consul_service`.
  - app_firewall enforcement is a oneof: `blocking`, `monitoring`.
  - service_policy default action is one of `allow_list`, `deny_list`, `legacy_default_action`.
  - bot_defense protected_app_endpoints is a list with mitigation actions per entry.
"""
from __future__ import annotations

import base64
import re
from datetime import UTC, datetime
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.x509.oid import NameOID

from app.logging_config import get_logger

log = get_logger(__name__)

ALL_RE_SITES_SENTINEL = "__all_re__"

# ---------------------------------------------------------------------------
# Cert parsing
# ---------------------------------------------------------------------------
_STRING_URL_PREFIX = re.compile(r"^string:///", re.IGNORECASE)


def _decode_cert_pem(cert_url: str) -> str | None:
    if not cert_url or not _STRING_URL_PREFIX.match(cert_url):
        return None
    b64 = _STRING_URL_PREFIX.sub("", cert_url, count=1)
    try:
        return base64.b64decode(b64).decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("cert_pem_decode_failed", error=str(exc))
        return None


def _parse_first_cert_from_pem(pem: str) -> x509.Certificate | None:
    try:
        return x509.load_pem_x509_certificate(pem.encode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("cert_parse_failed", error=str(exc))
        return None


def _cert_common_name(name: x509.Name) -> str | None:
    try:
        return name.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value  # type: ignore[return-value]
    except IndexError:
        return None


def _cert_sans(cert: x509.Certificate) -> list[str]:
    try:
        ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        return [str(n) for n in ext.value.get_values_for_type(x509.DNSName)]
    except x509.ExtensionNotFound:
        return []


def extract_cert_fields(spec: dict[str, Any]) -> dict[str, Any]:
    auto_info = spec.get("auto_cert_info") or {}
    is_auto = bool(auto_info)

    not_after: datetime | None = None
    not_before: datetime | None = None
    subject: str | None = None
    issuer: str | None = None
    san: list[str] = []
    serial: str | None = None
    fingerprint: str | None = None

    pem = _decode_cert_pem(spec.get("certificate_url") or "")
    cert = _parse_first_cert_from_pem(pem) if pem else None
    if cert is not None:
        not_before = cert.not_valid_before_utc
        not_after = cert.not_valid_after_utc
        subject = _cert_common_name(cert.subject) or cert.subject.rfc4514_string()
        issuer = _cert_common_name(cert.issuer) or cert.issuer.rfc4514_string()
        san = _cert_sans(cert)
        serial = format(cert.serial_number, "x")
        try:
            fingerprint = cert.fingerprint(hashes.SHA256()).hex()
        except Exception:  # noqa: BLE001
            fingerprint = None

    if not_after is None and auto_info.get("auto_cert_expiry"):
        try:
            not_after = _parse_iso(auto_info["auto_cert_expiry"])
        except ValueError:
            pass
    if subject is None and auto_info.get("auto_cert_subject_name"):
        subject = auto_info["auto_cert_subject_name"]

    return {
        "subject": subject,
        "issuer": issuer,
        "san_dns": san,
        "not_before": not_before,
        "not_after": not_after,
        "serial_number": serial,
        "fingerprint_sha256": fingerprint,
        "auto_cert": is_auto,
    }


def _parse_iso(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


# ---------------------------------------------------------------------------
# HTTP Load Balancer
# ---------------------------------------------------------------------------
_ADVERTISE_KEYS = [
    "advertise_on_public_default_vip",
    "advertise_on_public",
    "advertise_custom",
    "do_not_advertise",
]
_LB_TYPE_KEYS = {"https_auto_cert": "https", "https": "https", "http": "http"}


def _extract_advertised_sites(spec: dict[str, Any]) -> list[str]:
    if "advertise_on_public_default_vip" in spec:
        return [ALL_RE_SITES_SENTINEL]
    if "do_not_advertise" in spec:
        return []
    if "advertise_on_public" in spec:
        return [ALL_RE_SITES_SENTINEL]
    if "advertise_custom" in spec:
        sites: list[str] = []
        for entry in (spec["advertise_custom"].get("advertise_where") or []):
            if "site" in entry:
                site_ref = (entry["site"] or {}).get("site") or {}
                if site_ref.get("name"):
                    sites.append(site_ref["name"])
            elif "virtual_site" in entry:
                vs_ref = (entry["virtual_site"] or {}).get("virtual_site") or {}
                if vs_ref.get("name"):
                    sites.append(f"virtual:{vs_ref['name']}")
        return sites
    return []


def extract_lb_fields(item: dict[str, Any]) -> dict[str, Any]:
    spec = item.get("get_spec") or item.get("spec") or {}
    name = item.get("name", "")
    namespace = item.get("namespace", "")

    lb_type = "unknown"
    for k, v in _LB_TYPE_KEYS.items():
        if k in spec:
            lb_type = v
            break

    advertise_mode: str | None = None
    for key in _ADVERTISE_KEYS:
        if key in spec:
            advertise_mode = key
            break

    has_waf = bool(spec.get("app_firewall"))
    has_bot_defense = bool(spec.get("bot_defense") or spec.get("bot_defense_advanced"))
    has_api_protection = bool(
        spec.get("api_protection_rules")
        or spec.get("api_discovery")
        or spec.get("enable_api_discovery")
        or spec.get("api_definition")
    )
    active_policies = (spec.get("active_service_policies") or {}).get("policies") or []
    has_service_policy = bool(active_policies) or spec.get("service_policies_from_namespace") is not None

    pool_refs: list[str] = []
    for route_pool in spec.get("default_route_pools") or []:
        pool = route_pool.get("pool") or {}
        if pool.get("name"):
            pool_refs.append(pool["name"])

    cert_ref: str | None = None
    if "https" in spec:
        tls = (spec["https"].get("tls_cert_params") or {}).get("certificates") or []
        if tls:
            cert_ref = tls[0].get("name")

    return {
        "namespace": namespace,
        "name": name,
        "domains": spec.get("domains") or [],
        "lb_type": lb_type,
        "advertise_mode": advertise_mode,
        "advertised_sites": _extract_advertised_sites(spec),
        "has_waf": has_waf,
        "has_service_policy": has_service_policy,
        "has_bot_defense": has_bot_defense,
        "has_api_protection": has_api_protection,
        "origin_pool_refs": pool_refs,
        "cert_ref": cert_ref,
        "raw_spec": spec,
    }


def extract_lb_policy_attachments(item: dict[str, Any]) -> list[dict[str, str]]:
    """Slice 3: pull every policy ref off an LB so PolicyAttachment can be built.

    Returns a list of {policy_type, policy_namespace, policy_name} dicts.
    """
    spec = item.get("get_spec") or item.get("spec") or {}
    out: list[dict[str, str]] = []

    waf = spec.get("app_firewall")
    if isinstance(waf, dict) and waf.get("name"):
        out.append({
            "policy_type": "app_firewall",
            "policy_namespace": waf.get("namespace") or "",
            "policy_name": waf["name"],
        })

    for p in (spec.get("active_service_policies") or {}).get("policies") or []:
        if isinstance(p, dict) and p.get("name"):
            out.append({
                "policy_type": "service_policy",
                "policy_namespace": p.get("namespace") or "",
                "policy_name": p["name"],
            })

    bot = spec.get("bot_defense") or spec.get("bot_defense_advanced")
    if isinstance(bot, dict):
        # Two F5 XC bot-defense shapes:
        #   1. Reference to a separate bot_defense_policy object (older / rare):
        #        bot_defense.ref = { name, namespace }
        #   2. Inline policy with protected_app_endpoints[] (modern):
        #        bot_defense.policy.protected_app_endpoints = [{metadata.name, ...}]
        ref = bot.get("ref") if isinstance(bot.get("ref"), dict) else None
        if ref and ref.get("name"):
            out.append({
                "policy_type": "bot_defense_policy",
                "policy_namespace": ref.get("namespace") or "",
                "policy_name": ref["name"],
            })
        else:
            # Inline shape — emit one synthetic bot_defense_policy attachment
            # per protected_app_endpoint. The synthetic name uses the
            # endpoint metadata.name; namespace inherits from the LB.
            policy = bot.get("policy") if isinstance(bot.get("policy"), dict) else {}
            endpoints = policy.get("protected_app_endpoints") or []
            lb_namespace = item.get("namespace") or ""
            if isinstance(endpoints, list):
                for ep in endpoints:
                    if not isinstance(ep, dict):
                        continue
                    metadata = ep.get("metadata") or {}
                    ep_name = metadata.get("name")
                    if not ep_name:
                        continue
                    out.append({
                        "policy_type": "bot_defense_policy",
                        "policy_namespace": lb_namespace,
                        "policy_name": ep_name,
                    })

    api_def = spec.get("api_definition")
    if isinstance(api_def, dict):
        for key in ("api_definitions", "api_definition_ref"):
            entries = api_def.get(key) or []
            if isinstance(entries, list):
                for entry in entries:
                    if isinstance(entry, dict) and entry.get("name"):
                        out.append({
                            "policy_type": "api_definition",
                            "policy_namespace": entry.get("namespace") or "",
                            "policy_name": entry["name"],
                        })
        if api_def.get("name"):
            out.append({
                "policy_type": "api_definition",
                "policy_namespace": api_def.get("namespace") or "",
                "policy_name": api_def["name"],
            })

    return out


# ---------------------------------------------------------------------------
# Origin pool
# ---------------------------------------------------------------------------
def _origin_address(origin: dict[str, Any]) -> str:
    for key in ("public_ip", "private_ip"):
        if key in origin:
            ip = origin[key].get("ip") if isinstance(origin[key], dict) else None
            if ip:
                return ip
    for key in ("public_name", "private_name"):
        if key in origin:
            dns = origin[key].get("dns_name") if isinstance(origin[key], dict) else None
            if dns:
                return dns
    if "k8s_service" in origin:
        return f"k8s://{origin['k8s_service'].get('service_name', '')}"
    if "consul_service" in origin:
        return f"consul://{origin['consul_service'].get('service_name', '')}"
    return "unknown"


def extract_pool_fields(item: dict[str, Any]) -> dict[str, Any]:
    spec = item.get("get_spec") or item.get("spec") or {}
    return {
        "namespace": item.get("namespace", ""),
        "name": item.get("name", ""),
        "port": spec.get("port"),
        "lb_algorithm": spec.get("loadbalancer_algorithm"),
        "origin_count": len(spec.get("origin_servers") or []),
        "origin_addresses": [_origin_address(o) for o in (spec.get("origin_servers") or [])],
        "healthcheck_refs": [h.get("name") for h in (spec.get("healthcheck") or []) if h.get("name")] or None,
        "raw_spec": spec,
    }


# ---------------------------------------------------------------------------
# F5 XC's `spec.site_type` enum uses several values across tenant generations:
#   modern: CUSTOMER_EDGE / REGIONAL_EDGE / INGRESS_GATEWAY / VIRTUAL_SITE
#   legacy: CE / RE / VIRTUAL_SITE
# Map all known to internal lowercase taxonomy.
_SITE_TYPE_MAP = {
    "RE": "re",
    "REGIONAL_EDGE": "re",
    "CE": "ce",
    "CUSTOMER_EDGE": "ce",
    "INGRESS_GATEWAY": "ig",
    "INGRESS_EGRESS_GATEWAY": "ig",
    "VIRTUAL_SITE": "virtual",
}

# Name-based RE detection. F5 XC RE names follow a deterministic pattern:
# `<3-or-4-char-pop-code><digit>-<3-letter-airport>` where the airport code
# matches IATA. Examples:
#   dal3-dal, dc12-ash, lon4-lhr, fra1-fra, syd1-syd, sg1-sin, nyc1-jfk
# The pattern is *internal* RE site naming; F5 has used it consistently for
# years across all global meshes.
_RE_NAME_PATTERN = re.compile(r"^[a-z]{2,4}\d+-[a-z]{3}$")


def classify_site_type_by_name(name: str) -> str:
    """Heuristic site type from name when spec.site_type isn't available.

    Returns 're' for confident RE matches, 'unknown' otherwise. Never
    classifies as 'ce' from name alone — too easy to misclassify
    operator-named CE sites.
    """
    if not name:
        return "unknown"
    if _RE_NAME_PATTERN.match(name.lower()):
        return "re"
    return "unknown"


def extract_site_fields(item: dict[str, Any]) -> dict[str, Any]:
    spec = item.get("get_spec") or item.get("spec") or {}
    sysmeta = item.get("system_metadata") or {}
    name = item.get("name", "")

    raw_type = (spec.get("site_type") or "").upper()
    site_type = _SITE_TYPE_MAP.get(raw_type)
    # If the spec didn't yield a known type (common when detail GET 404s
    # for restricted sites — typically REs in the system namespace),
    # fall back to a name-based heuristic. This catches RE sites by their
    # deterministic naming convention. CE sites that 200 on detail
    # already classified above; CE sites without spec stay 'unknown'.
    if not site_type:
        site_type = classify_site_type_by_name(name)

    return {
        "name": name,
        "site_type": site_type,
        "operational_status": sysmeta.get("operational_status"),
        "region": spec.get("region"),
        "provider": spec.get("provider"),
        "raw_spec": spec,
    }


# ---------------------------------------------------------------------------
# Origin status classifier
# ---------------------------------------------------------------------------
_RAW_STATUS_MAP = {
    "HEALTHY": "healthy",
    "UNHEALTHY": "unhealthy",
    "UNKNOWN": "warning",
    "STARTING": "warning",
    "DRAINING": "info",
}


def classify_origin_status(raw_status: str | None) -> str:
    if not raw_status:
        return "unknown"
    return _RAW_STATUS_MAP.get(raw_status.upper(), "unknown")


# ---------------------------------------------------------------------------
# Cert status classifier
# ---------------------------------------------------------------------------
def classify_cert_status(
    not_after: datetime | None, *, warn_days: int, critical_days: int,
) -> tuple[str, int | None]:
    if not_after is None:
        return "unknown", None
    now = datetime.now(UTC)
    if not_after.tzinfo is None:
        not_after = not_after.replace(tzinfo=UTC)
    delta = (not_after - now).days
    if delta < 0:
        return "expired", delta
    if delta <= critical_days:
        return "critical", delta
    if delta <= warn_days:
        return "warn", delta
    return "ok", delta


# ===========================================================================
# Slice 3 — Policy transformers
# ===========================================================================

def _is_shared(namespace: str) -> bool:
    return namespace == "shared"


# --- App Firewall (WAF) -----------------------------------------------------
def extract_app_firewall_fields(item: dict[str, Any]) -> dict[str, Any]:
    spec = item.get("get_spec") or item.get("spec") or {}
    name = item.get("name", "")
    namespace = item.get("namespace", "")

    # Enforcement mode is a protobuf oneof
    if "blocking" in spec:
        enforcement = "blocking"
    elif "monitoring" in spec:
        enforcement = "monitoring"
    else:
        enforcement = None

    # Detection settings: surface the high-level detection setting choice
    detection = None
    for key in ("default_detection_settings", "default_violation_settings", "detection_settings"):
        if key in spec:
            detection = key
            break

    # Anonymization
    anon = None
    if "default_anonymization" in spec:
        a = spec["default_anonymization"]
        # F5 XC anonymization is a oneof with keys like
        # "default_anonymization" / "custom_anonymization" / "disable_anonymization"
        if isinstance(a, dict):
            anon = next(iter(a.keys()), None)
        elif isinstance(a, str):
            anon = a

    # Default bot setting
    bot_setting = None
    if "default_bot_setting" in spec:
        b = spec["default_bot_setting"]
        if isinstance(b, dict):
            bot_setting = next(iter(b.keys()), None)
        elif isinstance(b, str):
            bot_setting = b

    # Signature categories — F5 XC stores this in a structured nested form;
    # we collect anything resembling a "category" / "violation_settings" name.
    sig_categories: list[str] = []
    sig_block = spec.get("violation_settings") or {}
    if isinstance(sig_block, dict):
        for k in sig_block:
            sig_categories.append(k)
    # Also surface enabled OWASP / CC / SSN / PII flags from common shapes
    for flag, label in [
        ("blocking_settings", "blocking"),
        ("default_attack_categories_action", "default_attack_categories"),
    ]:
        if flag in spec:
            sig_categories.append(label)

    # Blocked attack types
    blocked_attack_types: list[str] = []
    bs = spec.get("blocking_settings") or {}
    if isinstance(bs, dict):
        for k, v in bs.items():
            if isinstance(v, dict) and v.get("action") in ("BLOCK", "BLOCKING"):
                blocked_attack_types.append(k)
            elif isinstance(v, str) and v in ("BLOCK", "BLOCKING"):
                blocked_attack_types.append(k)

    # Counts
    custom_rules = spec.get("custom_anonymization") or spec.get("custom_violation_actions") or []
    if isinstance(custom_rules, dict):
        custom_rule_count = len(custom_rules.get("rules") or custom_rules.get("custom_rules") or [])
    elif isinstance(custom_rules, list):
        custom_rule_count = len(custom_rules)
    else:
        custom_rule_count = 0

    exclusion_rule_count = 0
    if isinstance(spec.get("violation_settings_choice"), dict):
        ex = spec["violation_settings_choice"].get("exclusions") or []
        if isinstance(ex, list):
            exclusion_rule_count = len(ex)
    if isinstance(spec.get("exclusion_rules"), list):
        exclusion_rule_count = len(spec["exclusion_rules"])

    # Allowed response codes (sometimes a list of ints, sometimes wrapped)
    allowed_codes: list[int] | None = None
    arc = spec.get("allowed_response_codes")
    if isinstance(arc, dict):
        codes = arc.get("response_code") or arc.get("response_codes") or []
        if isinstance(codes, list):
            allowed_codes = [c for c in codes if isinstance(c, int)]
    elif isinstance(arc, list):
        allowed_codes = [c for c in arc if isinstance(c, int)]

    return {
        "namespace": namespace,
        "name": name,
        "is_shared": _is_shared(namespace),
        "enforcement_mode": enforcement,
        "default_anonymization": anon,
        "default_bot_setting": bot_setting,
        "detection_settings": detection,
        "enabled_signature_categories": sorted(set(sig_categories)),
        "blocked_attack_types": sorted(set(blocked_attack_types)),
        "custom_rule_count": custom_rule_count,
        "exclusion_rule_count": exclusion_rule_count,
        "allowed_response_codes": allowed_codes,
        "raw_spec": spec,
    }


# --- Service Policy ---------------------------------------------------------
def extract_service_policy_fields(item: dict[str, Any]) -> dict[str, Any]:
    spec = item.get("get_spec") or item.get("spec") or {}
    name = item.get("name", "")
    namespace = item.get("namespace", "")

    # Default action — F5 XC stores under one of:
    #   default_action_choice.{allow_list, deny_list, legacy_default_action_next_policy, ...}
    default_action: str | None = None
    dac = spec.get("default_action_choice") or {}
    if isinstance(dac, dict) and dac:
        first_key = next(iter(dac.keys()), None)
        if first_key:
            mapping = {
                "allow_list": "ALLOW",
                "deny_list": "DENY",
                "legacy_default_action_next_policy": "NEXT_POLICY",
                "default_action_next_policy": "NEXT_POLICY",
            }
            default_action = mapping.get(first_key, first_key.upper())

    # Rules and their actions
    rules = spec.get("rules") or []
    if not isinstance(rules, list):
        rules = []
    rule_count = len(rules)
    allow_count = 0
    deny_count = 0
    has_geo = False
    has_ip = False
    has_path = False

    for rule_entry in rules:
        if not isinstance(rule_entry, dict):
            continue
        # Rules can be wrapped inside `simple_rule` / `custom_rule` / `rule_specifier` etc.
        body = rule_entry.get("simple_rule") or rule_entry.get("custom_rule") or rule_entry
        if not isinstance(body, dict):
            continue
        action = body.get("action") or ""
        if isinstance(action, str):
            if action.upper() in ("ALLOW", "ALLOW_LIST"):
                allow_count += 1
            elif action.upper() in ("DENY", "DENY_LIST"):
                deny_count += 1
        # Surface common predicate types
        if any(k in body for k in ("country_list", "asn_list", "geo_list")):
            has_geo = True
        if any(k in body for k in ("ip_prefix_list", "ip_matcher", "client_selector_ip")):
            has_ip = True
        if any(k in body for k in ("path", "path_match", "url_matcher")):
            has_path = True

    return {
        "namespace": namespace,
        "name": name,
        "is_shared": _is_shared(namespace),
        "default_action": default_action,
        "rule_count": rule_count,
        "allow_rule_count": allow_count,
        "deny_rule_count": deny_count,
        "has_geo_rules": has_geo,
        "has_ip_rules": has_ip,
        "has_path_rules": has_path,
        "raw_spec": spec,
    }


# --- Bot Defense Policy -----------------------------------------------------
def extract_bot_defense_policy_fields(item: dict[str, Any]) -> dict[str, Any]:
    spec = item.get("get_spec") or item.get("spec") or {}
    name = item.get("name", "")
    namespace = item.get("namespace", "")

    endpoints = spec.get("protected_app_endpoints") or []
    if not isinstance(endpoints, list):
        endpoints = []

    paths: list[str] = []
    has_js = False
    has_captcha = False
    has_redirect = False
    has_block = False

    for ep in endpoints:
        if not isinstance(ep, dict):
            continue
        path_obj = ep.get("path") or {}
        if isinstance(path_obj, dict):
            for v in path_obj.values():
                if isinstance(v, str):
                    paths.append(v)

        mit = ep.get("mitigation") or ep.get("flow_label") or {}
        if isinstance(mit, dict):
            keys = mit.keys()
            if "js_challenge" in keys:
                has_js = True
            if "captcha_challenge" in keys:
                has_captcha = True
            if "redirect" in keys:
                has_redirect = True
            if "block" in keys:
                has_block = True

    return {
        "namespace": namespace,
        "name": name,
        "is_shared": _is_shared(namespace),
        "protected_endpoint_count": len(endpoints),
        "protected_paths": sorted(set(paths)),
        "has_javascript_challenge": has_js,
        "has_captcha_challenge": has_captcha,
        "has_redirect": has_redirect,
        "has_block": has_block,
        "raw_spec": spec,
    }


# --- API Definition ---------------------------------------------------------
def extract_api_definition_fields(item: dict[str, Any]) -> dict[str, Any]:
    spec = item.get("get_spec") or item.get("spec") or {}
    name = item.get("name", "")
    namespace = item.get("namespace", "")

    api_specs = spec.get("api_specs") or []
    if not isinstance(api_specs, list):
        api_specs = []

    spec_format = None
    endpoint_count = 0
    has_validation = False
    declared_endpoints: list[dict[str, Any]] = []

    _http_methods = {"get", "post", "put", "delete", "patch", "options", "head", "trace"}

    for s in api_specs:
        if not isinstance(s, dict):
            continue
        # Both swagger_spec and openapi_spec follow the same paths{} → method{} layout
        for spec_key, fmt in (("swagger_spec", "swagger"), ("openapi_spec", "openapi")):
            sub = s.get(spec_key)
            if not isinstance(sub, dict):
                continue
            spec_format = spec_format or fmt
            paths = sub.get("paths") or {}
            if not isinstance(paths, dict):
                continue
            endpoint_count += len(paths)
            for path, methods in paths.items():
                if not isinstance(methods, dict):
                    continue
                for m_key in methods:
                    if m_key.lower() in _http_methods:
                        declared_endpoints.append({
                            "method": m_key.upper(),
                            "path": path,
                        })
        if s.get("validation") or s.get("validation_rules"):
            has_validation = True

    if spec.get("validation_rules") or spec.get("api_validation_rules"):
        has_validation = True

    return {
        "namespace": namespace,
        "name": name,
        "is_shared": _is_shared(namespace),
        "spec_format": spec_format,
        "api_specs_count": len(api_specs),
        "endpoint_count": endpoint_count,
        "has_validation_rules": has_validation,
        "raw_spec": spec,
        "declared_endpoints": declared_endpoints if declared_endpoints else None,
    }
