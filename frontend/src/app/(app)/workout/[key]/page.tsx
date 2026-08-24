import { notFound } from "next/navigation";

import { ApiError, serverGet } from "@/lib/api/server";
import type {
  FitnessPartner,
  FitnessPlaylistDetail,
  FitnessSession,
  FitnessStats,
} from "@/lib/api/types";

import { WorkoutPlayer } from "./WorkoutPlayer";

export const dynamic = "force-dynamic";

export default async function WorkoutPlaylistPage({
  params,
}: {
  params: Promise<{ key: string }>;
}) {
  const { key } = await params;

  let playlist: FitnessPlaylistDetail;
  try {
    playlist = await serverGet<FitnessPlaylistDetail>(
      `/fitness/playlists/${key}`,
    );
  } catch (error) {
    // An unknown playlist key is a 404 from the API and a 404 here.
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  const [stats, recent, partners] = await Promise.all([
    serverGet<FitnessStats>("/fitness/stats"),
    serverGet<FitnessSession[]>("/fitness/recent"),
    serverGet<FitnessPartner[]>("/fitness/partners"),
  ]);

  return (
    <WorkoutPlayer
      playlist={playlist}
      initialStats={stats}
      initialRecent={recent}
      partners={partners}
    />
  );
}
