// @odoo-module ignore

// --- Service Worker Activation Control ---
self.addEventListener("install", (event) => {
    self.skipWaiting();
});

self.addEventListener("activate", (event) => {
    event.waitUntil(self.clients.claim());
});

// ============================================================
// KSER Service Worker Extension
// Appended to Odoo's core service worker via controller override.
// Provides offline-first background sync and intelligent caching.
// ============================================================

// --- ثوابت قاعدة البيانات ---
/** @type {string} */
const KSER_CACHE_NAME = "kser-v19-offline";
const KSER_DB_NAME = "KSER_Offline_DB";

/** @type {number} */
const KSER_DB_VERSION = 3;

/** @type {string} */
const KSER_STORE_NAME = "Pending_Beneficiaries";

/** @type {string} - مخزن الطلبات الميتة (فشلت بشكل دائم) */
const KSER_DEAD_LETTER_STORE = "Dead_Letter_Queue";

/** @type {string} */
const KSER_SYNC_TAG = "kser-sync";

/** @type {string} */
const ODOO_ASSETS_CACHE = "kser-assets-cache-v1";

/** @type {number} - الحد الأقصى لمحاولات إعادة الإرسال */
const KSER_MAX_RETRIES = 5;

// ============================================================
// تعريف واجهة سجل الطلب المعلّق (PendingRequest Interface)
// ============================================================
/**
 * @typedef {Object} PendingRequest
 * @property {number}                id        - المعرف الفريد (autoIncrement)
 * @property {string}                url       - عنوان URL للطلب
 * @property {Record<string,string>} headers   - ترويسات HTTP
 * @property {string}                payload   - جسم الطلب (JSON string)
 * @property {number}                timestamp - طابع زمني (Date.now)
 * @property {number}                [retryCount] - عدد محاولات إعادة الإرسال
 */

// --- IndexedDB Helpers ---

/**
 * فتح قاعدة بيانات IndexedDB
 * @returns {Promise<IDBDatabase>}
 */
function ksOpenDatabase() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(KSER_DB_NAME, KSER_DB_VERSION);

        request.onupgradeneeded = (event) => {
            /** @type {IDBDatabase} */
            const db = /** @type {IDBOpenDBRequest} */ (event.target).result;
            if (!db.objectStoreNames.contains(KSER_STORE_NAME)) {
                db.createObjectStore(KSER_STORE_NAME, {
                    keyPath: "id",
                    autoIncrement: true,
                });
            }
            // إنشاء مخزن الطلبات الميتة إذا لم يكن موجوداً
            if (!db.objectStoreNames.contains(KSER_DEAD_LETTER_STORE)) {
                db.createObjectStore(KSER_DEAD_LETTER_STORE, {
                    keyPath: "id",
                    autoIncrement: true,
                });
            }
            // إنشاء مخزن كاش الـ RPC إذا لم يكن موجوداً
            if (!db.objectStoreNames.contains("RPC_Cache")) {
                db.createObjectStore("RPC_Cache", {
                    keyPath: "key",
                });
            }
        };

        request.onsuccess = (event) => resolve(/** @type {IDBOpenDBRequest} */ (event.target).result);
        request.onerror = (event) => reject(/** @type {IDBOpenDBRequest} */ (event.target).error);
    });
}

/**
 * حفظ طلب معلّق في IndexedDB
 * @param {string}                url     - عنوان URL
 * @param {Record<string,string>} headers - ترويسات HTTP
 * @param {string}                payload - جسم الطلب
 * @returns {Promise<IDBValidKey>}
 */
async function ksSavePendingRequest(url, headers, payload, mockId = null) {
    const db = await ksOpenDatabase();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(KSER_STORE_NAME, "readwrite");
        const store = tx.objectStore(KSER_STORE_NAME);

        /** @type {PendingRequest} */
        const record = {
            url: url,
            headers: headers,
            payload: payload,
            timestamp: Date.now(),
            retryCount: 0,
            mockId: mockId,
        };

        const request = store.add(record);
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

/**
 * جلب جميع الطلبات المعلّقة
 * @returns {Promise<PendingRequest[]>}
 */
async function ksGetPendingRequests() {
    const db = await ksOpenDatabase();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(KSER_STORE_NAME, "readonly");
        const store = tx.objectStore(KSER_STORE_NAME);

        const request = store.getAll();
        request.onsuccess = () => resolve(/** @type {PendingRequest[]} */ (request.result));
        request.onerror = () => reject(request.error);
    });
}

/**
 * حذف سجل من مخزن الطلبات المعلّقة
 * @param {number} id - معرف السجل
 * @returns {Promise<void>}
 */
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

/**
 * تحديث عدد محاولات إعادة الإرسال لسجل معيّن
 * @param {PendingRequest} record - السجل المراد تحديثه
 * @returns {Promise<void>}
 */
async function ksUpdateRetryCount(record) {
    const db = await ksOpenDatabase();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(KSER_STORE_NAME, "readwrite");
        const store = tx.objectStore(KSER_STORE_NAME);

        record.retryCount = (record.retryCount || 0) + 1;
        const request = store.put(record);
        request.onsuccess = () => resolve();
        request.onerror = () => reject(request.error);
    });
}

/**
 * نقل سجل فاشل إلى قائمة الطلبات الميتة (Dead Letter Queue)
 * @param {PendingRequest} record       - السجل الأصلي
 * @param {string}         errorMessage - رسالة الخطأ
 * @returns {Promise<void>}
 */
async function ksMoveToDeadLetterQueue(record, errorMessage) {
    const db = await ksOpenDatabase();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(
            [KSER_STORE_NAME, KSER_DEAD_LETTER_STORE],
            "readwrite"
        );

        const pendingStore = tx.objectStore(KSER_STORE_NAME);
        const deadLetterStore = tx.objectStore(KSER_DEAD_LETTER_STORE);

        // حذف من مخزن الطلبات المعلّقة
        pendingStore.delete(record.id);

        // إضافة إلى مخزن الطلبات الميتة
        deadLetterStore.add({
            url: record.url,
            headers: record.headers,
            payload: record.payload,
            timestamp: record.timestamp,
            failedAt: Date.now(),
            errorMessage: errorMessage,
            retryCount: record.retryCount || 0,
        });

        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
}

/**
 * حفظ استجابة RPC في الكاش المحلي لاستخدامها وقت انقطاع الإنترنت
 * @param {string} key - مفتاح الكاش الفريد
 * @param {*} response - نتيجة الاستجابة
 * @returns {Promise<void>}
 */
async function ksCacheRpcResponse(key, response) {
    const db = await ksOpenDatabase();
    return new Promise((resolve, reject) => {
        const tx = db.transaction("RPC_Cache", "readwrite");
        const store = tx.objectStore("RPC_Cache");
        const record = {
            key: key,
            response: response,
            timestamp: Date.now()
        };
        const request = store.put(record);
        request.onsuccess = () => resolve();
        request.onerror = () => reject(request.error);
    });
}

/**
 * جلب استجابة RPC مخزنة مسبقاً من الكاش
 * @param {string} key - مفتاح الكاش
 * @returns {Promise<*>}
 */
async function ksGetCachedRpcResponse(key) {
    const db = await ksOpenDatabase();
    return new Promise((resolve, reject) => {
        const tx = db.transaction("RPC_Cache", "readonly");
        const store = tx.objectStore("RPC_Cache");
        const request = store.get(key);
        request.onsuccess = () => {
            if (request.result) {
                resolve(request.result.response);
            } else {
                resolve(null);
            }
        };
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
        // مهم: أزرار الفورم من نوع type="object" (مثل زر "تأكيد وحفظ" بالويزارد)
        // تُرسل عبر مسار مختلف تماماً (call_button) وليس call_kw
        // بدون هذا السطر، الطلب يفشل مباشرة عند قطع الاتصال ولا يُحفظ أبداً بـ IndexedDB
        url.pathname.startsWith("/web/dataset/call_button/") ||
        url.pathname.startsWith("/web/dataset/search_read") ||
        url.pathname.startsWith("/web/action/")
    );

    if (isRpc) {
        event.respondWith(
            (async () => {
                /** @type {Object} */
                let parsedBody = {};
                /** @type {number|null} */
                let reqId = null;
                /** @type {string} */
                let rpcMethod = "";
                /** @type {string} */
                let modelName = "";
                /** @type {string} */
                let cacheKey = "";

                try {
                    const clonedReqForCheck = event.request.clone();
                    const bodyText = await clonedReqForCheck.text();
                    parsedBody = JSON.parse(bodyText);
                    reqId = parsedBody.id || null;
                    rpcMethod = (parsedBody.params && typeof parsedBody.params.method === 'string') ? parsedBody.params.method : "";
                    modelName = (parsedBody.params && typeof parsedBody.params.model === 'string') ? parsedBody.params.model : "";

                    // تحديد الدوال التي نقوم بعمل كاش لاستجاباتها (قراءة فقط ولا تغير حالة النظام)
                    // ملاحظة: أودو 17/18 يستخدم أسماء الدوال الجديدة (web_read, web_search_read)
                    // بدلاً من القديمة (read, search_read) في أغلب طلبات الويب كلاينت
                    // لذا لازم ندرج الاثنين معاً وإلا تظل RPC_Cache فارغة رغم نجاح الاتصال
                    const cacheableMethods = [
                        "get_views", "load_views", "fields_get",
                        "search_read", "web_search_read",
                        "read", "web_read",
                        "default_get",
                    ];
                    if (rpcMethod && cacheableMethods.includes(rpcMethod)) {
                        // إنشاء مفتاح فريد يعتمد على الموديل والدالة والمعاملات (بدون معرف الطلب المتغير)
                        cacheKey = `${modelName}:${rpcMethod}:${JSON.stringify(parsedBody.params)}`;
                    } else if (url.pathname.startsWith("/web/action/")) {
                        // تخزين إجراءات الواجهة (Actions) لتفتح بسلاسة دون اتصال
                        cacheKey = `action:${url.pathname}:${JSON.stringify(parsedBody)}`;
                    }
                } catch (e) {
                    console.warn("[KSER SW] فشل فحص الطلب لإنشاء مفتاح الكاش", e);
                }

                try {
                    const response = await fetch(event.request.clone());

                    // إذا نجح الاتصال وكانت الدالة قابلة للتخزين، نقوم بحفظها
                    if (response.ok && cacheKey) {
                        try {
                            const clonedRes = response.clone();
                            const resJson = await clonedRes.json();
                            if (resJson && !resJson.error) {
                                await ksCacheRpcResponse(cacheKey, resJson.result);
                                console.log(`[KSER SW Cache] ✅ تم حفظ استجابة RPC في الكاش: ${cacheKey}`);
                            }
                        } catch (cacheErr) {
                            console.warn("[KSER SW Cache] فشل تخزين استجابة RPC:", cacheErr);
                        }
                    }

                    return response;
                } catch (networkError) {
                  try {
                    // === وضع الأوفلاين (Offline Mode) ===
                    console.log(`[KSER SW] 🔌 تم كشف وضع الأوفلاين لـ RPC: ${rpcMethod} على موديل ${modelName}`);

                    const isSaveAction = typeof rpcMethod === 'string' && (
                        rpcMethod === "create" ||
                        rpcMethod === "write" ||
                        rpcMethod === "web_save" ||
                        rpcMethod === "name_create" ||
                        rpcMethod.startsWith("action_")
                    );

                    /** @type {string[]} */
                    const targetModels = [
                        "kser.beneficiary",
                        "res.partner",
                        "kser.clinic.visit",
                        "kser.prescription",
                        "kser.prescription.line",
                        "kser.child.followup",
                        "kser.national.id.wizard",
                        "kser.bank.receipt.wizard"
                    ];

                    // 1. إذا كان الطلب هو حفظ مستفيد جديد أو معالج ويزارد أو شريك (res.partner)
                    if (isSaveAction && targetModels.includes(modelName)) {
                        let mockResult = null;
                        let mockId = null;

                        if (rpcMethod === "write") {
                            mockResult = true;
                        } else if (rpcMethod === "name_create") {
                            mockId = Math.floor(Math.random() * 100000);
                            const nameArg = (parsedBody.params && parsedBody.params.args && parsedBody.params.args[0]) || "New Contact";
                            mockResult = [mockId, nameArg];
                        } else if (rpcMethod === "action_manual_entry" || rpcMethod === "action_extract_data") {
                            // إرجاع أكشن لإعادة فتح الويزارد في وضع التعديل (Edit Mode) لتظهر الأزرار
                            const wizardId = (parsedBody.params && parsedBody.params.args && parsedBody.params.args[0]) ||
                                             (parsedBody.params && parsedBody.params.context && parsedBody.params.context.active_id) ||
                                             Math.floor(Math.random() * 100000);
                            mockResult = {
                                type: "ir.actions.act_window",
                                res_model: modelName,
                                res_id: wizardId,
                                view_mode: "form",
                                target: "new",
                            };
                        } else if (rpcMethod === "action_confirm_and_save") {
                            mockResult = { type: "ir.actions.act_window_close" };
                        } else if (rpcMethod.startsWith("action_")) {
                            mockResult = true;
                        } else {
                            mockId = Math.floor(Math.random() * 100000);
                            mockResult = [{ id: mockId }];
                        }

                        const clonedReqForSave = event.request.clone();
                        const bodyText = await clonedReqForSave.text();
                        /** @type {Record<string,string>} */
                        const headersObj = {};
                        for (const [key, value] of event.request.headers.entries()) {
                            headersObj[key] = value;
                        }

                        await ksSavePendingRequest(event.request.url, headersObj, bodyText, mockId);

                        if (self.registration && self.registration.sync) {
                            await self.registration.sync.register(KSER_SYNC_TAG);
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

                    // 2. إذا كانت الاستجابة مخزنة مسبقاً في كاش الـ RPC
                    if (cacheKey) {
                        const cachedResult = await ksGetCachedRpcResponse(cacheKey);
                        if (cachedResult !== null) {
                            console.log(`[KSER SW Cache] 🎯 تم الاسترجاع من الكاش المحلي لـ: ${cacheKey}`);
                            const mockResponse = {
                                jsonrpc: "2.0",
                                id: reqId,
                                result: cachedResult,
                            };
                            return new Response(JSON.stringify(mockResponse), {
                                status: 200,
                                headers: { "Content-Type": "application/json" },
                            });
                        }
                    }

                    // 3. استجابات افتراضية وقائية في حال لم يسبق تخزينها لتجنب انهيار الواجهة
                    // === القيم الافتراضية الموحّدة لكل موديل (تُستخدم في default_get و onchange و read) ===
                    // هذه القائمة هي "مصدر الحقيقة الوحيد" لحقل state وبقية الحقول المهمة
                    // لأن أودو الحديث (17/18) يطلب القيم الافتراضية غالباً عبر "onchange"
                    // وليس عبر "default_get" كما كان بالإصدارات القديمة
                    /** @type {Record<string, Record<string, *>>} */
                    const knownModelDefaults = {
                        "kser.national.id.wizard": {
                            state: "review",
                            target_type: "beneficiary",
                            is_manual_entry: true,
                            is_child: false,
                            is_disabled: false,
                        },
                        "kser.bank.receipt.wizard": {
                            state: "review",
                            is_manual_entry: true,
                        },
                        "kser.inventory.wizard": {
                            state: "draft",
                        },
                    };
                    const fallbackFields = knownModelDefaults[modelName] || {};

                    let mockResult = null;
                    if (rpcMethod === "onchange") {
                        // مهم: onchange يتوقع شكل الاستجابة {value: {...}}
                        // بدون تعبئة "value" بالحقول الافتراضية، تضل الحالة (state) فاضية
                        // وتختفي كل الأزرار المشروطة بها (مثل زر "تأكيد وحفظ")
                        mockResult = { value: { ...fallbackFields } };
                    } else if (rpcMethod === "web_search_read" || rpcMethod === "search_read" || url.pathname.includes("search_read")) {
                        mockResult = { records: [], length: 0 };
                    } else if (rpcMethod === "default_get" || rpcMethod === "read" || rpcMethod === "web_read") {
                        if (rpcMethod === "default_get") {
                            mockResult = fallbackFields;
                        } else {
                            // read / web_read: يجب إرجاع مصفوفة سجلات تحتوي على id
                            const argIds =
                                (parsedBody.params && parsedBody.params.args && parsedBody.params.args[0]) ||
                                (parsedBody.params && parsedBody.params.ids) ||
                                [];
                            const idsList = Array.isArray(argIds) ? argIds : [argIds];

                            mockResult = idsList.map((recId) => ({
                                id: recId,
                                ...fallbackFields,
                            }));
                        }
                    } else if (rpcMethod === "load_views" || rpcMethod === "get_views") {
                        mockResult = { models: {}, views: {} };
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
                  } catch (fatalErr) {
                    // شبكة الأمان الأخيرة: أي خطأ غير متوقع بمنطق المحاكاة أعلاه
                    // يجب ألا يتسبب بفشل الطلب بالكامل (net::ERR_FAILED) أمام المستخدم،
                    // بل نرجّع استجابة JSON-RPC فارغة وآمنة حتى لا تنهار الواجهة
                    console.error("[KSER SW] ⚠️ خطأ غير متوقع أثناء توليد استجابة أوفلاين وهمية:", fatalErr);
                    return new Response(JSON.stringify({
                        jsonrpc: "2.0",
                        id: reqId,
                        result: null,
                    }), {
                        status: 200,
                        headers: { "Content-Type": "application/json" },
                    });
                  }
                }
            })()
        );
    }
});

/**
 * استبدال المعرفات الوهمية (Mock IDs) بالمعرفات الحقيقية (Real IDs) بشكل عودي داخل كائن الحمولة (Payload)
 * @param {any} obj - الكائن المراد معالجته
 * @param {Record<number, number>} idMap - جدول مطابقة المعرفات
 * @returns {any} الكائن بعد الاستبدال
 */
function ksReplaceMockIds(obj, idMap) {
    // مهم: يجب التحقق من idMap أولاً حتى للقيم الأولية (أرقام/نصوص)
    // بغض النظر عن كونها عنصر مصفوفة مباشر [76431] أو قيمة خاصية {id: 76431}
    // الخطأ السابق كان يتجاهل الحالة الأولى تماماً، وهي بالضبط الشكل الذي
    // يرسل به أودو معرفات السجلات لاستدعاءات الأزرار: args: [[76431], {...}]
    if (typeof obj === 'number' && idMap[obj] !== undefined) {
        return idMap[obj];
    }
    if (typeof obj === 'string' && idMap[obj] !== undefined) {
        return idMap[obj];
    }
    if (obj === null || typeof obj !== 'object') {
        return obj;
    }
    if (Array.isArray(obj)) {
        return obj.map(item => ksReplaceMockIds(item, idMap));
    }
    const newObj = {};
    for (const [key, value] of Object.entries(obj)) {
        newObj[key] = ksReplaceMockIds(value, idMap);
    }
    return newObj;
}

// --- Sync Event Listener (Replay offline requests) ---

self.addEventListener("sync", (event) => {
    if (event.tag === KSER_SYNC_TAG) {
        event.waitUntil(
            (async () => {
                /** @type {PendingRequest[]} */
                const pendingRequests = await ksGetPendingRequests();

                if (pendingRequests.length === 0) return;
                console.log(`[KSER SW Sync] بدء مزامنة ${pendingRequests.length} طلب(ات) معلّقة...`);

                const idMap = {};

                for (const record of pendingRequests) {
                    try {
                        let payload = record.payload;
                        try {
                            const parsedPayload = JSON.parse(record.payload);
                            const updatedPayload = ksReplaceMockIds(parsedPayload, idMap);
                            payload = JSON.stringify(updatedPayload);
                        } catch (e) {
                            console.warn("[KSER SW Sync] فشل تحليل أو معالجة حمولة الطلب:", e);
                        }

                        const response = await fetch(record.url, {
                            method: "POST",
                            headers: record.headers,
                            body: payload,
                        });

                        if (response.ok) {
                            // أودو يعيد HTTP 200 دائمًا حتى لو فشل الطلب تطبيقيًا
                            /** @type {string} */
                            const responseText = await response.text();

                            /** @type {Object} */
                            let respJson;
                            try {
                                respJson = JSON.parse(responseText);
                            } catch (_parseErr) {
                                console.error(
                                    `[KSER SW Sync] ❌ استجابة غير JSON للسجل id=${record.id} — نقل إلى Dead Letter Queue`
                                );
                                await ksMoveToDeadLetterQueue(record, `Non-JSON response: ${responseText.substring(0, 200)}`);
                                continue;
                            }

                            if (!respJson.error) {
                                // استخراج المعرف الحقيقي من النتيجة
                                let realId = null;
                                if (respJson.result) {
                                    if (Array.isArray(respJson.result)) {
                                        if (typeof respJson.result[0] === 'number') {
                                            realId = respJson.result[0];
                                        } else if (respJson.result[0] && typeof respJson.result[0].id === 'number') {
                                            realId = respJson.result[0].id;
                                        }
                                    } else if (respJson.result.id) {
                                        realId = respJson.result.id;
                                    } else if (typeof respJson.result === 'number') {
                                        realId = respJson.result;
                                    }
                                }

                                if (record.mockId && realId) {
                                    idMap[record.mockId] = realId;
                                    console.log(`[KSER SW Sync] 🔗 تم مطابقة المعرف الوهمي ${record.mockId} بالمعرف الحقيقي ${realId}`);
                                }

                                await ksDeleteRequest(record.id);
                                console.log(`[KSER SW Sync] ✅ تمت مزامنة السجل id=${record.id} بنجاح`);
                            } else {
                                /** @type {string} */
                                const errorMsg =
                                    respJson.error.data?.message ||
                                    respJson.error.message ||
                                    JSON.stringify(respJson.error);

                                const currentRetries = (record.retryCount || 0) + 1;

                                if (currentRetries >= KSER_MAX_RETRIES) {
                                    // تجاوز الحد الأقصى — نقل إلى Dead Letter Queue
                                    console.error(
                                        `[KSER SW Sync] ☠️ فشل دائم للسجل id=${record.id} بعد ${currentRetries} محاولة — نقل إلى Dead Letter Queue:`,
                                        errorMsg
                                    );
                                    await ksMoveToDeadLetterQueue(record, errorMsg);
                                } else {
                                    console.warn(
                                        `[KSER SW Sync] ⚠️ فشل تطبيقي من أودو للسجل id=${record.id} (محاولة ${currentRetries}/${KSER_MAX_RETRIES}):`,
                                        errorMsg
                                    );
                                    await ksUpdateRetryCount(record);
                                }
                            }
                        } else {
                            console.warn(
                                `[KSER SW Sync] استجابة HTTP غير ناجحة للسجل id=${record.id}: ${response.status}`
                            );
                            await ksUpdateRetryCount(record);
                        }
                    } catch (/** @type {Error} */ syncError) {
                        console.warn(`[KSER SW Sync] 🔌 فشل الاتصال للسجل id=${record.id}:`, syncError.message);
                        // الشبكة ميتة — نوقف الحلقة فوراً
                        break;
                    }
                }
            })()
        );
    }
});