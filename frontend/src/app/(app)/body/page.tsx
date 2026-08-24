import { serverGet } from "@/lib/api/server";
import type { HealthBody } from "@/lib/api/types";

import { LineChart } from "../charts";
import { Card, Empty, LONG_RANGES, num, PageHeader, RangeTabs, shortDate, Stat } from "../ui";
import { BandLegend, BodyTable } from "./BodyTable";
import { RecordMeasurement, RecordProfile, RecordWeight } from "./RecordBody";

export const dynamic = "force-dynamic";

/**
 * Body composition: weight, BMI, waist, and the ratio between waist and
 * height.
 *
 * Four numbers that only mean something together. A weight is not
 * interpretable without a height; a waist is not interpretable without one
 * either. So they share a page, share a table, and are recorded here rather
 * than only arriving from the phone.
 *
 * **Waist-to-height is the number to read, and it is not on the chart.** It
 * belongs to the table because it moves over months and takes a tape measure,
 * so a line of eleven points across two years is a worse rendering of it than
 * eleven coloured cells. It stays the number this page leads with in the stat
 * row: it needs no scales, it catches central adiposity that BMI misses in
 * someone of perfectly normal weight, and the healthy limit is one a person
 * can remember — keep your waist under half your height.
 *
 * **Why weight and BMI share a chart, with two axes.** A second axis is
 * normally a lie: two unrelated quantities scaled until they cross somewhere
 * flattering. It is honest here because these are the *same* quantity in two
 * units — at a fixed height BMI is weight times a constant — so the mapping
 * between the axes is arithmetic rather than a choice, and neither axis is
 * stretched to make the lines meet anywhere in particular.
 *
 * The consequence is worth stating, because it is visible: the BMI axis is
 * widened to fit the healthy band, so the BMI line is drawn over a taller
 * range than the weight line and its slope reads gentler. That is the same
 * trade `LineChart`'s `normalBand` already documents — vertical resolution
 * spent to put the boundary on screen — and here it is the whole point of the
 * second axis. Where the trace sits relative to 18.5–25 is a fact the kilogram
 * axis cannot express: 78 kg is inside that band for one person and well above
 * it for another. Read the two lines as one measurement against two rulers,
 * and the shapes off the axis each is labelled with.
 *
 * The fitness self-tests used to live here and now have their own page. Grip
 * strength is not a body measurement, and the page was two subjects wearing
 * one title.
 */

//: WHO's normal range. Drawn as a band rather than a line because it is a
//: range, and a single "25" line silently implies everything below it is
//: equally fine down to zero.
const BMI_NORMAL = { from: 18.5, to: 25 };

export default async function BodyPage({
  searchParams,
}: {
  searchParams: Promise<{ days?: string }>;
}) {
  const { days: raw } = await searchParams;
  const days = Number(raw) || 730;

  const body = await serverGet<HealthBody>(`/health/body?days=${days}`);
  const heightM = body.height_cm ? body.height_cm / 100 : null;

  // Oldest-first, which is what a chart plots. The API returns newest-first
  // because the table below reads better that way.
  const weights = body.weights.slice().reverse();
  const measurements = body.measurements.slice().reverse();

  const weightPoints = weights.map((row) => ({
    date: row.local_date,
    value: row.weight_kg,
  }));
  const bmiPoints = heightM
    ? weightPoints.map((point) => ({
        date: point.date,
        value: point.value / (heightM * heightM),
      }))
    : [];
  const waistPoints = measurements
    .filter((row) => row.waist_cm !== null && row.waist_cm !== undefined)
    .map((row) => ({ date: row.local_date, value: row.waist_cm as number }));

  const latestWeight = body.weights[0];
  const latestWaist = body.measurements.find(
    (row) => row.waist_cm !== null && row.waist_cm !== undefined,
  );
  const latestBmi =
    latestWeight && heightM ? latestWeight.weight_kg / (heightM * heightM) : null;
  const ratio =
    latestWaist?.waist_cm && heightM ? latestWaist.waist_cm / 100 / heightM : null;

  // The stat row's colours come from the same thresholds the table uses, read
  // back off the freshest row rather than recomputed here — two implementations
  // of one band is how a green tile ends up above an amber cell.
  const newest = body.rows[0];
  const bandOf = (key: string) =>
    newest?.cells.find((cell) => cell.key === key)?.band ?? null;
  const tone = (band: number | null) =>
    band === null ? "" : band >= 4 ? "text-good" : band >= 3 ? "text-warning" : "text-critical";

  return (
    <>
      <PageHeader
        title="Body"
        subtitle={`Weight, BMI, waist and the waist-to-height ratio over ${days} days.`}
      >
        <RangeTabs basePath="/body" current={days} options={LONG_RANGES} />
      </PageHeader>

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat
          label="Latest weight"
          value={latestWeight ? `${num(latestWeight.weight_kg)} kg` : null}
          sub={
            latestWeight
              ? body.target_weight_kg
                ? `${shortDate(latestWeight.local_date)} · target ${num(body.target_weight_kg)} kg`
                : shortDate(latestWeight.local_date)
              : undefined
          }
          tone={tone(bandOf("weight_kg"))}
        />
        <Stat
          label="BMI"
          value={latestBmi ? num(latestBmi) : null}
          sub={
            heightM
              ? `normal ${BMI_NORMAL.from}–${BMI_NORMAL.to} · height ${num(body.height_cm)} cm`
              : "set a height below to derive this"
          }
          tone={tone(bandOf("bmi"))}
        />
        <Stat
          label="Waist"
          value={latestWaist?.waist_cm ? `${num(latestWaist.waist_cm)} cm` : null}
          sub={latestWaist ? shortDate(latestWaist.local_date) : undefined}
          tone={tone(bandOf("waist_cm"))}
        />
        <Stat
          label="Waist-to-height"
          value={ratio ? num(ratio, 2) : null}
          sub={
            heightM
              ? "healthy under 0.5 — waist under half your height"
              : "set a height below to derive this"
          }
          tone={tone(bandOf("waist_height_ratio"))}
        />
      </div>

      <div className="space-y-4">
        <Card
          title="Weight and BMI"
          subtitle={
            heightM
              ? "One measurement on two rulers — at a fixed height BMI is weight times a constant. The BMI axis is widened to fit the WHO normal range, which is why its line reads gentler; the band is what the second axis is for."
              : "Set a height below and this chart gains a BMI axis and the healthy band that goes with it."
          }
        >
          <LineChart
            series={[
              { label: "Weight", points: weightPoints, unit: "kg" },
              ...(bmiPoints.length
                ? [
                    {
                      label: "BMI",
                      points: bmiPoints,
                      unit: "kg/m²",
                      axis: "right" as const,
                    },
                  ]
                : []),
            ]}
            height={260}
            unit="kg"
            rightAxisLabel="BMI"
            {...(heightM
              ? {
                  normalBand: {
                    from: BMI_NORMAL.from,
                    to: BMI_NORMAL.to,
                    label: `BMI ${BMI_NORMAL.from}–${BMI_NORMAL.to}`,
                    axis: "right" as const,
                  },
                }
              : {})}
            {...(body.target_weight_kg
              ? {
                  reference: {
                    value: body.target_weight_kg,
                    label: `${num(body.target_weight_kg)} kg`,
                  },
                }
              : {})}
          />
        </Card>

        {waistPoints.length > 0 && (
          <Card
            title="Waist"
            subtitle="Its own chart, not a third line above: a ratio of 0.47 plotted against 82 kg is a flat line pinned to the axis."
          >
            <LineChart series={[{ label: "Waist", points: waistPoints }]} height={180} unit="cm" />
          </Card>
        )}

        <Card
          title="Readings"
          subtitle="One row per day something was recorded. Nothing is carried forward — a weight repeated down the column would colour days nobody stood on the scales."
        >
          <BodyTable columns={body.columns} rows={body.rows} />
        </Card>

        <Card
          title="Scale"
          subtitle="Five steps, worst to best. The number in each cell is the measurement itself, never the score. Hover a column heading for the evidence behind its colour."
        >
          <BandLegend />
        </Card>

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <Card title="Record a weight">
            <RecordWeight />
          </Card>
          <Card title="Record a measurement">
            <RecordMeasurement />
          </Card>
        </div>

        <Card
          title="Height and target"
          subtitle="Two numbers the rest of the page is derived against."
        >
          <RecordProfile
            initial={{
              height_cm: body.height_cm ?? null,
              target_weight_kg: body.target_weight_kg ?? null,
            }}
          />
        </Card>

        {body.rows.length === 0 && body.measurements.length === 0 && (
          <Card>
            <Empty>
              Nothing recorded yet. Add a weight above, or let the phone app sync what it has.
            </Empty>
          </Card>
        )}
      </div>
    </>
  );
}
