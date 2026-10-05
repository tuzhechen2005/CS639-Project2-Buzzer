/** URL of a stored image (T8). Readable without login; the id is the capability. */
export function imageUrl(imageId: string): string {
  return `/api/images/${imageId}`;
}
