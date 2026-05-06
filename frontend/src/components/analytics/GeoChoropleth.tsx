"use client";

import type { GeoEntry } from "@/lib/api";
import { cn } from "@/lib/cn";

/**
 * Country-level event distribution.
 *
 * Slice 7 decision (option A for question 2): country-level only. We render
 * as an enhanced bar list rather than a true choropleth — true choropleth
 * requires ~80kb of TopoJSON country boundary data, which is overkill for
 * the dataset (typically 10-30 countries max in any given window).
 *
 * The bar list is more readable than a colored map at this granularity, and
 * the country flag emoji + ISO code provide the geographic anchor without
 * the complexity. If choropleth is needed later, the data shape supports
 * dropping in react-simple-maps without an API change.
 */
export function GeoChoropleth({
  entries,
  height = 320,
}: {
  entries: GeoEntry[];
  height?: number;
}) {
  if (entries.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded border border-dashed border-carbon-600 bg-carbon-800/40 font-mono text-[10px] text-carbon-300"
        style={{ height }}
      >
        no geo data in this window — wait for the next sync cycle
      </div>
    );
  }

  const max = Math.max(...entries.map((e) => e.count));

  return (
    <div
      className="space-y-1.5 overflow-y-auto pr-2"
      style={{ maxHeight: height }}
    >
      {entries.map((e) => {
        const pct = max > 0 ? Math.round((e.count / max) * 100) : 0;
        return (
          <div key={e.country} className="relative">
            <div
              className="absolute inset-y-0 left-0 rounded-sm bg-accent-red/30"
              style={{ width: `${pct}%` }}
            />
            <div className="relative flex items-center justify-between px-3 py-1.5 font-mono text-xs">
              <div className="flex items-center gap-2">
                <span className="text-base leading-none">
                  {countryFlag(e.country)}
                </span>
                <span className="text-carbon-100">{e.country}</span>
                <span className="text-[10px] text-carbon-300">
                  {countryName(e.country)}
                </span>
              </div>
              <span
                className={cn(
                  "tabular-nums",
                  e.count > max * 0.5 ? "text-accent-red" : "text-carbon-100",
                )}
              >
                {e.count.toLocaleString()}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ISO 3166-1 alpha-2 → emoji flag (unicode regional indicators)
function countryFlag(code: string): string {
  if (!code || code.length !== 2) return "🏳️";
  const A = 0x1f1e6;
  const A_OFFSET = "A".charCodeAt(0);
  return String.fromCodePoint(
    A + code.charCodeAt(0) - A_OFFSET,
    A + code.charCodeAt(1) - A_OFFSET,
  );
}

// Minimal ISO → name mapping for the most-seen countries in F5 XC data.
// Falls back to the code if not in the map.
const COUNTRY_NAMES: Record<string, string> = {
  US: "United States",
  CN: "China",
  RU: "Russia",
  IN: "India",
  BR: "Brazil",
  DE: "Germany",
  GB: "United Kingdom",
  FR: "France",
  CA: "Canada",
  AU: "Australia",
  JP: "Japan",
  KR: "South Korea",
  VN: "Vietnam",
  IR: "Iran",
  TR: "Turkey",
  UA: "Ukraine",
  PL: "Poland",
  NL: "Netherlands",
  SG: "Singapore",
  HK: "Hong Kong",
  TW: "Taiwan",
  MX: "Mexico",
  AR: "Argentina",
  ZA: "South Africa",
  NG: "Nigeria",
  EG: "Egypt",
  IT: "Italy",
  ES: "Spain",
  ID: "Indonesia",
  TH: "Thailand",
  PH: "Philippines",
  MY: "Malaysia",
  SE: "Sweden",
  NO: "Norway",
  FI: "Finland",
  DK: "Denmark",
  CH: "Switzerland",
  AT: "Austria",
  BE: "Belgium",
  IE: "Ireland",
  IL: "Israel",
};

function countryName(code: string): string {
  return COUNTRY_NAMES[code?.toUpperCase()] ?? "—";
}
