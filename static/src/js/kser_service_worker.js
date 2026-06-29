// @odoo-module ignore

// ============================================================
// KSER Service Worker Extension
// Appended to Odoo's core service worker via controller override.
// Provides offline-first background sync and intelligent caching.
// ============================================================

const KSER_DB_NAME = "KSER_Offline_DB";
const KSER_DB_VERSION = 1;
const KSER_STORE_NAME = "Pending_Beneficiaries";
const KSER_SYNC_TAG = "kser-sync";
const ODOO_ASSETS_CACHE = "kser-assets-cache-v1";

// --- IndexedDB Helpers ---

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

// --- Fetch Event Listener (Caching & RPC Interception) ---

self.addEventListener("fetch", (event) => {
    const url = new URL(event.request.url);

    // 1. معالجة طلبات الملفات الثابتة (JS, CSS, Images, Views) - Cache as you fetch
    if (event.request.method === "GET" && (url.pathname.startsWith('/web/assets') || url.pathname.startsWith('/web/static') || url.pathname.startsWith('/web/image'))) {
        event.respondWith(
            caches.match(event.request).then((cachedResponse) => {
                if (cachedResponse) {
                    return cachedResponse; // إرجاع من الكاش إذا وجد
                }
                return fetch(event.request).then((networkResponse) => {
                    // إذا كان الطلب ناجحاً، احفظه في الكاش للاستخدام وقت انقطاع النت
                    if (networkResponse && networkResponse.status === 200 && networkResponse.type === 'basic') {
                        const responseToCache = networkResponse.clone();
                        caches.open(ODOO_ASSETS_CACHE).then((cache) => {
                            cache.put(event.request, responseToCache);
                        });
                    }
                    return networkResponse;
                }).catch(() => {
                    // فشل الاتصال ولم نجد الملف في الكاش
                    return new Response("Asset offline", { status: 503 });
                });
            })
        );
        return;
    }

    // 2. معالجة طلبات Odoo RPC (POST)
    const isRpc = event.request.method === "POST" && (
        url.pathname.startsWith("/web/dataset/call_kw/") ||
        url.pathname.startsWith("/web/dataset/search_read") ||
        url.pathname.startsWith("/web/action/")
    );

    if (isRpc) {
        event.respondWith(
            (async () => {
                try {
                    const response = await fetch(event.request.clone());
                    return response;
                } catch (networkError) {
                    // === وضع الأوفلاين (Offline Mode) ===
                    const clonedRequest = event.request.clone();
                    const bodyText = await clonedRequest.text();

                    let parsedBody = {};
                    let reqId = null;
                    let rpcMethod = "";
                    let modelName = "";

                    try {
                        parsedBody = JSON.parse(bodyText);
                        reqId = parsedBody.id || null;
                        rpcMethod = parsedBody.params ? parsedBody.params.method : "";
                        modelName = parsedBody.params ? parsedBody.params.model : "";
                    } catch (e) {}

                    let mockResult = true;

                    const isSaveAction = rpcMethod === "create" || rpcMethod === "write" || rpcMethod === "web_save";

                    // إذا كان الطلب هو حفظ مستفيد جديد
                    if (isSaveAction && modelName === "kser.beneficiary") {
                        const headersObj = {};
                        for (const [key, value] of clonedRequest.headers.entries()) {
                            headersObj[key] = value;
                        }

                        await ksSavePendingRequest(clonedRequest.url, headersObj, bodyText);

                        if (self.registration && self.registration.sync) {
                            await self.registration.sync.register(KSER_SYNC_TAG);
                        }

                        mockResult = [{ id: Math.floor(Math.random() * 100000) }];
                    }
                    // إذا كان طلب واجهة عادي (بحث، تغيير حقل) نعطيه استجابة وهمية لمنع الانهيار
                    else {
                        if (rpcMethod === "onchange") {
                            mockResult = { value: {} };
                        } else if (rpcMethod === "web_search_read" || rpcMethod === "search_read" || url.pathname.includes("search_read")) {
                            mockResult = { records: [], length: 0 };
                        } else if (rpcMethod === "default_get") {
                            mockResult = {};
                        } else if (rpcMethod === "load_views") {
                            // إذا حاول تحميل شاشة لم تُخزن مسبقاً
                            mockResult = { fields_views: {}, fields: {} };
                        }
                    }

                    const mockResponse = {
                        jsonrpc: "2.0",
                        id: reqId,
                        result: mockResult,
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

// --- Sync Event Listener (Replay offline requests) ---

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
                            const respJson = await response.json();
                            if (!respJson.error) {
                                await ksDeleteRequest(record.id);
                            }
                        }
                    } catch (syncError) {
                        // لا يزال غير متصل، اتركها للمحاولة القادمة
                    }
                }
            })()
        );
    }
});