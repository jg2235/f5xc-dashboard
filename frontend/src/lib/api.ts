// Thin fetch wrapper. Stores JWT in localStorage; sends Authorization: Bearer.
const BASE_URL = "/api/v1";

// ---------------- Slice 1/2 types ----------------

export type LoadBalancerSummary = {
  id: string;
  namespace: string;
  name: string;
  domains: string[];
  lb_type: "http" | "https" | "unknown";
  advertise_mode: string | null;
  advertised_sites: string[];
  has_waf: boolean;
  has_service_policy: boolean;
  has_bot_defense: boolean;
  has_api_protection: boolean;
  origin_pool_refs: string[];
  cert_ref: string | null;
  last_seen_at: string;
};

export type LoadBalancerDetail = LoadBalancerSummary & {
  raw_spec: Record<string, unknown>;
  pools: OriginPoolSummary[];
};

export type LoadBalancerStats = {
  total: number;
  with_waf: number;
  with_bot_defense: number;
  with_api_protection: number;
  with_service_policy: number;
  https: number;
  http_only: number;
};

export type CertStatus = "ok" | "warn" | "critical" | "expired" | "unknown";

export type CertificateSummary = {
  id: string;
  namespace: string;
  name: string;
  subject: string | null;
  issuer: string | null;
  san_dns: string[];
  not_before: string | null;
  not_after: string | null;
  auto_cert: boolean;
  days_until_expiry: number | null;
  status: CertStatus;
  last_seen_at: string;
};

export type CertificateStats = {
  total: number;
  ok: number;
  warn: number;
  critical: number;
  expired: number;
};

export type OriginStatus = "healthy" | "unhealthy" | "warning" | "info" | "unknown";

export type OriginHealthCell = {
  origin_address: string;
  origin_port: number | null;
  site_name: string;
  site_type: string | null;
  raw_status: string;
  classified_status: OriginStatus;
  consecutive_failures: number;
  last_status_change: string | null;
  last_probe_at: string | null;
};

export type OriginPoolSummary = {
  id: string;
  namespace: string;
  name: string;
  port: number | null;
  lb_algorithm: string | null;
  origin_count: number;
  healthy_count: number;
  unhealthy_count: number;
  warning_count: number;
  last_healthcheck_at: string | null;
  last_seen_at: string;
};

export type OriginPoolDetail = OriginPoolSummary & {
  origin_addresses: string[];
  site_names: string[];
  healthcheck_refs: string[] | null;
  health_matrix: OriginHealthCell[];
  raw_spec: Record<string, unknown>;
};

export type PoolStats = {
  total_pools: number;
  pools_with_unhealthy: number;
  pools_with_warnings: number;
  total_origins: number;
  unhealthy_cells: number;
  warning_cells: number;
};

export type CurrentUser = {
  id: string;
  username: string;
  email: string | null;
  role: string;
  is_active: boolean;
};

// ---------------- Slice 3 policy types ----------------

export type PolicyType =
  | "app_firewall"
  | "service_policy"
  | "bot_defense_policy"
  | "api_definition";

export type PolicyTypeUrl =
  | "app_firewalls"
  | "service_policies"
  | "bot_defense_policies"
  | "api_definitions";

export const POLICY_TYPE_LABELS: Record<PolicyTypeUrl, string> = {
  app_firewalls: "App Firewall (WAF)",
  service_policies: "Service Policy",
  bot_defense_policies: "Bot Defense",
  api_definitions: "API Definition",
};

export const POLICY_TYPE_SHORT: Record<PolicyTypeUrl, string> = {
  app_firewalls: "WAF",
  service_policies: "Service",
  bot_defense_policies: "Bot",
  api_definitions: "API",
};

export type PolicyAttachmentRef = {
  lb_id: string;
  lb_name: string;
  lb_namespace: string;
};

export type PolicyBase = {
  id: string;
  namespace: string;
  name: string;
  is_shared: boolean;
  last_seen_at: string;
};

export type AppFirewallSummary = PolicyBase & {
  enforcement_mode: "blocking" | "monitoring" | null;
  enabled_signature_categories: string[];
  blocked_attack_types: string[];
  custom_rule_count: number;
  exclusion_rule_count: number;
};

export type AppFirewallDetail = AppFirewallSummary & {
  default_anonymization: string | null;
  default_bot_setting: string | null;
  detection_settings: string | null;
  allowed_response_codes: number[] | null;
  raw_spec: Record<string, unknown>;
  attached_to: PolicyAttachmentRef[];
};

export type ServicePolicySummary = PolicyBase & {
  default_action: string | null;
  rule_count: number;
  allow_rule_count: number;
  deny_rule_count: number;
  has_geo_rules: boolean;
  has_ip_rules: boolean;
  has_path_rules: boolean;
};

export type ServicePolicyDetail = ServicePolicySummary & {
  raw_spec: Record<string, unknown>;
  attached_to: PolicyAttachmentRef[];
};

export type BotDefensePolicySummary = PolicyBase & {
  protected_endpoint_count: number;
  has_javascript_challenge: boolean;
  has_captcha_challenge: boolean;
  has_redirect: boolean;
  has_block: boolean;
};

export type BotDefensePolicyDetail = BotDefensePolicySummary & {
  protected_paths: string[];
  raw_spec: Record<string, unknown>;
  attached_to: PolicyAttachmentRef[];
};

export type ApiDefinitionSummary = PolicyBase & {
  spec_format: string | null;
  api_specs_count: number;
  endpoint_count: number;
  has_validation_rules: boolean;
};

export type ApiDefinitionDetail = ApiDefinitionSummary & {
  raw_spec: Record<string, unknown>;
  attached_to: PolicyAttachmentRef[];
};

export type AnyPolicySummary =
  | AppFirewallSummary
  | ServicePolicySummary
  | BotDefensePolicySummary
  | ApiDefinitionSummary;

export type AnyPolicyDetail =
  | AppFirewallDetail
  | ServicePolicyDetail
  | BotDefensePolicyDetail
  | ApiDefinitionDetail;

export type AttachedPolicyRef = {
  policy_type: PolicyType;
  policy_namespace: string;
  policy_name: string;
  is_shared: boolean;
  policy_id: string | null;
};

export type PolicyTypeStats = {
  total: number;
  shared: number;
  local: number;
  unattached: number;
};

export type PolicyStats = {
  app_firewall: PolicyTypeStats;
  service_policy: PolicyTypeStats;
  bot_defense_policy: PolicyTypeStats;
  api_definition: PolicyTypeStats;
};

// ---------------- Slice 4 WAF analytics types ----------------

export type WafSparklinePoint = {
  bucket_time: string;
  request_count: number;
  blocked_count: number;
  monitored_count: number;
  error_count: number;
};

export type WafSparkline = {
  lb_namespace: string | null;
  lb_name: string | null;
  points: WafSparklinePoint[];
  total_requests: number;
  total_blocked: number;
  total_monitored: number;
  total_errors: number;
};

export type TopKEntry = { key: string; count: number };

export type WafTopK = {
  dimension: string;
  entries: TopKEntry[];
};

export type WafEventSummary = {
  event_time: string;
  lb_namespace: string;
  lb_name: string;
  action: "ALLOW" | "BLOCK" | "MONITOR" | string;
  source_ip: string | null;
  source_country: string | null;
  method: string | null;
  url: string | null;
  response_code: number | null;
  primary_signature: string | null;
  severity: string | null;
};

export type WafOverviewStats = {
  window_minutes: number;
  total_requests: number;
  total_blocked: number;
  total_monitored: number;
  total_errors: number;
  block_rate_pct: number;
};

export type TopKDim =
  | "source_ip"
  | "source_country"
  | "primary_signature"
  | "url"
  | "lb_name"
  | "action";

// ---------------- Slice 5 Bot analytics types ----------------

export type BotSparklinePoint = {
  bucket_time: string;
  request_count: number;
  challenge_count: number;
  block_count: number;
  allow_count: number;
};

export type BotSparkline = {
  lb_namespace: string | null;
  lb_name: string | null;
  points: BotSparklinePoint[];
  total_requests: number;
  total_challenges: number;
  total_blocks: number;
  total_allows: number;
};

export type BotTopKEntry = { key: string; count: number };

export type BotTopK = {
  dimension: string;
  entries: BotTopKEntry[];
};

export type BotEventSummary = {
  event_time: string;
  lb_namespace: string;
  lb_name: string;
  source: "standard" | "bd_advanced" | string;
  action: "ALLOW" | "BLOCK" | "CHALLENGE" | "MONITOR" | string;
  bot_category: string;
  confidence_bucket: "low" | "medium" | "high" | "unknown" | string;
  confidence_score: number | null;
  challenge_result: "passed" | "failed" | "abandoned" | "not_issued" | string;
  challenge_type: string | null;
  source_ip: string | null;
  source_country: string | null;
  source_asn: number | null;
  method: string | null;
  endpoint_path: string | null;
  ua_family: string | null;
  user_agent: string | null;
  device_anomalies: string[] | null;
};

export type BotOverviewStats = {
  window_minutes: number;
  total_requests: number;
  total_challenges: number;
  total_blocks: number;
  total_allows: number;
  challenge_rate_pct: number;
  block_rate_pct: number;
};

export type BotEndpointStats = {
  endpoint_path: string;
  method: string | null;
  total_events: number;
  challenge_count: number;
  block_count: number;
  allow_count: number;
  monitor_count: number;
  distinct_source_ips: number;
  top_bot_category: string | null;
  last_seen_at: string;
};

export type BotTopKDim =
  | "source_ip"
  | "source_country"
  | "ua_family"
  | "endpoint_path"
  | "challenge_result"
  | "bot_category"
  | "action"
  | "lb_name"
  | "source_asn";

// ---------------- Slice 6 API analytics types ----------------

export type ApiDiscoveryStateOut = {
  lb_namespace: string;
  lb_name: string;
  state: "learning" | "mature" | "enforcing" | "disabled" | "unknown" | string;
  confidence_score: number | null;
  total_endpoints_discovered: number;
  total_traffic_samples: number;
  last_learning_update: string | null;
  state_changed_at: string | null;
};

export type ApiOverviewStats = {
  total_endpoints: number;
  shadow_endpoints: number;
  declared_endpoints: number;
  state_counts: Record<string, number>;
  avg_p99_latency_ms: number | null;
  error_rate_pct: number;
  window_minutes: number;
};

export type ApiEndpointSummary = {
  id: string;
  lb_namespace: string;
  lb_name: string;
  method: string;
  endpoint_path: string;
  is_shadow: boolean;
  api_definition_namespace: string | null;
  api_definition_name: string | null;
  discovery_confidence: number | null;
  total_request_samples: number;
  last_seen_at: string | null;
  auth_type: string | null;
  response_codes: number[] | null;
};

export type ApiEndpointDetail = ApiEndpointSummary & {
  first_seen_at: string | null;
  query_params: Array<Record<string, unknown>> | null;
  body_params: Array<Record<string, unknown>> | null;
};

export type ApiSparklinePoint = {
  bucket_time: string;
  request_count: number;
  error_4xx_count: number;
  error_5xx_count: number;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
  latency_p99_ms: number | null;
};

export type ApiEndpointSparkline = {
  method: string | null;
  endpoint_path: string | null;
  points: ApiSparklinePoint[];
  total_requests: number;
  total_4xx: number;
  total_5xx: number;
  max_p99_ms: number | null;
};

export type ApiTopKEntry = { key: string; count: number };

export type ApiTopK = {
  dimension: string;
  entries: ApiTopKEntry[];
};

export type ApiTopKDim =
  | "volume"
  | "latency_p99"
  | "error_rate"
  | "shadow"
  | "method"
  | "auth_type";

// ---------------- Slice 7 Security analytics + alerts types ----------------

export type SecurityOverviewStats = {
  window_minutes: number;
  total_attackers: number;
  countries_seen: number;
  top_country: string | null;
  top_country_count: number;
  total_waf_blocks: number;
  total_bot_interventions: number;
  total_api_4xx: number;
  open_alerts: number;
  critical_alerts: number;
};

export type GeoEntry = { country: string; count: number };

export type AttackerProfileSummary = {
  id: string;
  source_ip: string;
  source_asn: number | null;
  source_country: string | null;
  waf_block_count: number;
  waf_monitor_count: number;
  bot_block_count: number;
  bot_challenge_count: number;
  api_4xx_count: number;
  total_events: number;
  top_endpoint: string | null;
  top_signature: string | null;
  distinct_lbs: number;
  first_seen_at: string | null;
  last_seen_at: string | null;
};

export type AttackerTimelineEntry = {
  event_time: string;
  signal: "waf" | "bot" | string;
  action: string;
  lb_name: string | null;
  method: string | null;
  endpoint: string | null;
  classifier: string | null;
  rsp_code: number | null;
  severity: string | null;
  extra: Record<string, unknown> | null;
};

export type AlertOut = {
  id: string;
  rule_id: string;
  severity: "critical" | "warning" | "info" | string;
  status: "open" | "acknowledged" | "resolved" | string;
  dedupe_key: string;
  title: string;
  description: string;
  context: Record<string, unknown>;
  occurrence_count: number;
  first_seen_at: string;
  last_seen_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
};

export type AlertSummaryStats = {
  open: number;
  acknowledged: number;
  resolved: number;
  critical: number;
  warning: number;
  info: number;
};

export type AlertActionResult = {
  id: string;
  status: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
};

// ---------------- Auth + fetch wrapper ----------------

const TOKEN_KEY = "f5xc_token";

export const auth = {
  getToken(): string | null {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(TOKEN_KEY);
  },
  setToken(t: string) {
    window.localStorage.setItem(TOKEN_KEY, t);
  },
  clear() {
    window.localStorage.removeItem(TOKEN_KEY);
  },
};

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = auth.getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (!headers.has("Content-Type") && init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const resp = await fetch(`${BASE_URL}${path}`, { ...init, headers });
  if (resp.status === 401) {
    auth.clear();
    if (typeof window !== "undefined" && window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
    throw new ApiError(401, "Unauthorized");
  }
  if (!resp.ok) {
    const text = await resp.text();
    throw new ApiError(resp.status, text || resp.statusText);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

export const api = {
  login: async (
    username: string,
    password: string,
  ): Promise<{ access_token: string; expires_in: number }> => {
    const body = new URLSearchParams({ username, password });
    const resp = await fetch(`${BASE_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    if (!resp.ok) {
      throw new ApiError(
        resp.status,
        resp.status === 401 ? "Invalid credentials" : await resp.text(),
      );
    }
    return resp.json();
  },
  me: () => request<CurrentUser>("/auth/me"),

  // Load balancers
  listLoadBalancers: () => request<LoadBalancerSummary[]>("/loadbalancers"),
  lbStats: () => request<LoadBalancerStats>("/loadbalancers/stats"),
  getLoadBalancer: (id: string) => request<LoadBalancerDetail>(`/loadbalancers/${id}`),
  getLoadBalancerPolicies: (id: string) => request<AttachedPolicyRef[]>(`/loadbalancers/${id}/policies`),

  // Certificates
  listCertificates: (status?: CertStatus) =>
    request<CertificateSummary[]>(`/certificates${status ? `?status=${status}` : ""}`),
  certStats: () => request<CertificateStats>("/certificates/stats"),

  // Pools
  listPools: () => request<OriginPoolSummary[]>("/pools"),
  poolStats: () => request<PoolStats>("/pools/stats"),
  getPool: (id: string) => request<OriginPoolDetail>(`/pools/${id}`),

  // Policies (slice 3)
  policyStats: () => request<PolicyStats>("/policies/stats"),
  listPolicies: <T extends AnyPolicySummary>(
    type: PolicyTypeUrl,
    scope?: "shared" | "local",
  ) => request<T[]>(`/policies/${type}${scope ? `?scope=${scope}` : ""}`),
  getPolicy: <T extends AnyPolicyDetail>(type: PolicyTypeUrl, id: string) =>
    request<T>(`/policies/${type}/${id}`),

  // WAF analytics (slice 4)
  wafOverview: (windowMinutes = 60) =>
    request<WafOverviewStats>(`/analytics/waf/overview?window_minutes=${windowMinutes}`),
  wafSparkline: (params: { lbId?: string; hours?: number } = {}) => {
    const qs = new URLSearchParams();
    if (params.lbId) qs.set("lb_id", params.lbId);
    if (params.hours) qs.set("hours", String(params.hours));
    const tail = qs.toString() ? `?${qs.toString()}` : "";
    return request<WafSparkline>(`/analytics/waf/sparkline${tail}`);
  },
  wafTopK: (params: {
    dim: TopKDim;
    hours?: number;
    action?: "BLOCK" | "MONITOR" | "ALLOW";
    lbId?: string;
  }) => {
    const qs = new URLSearchParams({ dim: params.dim });
    if (params.hours) qs.set("hours", String(params.hours));
    if (params.action) qs.set("action", params.action);
    if (params.lbId) qs.set("lb_id", params.lbId);
    return request<WafTopK>(`/analytics/waf/topk?${qs.toString()}`);
  },
  wafEvents: (params: {
    limit?: number;
    hours?: number;
    action?: "BLOCK" | "MONITOR" | "ALLOW";
    severity?: string;
    lbId?: string;
  } = {}) => {
    const qs = new URLSearchParams();
    if (params.limit) qs.set("limit", String(params.limit));
    if (params.hours) qs.set("hours", String(params.hours));
    if (params.action) qs.set("action", params.action);
    if (params.severity) qs.set("severity", params.severity);
    if (params.lbId) qs.set("lb_id", params.lbId);
    const tail = qs.toString() ? `?${qs.toString()}` : "";
    return request<WafEventSummary[]>(`/analytics/waf/events${tail}`);
  },
  triggerSyncWafEvents: () =>
    request<Record<string, unknown>>("/sync/waf-events", { method: "POST" }),
  triggerSyncWafMetrics: () =>
    request<Record<string, unknown>>("/sync/waf-metrics", { method: "POST" }),

  // Bot analytics (slice 5)
  botOverview: (windowMinutes = 60) =>
    request<BotOverviewStats>(`/analytics/bot/overview?window_minutes=${windowMinutes}`),
  botSparkline: (params: { lbId?: string; hours?: number } = {}) => {
    const qs = new URLSearchParams();
    if (params.lbId) qs.set("lb_id", params.lbId);
    if (params.hours) qs.set("hours", String(params.hours));
    const tail = qs.toString() ? `?${qs.toString()}` : "";
    return request<BotSparkline>(`/analytics/bot/sparkline${tail}`);
  },
  botTopK: (params: {
    dim: BotTopKDim;
    hours?: number;
    action?: "BLOCK" | "CHALLENGE" | "ALLOW" | "MONITOR";
    botCategory?: string;
    lbId?: string;
  }) => {
    const qs = new URLSearchParams({ dim: params.dim });
    if (params.hours) qs.set("hours", String(params.hours));
    if (params.action) qs.set("action", params.action);
    if (params.botCategory) qs.set("bot_category", params.botCategory);
    if (params.lbId) qs.set("lb_id", params.lbId);
    return request<BotTopK>(`/analytics/bot/topk?${qs.toString()}`);
  },
  botEvents: (params: {
    limit?: number;
    hours?: number;
    action?: "BLOCK" | "CHALLENGE" | "ALLOW" | "MONITOR";
    source?: "standard" | "bd_advanced";
    botCategory?: string;
    lbId?: string;
  } = {}) => {
    const qs = new URLSearchParams();
    if (params.limit) qs.set("limit", String(params.limit));
    if (params.hours) qs.set("hours", String(params.hours));
    if (params.action) qs.set("action", params.action);
    if (params.source) qs.set("source", params.source);
    if (params.botCategory) qs.set("bot_category", params.botCategory);
    if (params.lbId) qs.set("lb_id", params.lbId);
    const tail = qs.toString() ? `?${qs.toString()}` : "";
    return request<BotEventSummary[]>(`/analytics/bot/events${tail}`);
  },
  botEndpoints: (params: { hours?: number; limit?: number; lbId?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.hours) qs.set("hours", String(params.hours));
    if (params.limit) qs.set("limit", String(params.limit));
    if (params.lbId) qs.set("lb_id", params.lbId);
    const tail = qs.toString() ? `?${qs.toString()}` : "";
    return request<BotEndpointStats[]>(`/analytics/bot/endpoints${tail}`);
  },
  triggerSyncBotEvents: () =>
    request<Record<string, unknown>>("/sync/bot-events", { method: "POST" }),
  triggerSyncBotMetrics: () =>
    request<Record<string, unknown>>("/sync/bot-metrics", { method: "POST" }),

  // API analytics (slice 6)
  apiOverview: (windowMinutes = 60) =>
    request<ApiOverviewStats>(`/analytics/api/overview?window_minutes=${windowMinutes}`),
  apiDiscoveryState: () =>
    request<ApiDiscoveryStateOut[]>("/analytics/api/discovery-state"),
  apiEndpoints: (params: {
    limit?: number;
    offset?: number;
    shadowOnly?: boolean;
    lbId?: string;
    authType?: string;
    sort?: "volume" | "last_seen" | "method" | "path";
  } = {}) => {
    const qs = new URLSearchParams();
    if (params.limit) qs.set("limit", String(params.limit));
    if (params.offset) qs.set("offset", String(params.offset));
    if (params.shadowOnly) qs.set("shadow_only", "true");
    if (params.lbId) qs.set("lb_id", params.lbId);
    if (params.authType) qs.set("auth_type", params.authType);
    if (params.sort) qs.set("sort", params.sort);
    const tail = qs.toString() ? `?${qs.toString()}` : "";
    return request<ApiEndpointSummary[]>(`/analytics/api/endpoints${tail}`);
  },
  apiEndpointDetail: (id: string) =>
    request<ApiEndpointDetail>(`/analytics/api/endpoints/${id}`),
  apiEndpointSparkline: (id: string, hours = 24) =>
    request<ApiEndpointSparkline>(`/analytics/api/endpoints/${id}/sparkline?hours=${hours}`),
  apiTopK: (params: { dim: ApiTopKDim; hours?: number; lbId?: string }) => {
    const qs = new URLSearchParams({ dim: params.dim });
    if (params.hours) qs.set("hours", String(params.hours));
    if (params.lbId) qs.set("lb_id", params.lbId);
    return request<ApiTopK>(`/analytics/api/topk?${qs.toString()}`);
  },
  triggerSyncApiEndpoints: () =>
    request<Record<string, unknown>>("/sync/api-endpoints", { method: "POST" }),
  triggerSyncApiDiscoveryState: () =>
    request<Record<string, unknown>>("/sync/api-discovery-state", { method: "POST" }),
  triggerSyncApiMetrics: () =>
    request<Record<string, unknown>>("/sync/api-metrics", { method: "POST" }),

  // Security analytics (slice 7)
  securityOverview: (windowMinutes = 1440) =>
    request<SecurityOverviewStats>(`/analytics/security/overview?window_minutes=${windowMinutes}`),
  securityGeo: (params: { hours?: number; signal?: "all" | "waf" | "bot" } = {}) => {
    const qs = new URLSearchParams();
    if (params.hours) qs.set("hours", String(params.hours));
    if (params.signal) qs.set("signal", params.signal);
    const tail = qs.toString() ? `?${qs.toString()}` : "";
    return request<GeoEntry[]>(`/analytics/security/geo${tail}`);
  },
  securityAttackers: (params: {
    limit?: number;
    offset?: number;
    country?: string;
    sort?: "total" | "waf" | "bot" | "last_seen";
  } = {}) => {
    const qs = new URLSearchParams();
    if (params.limit) qs.set("limit", String(params.limit));
    if (params.offset) qs.set("offset", String(params.offset));
    if (params.country) qs.set("country", params.country);
    if (params.sort) qs.set("sort", params.sort);
    const tail = qs.toString() ? `?${qs.toString()}` : "";
    return request<AttackerProfileSummary[]>(`/analytics/security/attackers${tail}`);
  },
  securityAttackerTimeline: (sourceIp: string, hours = 24, limit = 200) =>
    request<AttackerTimelineEntry[]>(
      `/analytics/security/attackers/${encodeURIComponent(sourceIp)}/timeline?hours=${hours}&limit=${limit}`,
    ),
  // Alerts (slice 7)
  listAlerts: (params: {
    status?: "all" | "open" | "acknowledged" | "resolved";
    severity?: "all" | "critical" | "warning" | "info";
    rule_id?: string;
    limit?: number;
    offset?: number;
  } = {}) => {
    const qs = new URLSearchParams();
    if (params.status) qs.set("status", params.status);
    if (params.severity) qs.set("severity", params.severity);
    if (params.rule_id) qs.set("rule_id", params.rule_id);
    if (params.limit) qs.set("limit", String(params.limit));
    if (params.offset) qs.set("offset", String(params.offset));
    const tail = qs.toString() ? `?${qs.toString()}` : "";
    return request<AlertOut[]>(`/alerts${tail}`);
  },
  alertSummary: () => request<AlertSummaryStats>("/alerts/summary"),
  alertDetail: (id: string) => request<AlertOut>(`/alerts/${id}`),
  acknowledgeAlert: (id: string) =>
    request<AlertActionResult>(`/alerts/${id}/acknowledge`, { method: "POST" }),
  resolveAlert: (id: string) =>
    request<AlertActionResult>(`/alerts/${id}/resolve`, { method: "POST" }),
  reopenAlert: (id: string) =>
    request<AlertActionResult>(`/alerts/${id}/reopen`, { method: "POST" }),
  triggerAttackerProfilesSync: () =>
    request<Record<string, unknown>>("/sync/attacker-profiles", { method: "POST" }),
  triggerAlertEvaluation: () =>
    request<Record<string, unknown>>("/sync/alerts/evaluate", { method: "POST" }),

  // Sync
  triggerSyncAll: () => request<Record<string, unknown>>("/sync/all", { method: "POST" }),
  triggerSyncHealthchecks: () =>
    request<Record<string, unknown>>("/sync/healthchecks", { method: "POST" }),
  triggerSyncPolicies: () => request<Record<string, unknown>>("/sync/policies", { method: "POST" }),
};

export { ApiError };
