import { permanentRedirect } from "next/navigation";

/**
 * `/vitals` was "BP + Weight" until weight moved to `/body`.
 *
 * Kept as a permanent redirect rather than deleted: this is a self-hosted app
 * whose users bookmark the page they open every morning, and a 404 on a URL
 * that worked yesterday reads as data loss rather than as a rename.
 * `permanentRedirect` sends a 308, so a browser that has followed it once
 * stops asking.
 */
export default function VitalsPage() {
  permanentRedirect("/blood-pressure");
}
