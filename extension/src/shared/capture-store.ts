/**
 * Local capture history (IndexedDB). A capture's thumbnail never leaves the
 * browser: the server keeps text only, and this store holds the picture next
 * to a copy of the text so "Recent" also works signed out. The service worker
 * writes a record after each successful capture; the side panel reads them.
 * IndexedDB is shared between both, and (unlike runtime messages) stores Blobs.
 */

const DB_NAME = "visionlearn";
const STORE = "captures";
const DB_VERSION = 1;

export const LOCAL_RETENTION_DAYS = 30;

export interface CaptureRecord {
  slide_id: string;
  presentation_id: string;
  /** Lower-cased page URL without query/fragment; "" when the page had none. */
  lectureKey: string;
  title: string;
  url: string;
  thumbnail: Blob | null;
  summary: string;
  capturedAt: number;
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const store = request.result.createObjectStore(STORE, { keyPath: "slide_id" });
      store.createIndex("lectureKey", "lectureKey");
      store.createIndex("capturedAt", "capturedAt");
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function run<T>(mode: IDBTransactionMode, work: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await openDb();
  try {
    return await new Promise<T>((resolve, reject) => {
      const transaction = db.transaction(STORE, mode);
      const request = work(transaction.objectStore(STORE));
      transaction.oncomplete = () => resolve(request.result);
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  } finally {
    db.close();
  }
}

export function saveCapture(record: CaptureRecord): Promise<unknown> {
  return run("readwrite", (store) => store.put(record));
}

/** Newest first. */
export async function listCaptures(): Promise<CaptureRecord[]> {
  const all = await run<CaptureRecord[]>("readonly", (store) => store.getAll());
  return all.sort((a, b) => b.capturedAt - a.capturedAt);
}

export function deleteCapture(slideId: string): Promise<unknown> {
  return run("readwrite", (store) => store.delete(slideId));
}

export async function deleteLectureCaptures(presentationId: string): Promise<void> {
  const all = await listCaptures();
  await Promise.all(all.filter((c) => c.presentation_id === presentationId).map((c) => deleteCapture(c.slide_id)));
}

export function clearCaptures(): Promise<unknown> {
  return run("readwrite", (store) => store.clear());
}

/** The presentation this lecture's earlier captures went into, so a signed-out
 * capture of the same page joins the same group. */
export async function latestPresentationFor(lectureKey: string): Promise<string | null> {
  if (!lectureKey) return null;
  const matches = await run<CaptureRecord[]>("readonly", (store) => store.index("lectureKey").getAll(lectureKey));
  matches.sort((a, b) => b.capturedAt - a.capturedAt);
  return matches[0]?.presentation_id ?? null;
}

/** Drops records past the retention window (the server drops its copy too). */
export async function purgeOlderThan(days: number): Promise<void> {
  const cutoff = Date.now() - days * 86_400_000;
  const all = await listCaptures();
  await Promise.all(all.filter((c) => c.capturedAt < cutoff).map((c) => deleteCapture(c.slide_id)));
}
