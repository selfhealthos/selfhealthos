// Aliases over the generated OpenAPI schema. Regenerate with:
//   npm run generate:api
// If a field disappears on the backend, every use of it here fails typecheck.

import type { components } from "./schema";

export type User = components["schemas"]["UserOut"];

// Access tokens. `AccessTokenCreated` is the only shape carrying the secret,
// and only on the 201 - the database holds a hash, so nothing can return it
// afterwards.
export type AccessToken = components["schemas"]["TokenOut"];
export type AccessTokenCreated = components["schemas"]["TokenCreatedOut"];
export type TokenScope = components["schemas"]["ScopeOut"];

// Health. Prefixed on the backend too: pydantic keys the OpenAPI
// component map by class name, so an unprefixed SummaryOut here would collide
// with another app's and silently take over its shape.
export type HealthSummary = components["schemas"]["HealthSummaryOut"];
export type HealthDay = components["schemas"]["HealthDayOut"];
export type HealthMetric = components["schemas"]["HealthMetricOut"];
export type HealthTrend = components["schemas"]["HealthTrendOut"];
export type HealthIntraday = components["schemas"]["HealthIntradayOut"];
export type HealthConnection = components["schemas"]["HealthConnectionOut"];
export type HealthAuthorize = components["schemas"]["HealthAuthorizeOut"];
export type HealthSyncQueued = components["schemas"]["HealthSyncQueued"];

// The deep-dive views. One type per page, because each page asks a different
// question of the same dataset - see the note above the routes in
// `apps/health/api.py`.
export type HealthHabitHistory = components["schemas"]["HealthHabitHistoryOut"];
export type HealthHabitRow = components["schemas"]["HealthHabitRowOut"];
export type HealthHeatmap = components["schemas"]["HealthHeatmapOut"];
export type HealthHeatmapColumn = components["schemas"]["HealthHeatmapColumnOut"];
export type HealthHeatmapRow = components["schemas"]["HealthHeatmapRowOut"];
export type HealthHeatmapCell = components["schemas"]["HealthHeatmapCellOut"];
export type HealthDietLog = components["schemas"]["HealthDietLogOut"];
export type HealthDietEntry = components["schemas"]["HealthDietEntryOut"];
export type HealthGut = components["schemas"]["HealthGutOut"];
export type HealthBristolDaily = components["schemas"]["HealthBristolDailyOut"];
export type HealthBody = components["schemas"]["HealthBodyOut"];
export type HealthLabMarker = components["schemas"]["HealthLabMarkerOut"];
export type HealthNote = components["schemas"]["HealthNoteOut"];
export type HealthDoc = components["schemas"]["HealthDocOut"];
export type HealthOffice = components["schemas"]["HealthOfficeOut"];
export type HealthSleepHistory = components["schemas"]["HealthSleepHistoryOut"];
export type HealthSleepSession = components["schemas"]["HealthSleepSessionOut"];
export type HealthNight = components["schemas"]["HealthNightOut"];
export type HealthNightSegment = components["schemas"]["HealthNightSegmentOut"];
export type HealthNightDip = components["schemas"]["HealthNightDipOut"];
export type HealthHeartDay = components["schemas"]["HealthHeartDayOut"];
export type HealthHeartHistory = components["schemas"]["HealthHeartHistoryOut"];
export type HealthHeartSeries = components["schemas"]["HealthHeartSeriesOut"];
export type HealthHeartZone = components["schemas"]["HealthHeartZoneOut"];
export type HealthActivity = components["schemas"]["HealthActivityOut"];
export type HealthActivityHistory = components["schemas"]["HealthActivityHistoryOut"];
export type HealthActivityDay = components["schemas"]["HealthActivityDayOut"];
export type HealthActivitySeries = components["schemas"]["HealthActivitySeriesOut"];
