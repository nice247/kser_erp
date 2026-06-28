// @odoo-module ignore

// ============================================================
// KSER Service Worker Extension
// Appended to Odoo's core service worker via controller override.
// Provides offline-first background sync for beneficiary creation.
// ============================================================

const KSER_DB_NAME = "KSER_Offline_DB";
const KSER_DB_VERSION = 1;
const KSER_STORE_NAME = "Pending_Beneficiaries";
const KSER_SYNC_TAG = "kser-sync";
const KSER_TARGET_PATH = "/web/dataset/call_kw/kser.beneficiary/create";

// --- Inline IndexedDB helpers (Service Workers cannot use importScripts for ES modules) ---

function ksOpenDatabase() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(KSER_DB_NAME, KSER_DB_VERSION);

        request.onupgradeneeded = (event) => {
            const db = event.target.result;
            if (!db.objectStoreNames.contains(KSER_STORE_NAME)) {
                db.createObjectStore(KSER_STORE_NAME, {
                    keyPath: "id",
                    autoIncrement: true,
                });
            }
        };

        request.onsuccess = (event) => resolve(event.target.result);
        request.onerror = (event) => reject(event.target.error);
    });
}

async function ksSavePendingRequest(url, headers, payload) {
    const db = await ksOpenDatabase();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(KSER_STORE_NAME, "readwrite");
        const store = tx.objectStore(KSER_STORE_NAME);

        const record = {
            url: url,
            headers: headers,
            payload: payload,
            timestamp: Date.now(),
        };

        const request = store.add(record);
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

async function ksGetPendingRequests() {
    const db = await ksOpenDatabase();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(KSER_STORE_NAME, "readonly");
        const store = tx.objectStore(KSER_STORE_NAME);

        const request = store.getAll();
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

async function ksDeleteRequest(id) {
    const db = await ksOpenDatabase();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(KSER_STORE_NAME, "readwrite");
        const store = tx.objectStore(KSER_STORE_NAME);

        const request = store.delete(id);
        request.onsuccess = () => resolve();
        request.onerror = () => reject(request.error);
    });
}

// --- Fetch Event Listener: Intercept beneficiary creation calls ---

self.addEventListener("fetch", (event) => {
    const url = new URL(event.request.url);
    const isTarget = event.request.method === "POST" && (
        url.pathname === "/web/dataset/call_kw/kser.beneficiary/create" ||
        url.pathname === "/web/dataset/call_kw/kser.beneficiary/web_save" ||
        url.pathname === "/web/dataset/call_kw/kser.beneficiary/write"
    );

    if (isTarget) {
        event.respondWith(
            (async () => {
                try {
                    const response = await fetch(event.request.clone());
                    return response;
                } catch (networkError) {
                    const clonedRequest = event.request.clone();
                    const body = await clonedRequest.text();

                    const headersObj = {};
                    for (const [key, value] of clonedRequest.headers.entries()) {
                        headersObj[key] = value;
                    }

                    await ksSavePendingRequest(
                        clonedRequest.url,
                        headersObj,
                        body
                    );

                    if (self.registration && self.registration.sync) {
                        await self.registration.sync.register(KSER_SYNC_TAG);
                    }

                    let reqId = null;
                    try {
                        const parsed = JSON.parse(body);
                        reqId = parsed.id;
                    } catch (e) {}

                    const mockResponse = {
                        jsonrpc: "2.0",
                        id: reqId,
                        result: true,
                    };

                    return new Response(JSON.stringify(mockResponse), {
                        status: 200,
                        headers: { "Content-Type": "application/json" },
                    });
                }
            })()
        );
    }
});

// --- Sync Event Listener: Replay pending requests when back online ---

self.addEventListener("sync", (event) => {
    if (event.tag === KSER_SYNC_TAG) {
        event.waitUntil(
            (async () => {
                const pendingRequests = await ksGetPendingRequests();

                for (const record of pendingRequests) {
                    try {
                        const response = await fetch(record.url, {
                            method: "POST",
                            headers: record.headers,
                            body: record.payload,
                        });

                        if (response.ok) {
                            await ksDeleteRequest(record.id);
                        }
                    } catch (syncError) {
                        // Network still unavailable; leave the record for the next sync attempt.
                    }
                }
            })()
        );
    }
});
