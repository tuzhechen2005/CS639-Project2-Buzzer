/** URL of a stored image (T8). Readable without login; the id is the capability.
 * The editor passes the image's sha256 as `version`, so a replaced image (same id,
 * new bytes) is fetched again instead of served from the 60 s browser cache. */
export function imageUrl(imageId: string, version?: string): string {
  return version ? `/api/images/${imageId}?v=${version}` : `/api/images/${imageId}`;
}
