// @odoo-module ignore

// ============================================================
// KSER IndexedDB — وحدة المزامنة دون اتصال (Offline Sync Module)
// يعمل في السياق الرئيسي للمتصفح كآلية احتياطية (Fallback)
// عندما لا يدعم المتصفح Background Sync API
// ============================================================

// --- ثوابت قاعدة البيانات ---
/** @type {string} */
const KSER_DB_NAME = "KSER_Offline_DB";

/** @type {number} */
const KSER_DB_VERSION = 3;

/** @type {string} */
const KSER_STORE_NAME = "Pending_Beneficiaries";

/** @type {string} - مخزن الطلبات الميتة (فشلت بشكل دائم) */
const KSER_DEAD_LETTER_STORE = "Dead_Letter_Queue";

/** @type {number} - الحد الأقصى لمحاولات إعادة الإرسال قبل نقل السجل لقائمة الطلبات الميتة */
const KSER_MAX_RETRIES = 5;

// --- قفل المزامنة لمنع التنفيذ المتداخل ---
/** @type {boolean} */
let _isSyncing = false;

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

/**
 * @typedef {Object} DeadLetterRecord
 * @property {number}                id           - المعرف الفريد (autoIncrement)
 * @property {string}                url          - عنوان URL للطلب الأصلي
 * @property {Record<string,string>} headers      - ترويسات HTTP الأصلية
 * @property {string}                payload      - جسم الطلب الأصلي
 * @property {number}                timestamp    - طابع زمني أصلي
 * @property {number}                failedAt     - طابع زمني عند الفشل النهائي
 * @property {string}                errorMessage - رسالة الخطأ من أودو
 * @property {number}                retryCount   - عدد المحاولات التي أُجريت
 */

// ============================================================
// دوال قاعدة البيانات (IndexedDB Helpers)
// ============================================================

/**
 * فتح قاعدة بيانات IndexedDB مع إنشاء المخازن إذا لزم الأمر
 * @returns {Promise<IDBDatabase>}
 */
function openDatabase() {
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

        request.onsuccess = (event) => {
            resolve(/** @type {IDBOpenDBRequest} */ (event.target).result);
        };

        request.onerror = (event) => {
            reject(/** @type {IDBOpenDBRequest} */ (event.target).error);
        };
    });
}

/**
 * حفظ طلب معلّق في IndexedDB لإعادة إرساله لاحقاً
 * @param {string}                url     - عنوان URL لطلب RPC
 * @param {Record<string,string>} headers - ترويسات HTTP
 * @param {string}                payload - جسم الطلب كنص JSON
 * @returns {Promise<IDBValidKey>}
 */
async function savePendingRequest(url, headers, payload) {
    const db = await openDatabase();
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
        };

        const request = store.add(record);
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

/**
 * جلب جميع الطلبات المعلّقة من IndexedDB
 * @returns {Promise<PendingRequest[]>}
 */
async function getPendingRequests() {
    const db = await openDatabase();
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
async function deleteRequest(id) {
    const db = await openDatabase();
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
async function updateRetryCount(record) {
    const db = await openDatabase();
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
 * نقل سجل فاشل بشكل دائم إلى قائمة الطلبات الميتة (Dead Letter Queue)
 * هذا يمنع إعادة المحاولة اللانهائية للطلبات التي يرفضها أودو تطبيقياً
 * @param {PendingRequest} record       - السجل الأصلي
 * @param {string}         errorMessage - رسالة الخطأ من أودو
 * @returns {Promise<void>}
 */
async function moveToDeadLetterQueue(record, errorMessage) {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
        // استخدام معاملة واحدة تشمل الحذف والإضافة لضمان الذرية
        const tx = db.transaction(
            [KSER_STORE_NAME, KSER_DEAD_LETTER_STORE],
            "readwrite"
        );

        const pendingStore = tx.objectStore(KSER_STORE_NAME);
        const deadLetterStore = tx.objectStore(KSER_DEAD_LETTER_STORE);

        // حذف من مخزن الطلبات المعلّقة
        pendingStore.delete(record.id);

        // إضافة إلى مخزن الطلبات الميتة مع معلومات الخطأ
        /** @type {DeadLetterRecord} */
        const deadRecord = {
            url: record.url,
            headers: record.headers,
            payload: record.payload,
            timestamp: record.timestamp,
            failedAt: Date.now(),
            errorMessage: errorMessage,
            retryCount: record.retryCount || 0,
        };
        deadLetterStore.add(deadRecord);

        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
}

// ============================================================
// كاش استجابات أودو (RPC Caching) لدعم الواجهات دون اتصال
// ============================================================

/**
 * حفظ استجابة RPC للقراءة فقط (مثل get_views, search_read) في الكاش
 * @param {string} cacheKey - المفتاح المميز للطلب
 * @param {any} resultData  - النتيجة المراد تخزينها (resJson.result)
 * @returns {Promise<void>}
 */
async function ksCacheRpcResponse(cacheKey, resultData) {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
        const tx = db.transaction("RPC_Cache", "readwrite");
        const store = tx.objectStore("RPC_Cache");
        const request = store.put({ key: cacheKey, result: resultData, timestamp: Date.now() });
        request.onsuccess = () => resolve();
        request.onerror = () => reject(request.error);
    });
}

/**
 * استرجاع استجابة RPC من الكاش
 * @param {string} cacheKey - المفتاح المميز للطلب
 * @returns {Promise<any|null>} - البيانات المخزنة أو null
 */
async function ksGetCachedRpcResponse(cacheKey) {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
        const tx = db.transaction("RPC_Cache", "readonly");
        const store = tx.objectStore("RPC_Cache");
        const request = store.get(cacheKey);
        request.onsuccess = () => {
            if (request.result) {
                resolve(request.result.result);
            } else {
                resolve(null);
            }
        };
        request.onerror = () => reject(request.error);
    });
}

// ============================================================
// محرك المزامنة الرئيسي (Main Sync Engine)
// ============================================================

/**
 * إعادة إرسال الطلبات المعلّقة — آلية احتياطية (Fallback)
 * تعمل كبديل عندما لا يدعم المتصفح Background Sync API
 *
 * الحماية من التنفيذ المتداخل:
 * - يستخدم قفل `_isSyncing` لمنع التداخل عند استدعاء الدالة
 *   من `setInterval` و `online` event و `load` event في نفس الوقت
 *
 * معالجة أخطاء أودو:
 * - أودو يعيد HTTP 200 دائمًا حتى لو فشل الطلب تطبيقيًا
 * - الخطأ الحقيقي يكون داخل جسم JSON كـ {"error": {...}}
 * - إذا تجاوز عدد المحاولات الحد الأقصى، يُنقل السجل إلى Dead Letter Queue
 *
 * تحسين الشبكة:
 * - عند فشل الاتصال بالشبكة، يتوقف الحلقة فوراً (break)
 *   لعدم محاولة إرسال طلبات أخرى على اتصال ميت
 *
 * @returns {Promise<void>}
 */
/**
 * استبدال المعرفات الوهمية (Mock IDs) بالمعرفات الحقيقية (Real IDs) بشكل عودي داخل كائن الحمولة (Payload)
 * @param {any} obj - الكائن المراد معالجته
 * @param {Record<number, number>} idMap - جدول مطابقة المعرفات
 * @returns {any} الكائن بعد الاستبدال
 */
function ksReplaceMockIds(obj, idMap) {
    // نفس إصلاح ملف الـ Service Worker: يجب التحقق من idMap للقيم الأولية
    // حتى عندما تكون عنصر مصفوفة مباشر [76431] وليس فقط قيمة خاصية {id: 76431}
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

/**
 * إعادة إرسال الطلبات المعلّقة — آلية احتياطية (Fallback)
 * تعمل كبديل عندما لا يدعم المتصفح Background Sync API
 *
 * @returns {Promise<void>}
 */
async function replayPendingRequestsFallback() {
    // --- التحقق من الاتصال ---
    if (!navigator.onLine) return;

    // --- قفل المزامنة: منع التنفيذ المتداخل ---
    if (_isSyncing) {
        console.log("[KSER Sync] ⏳ عملية مزامنة جارية بالفعل — تم تخطي هذا الاستدعاء");
        return;
    }

    _isSyncing = true;

    try {
        /** @type {PendingRequest[]} */
        const pending = await getPendingRequests();
        if (!pending || pending.length === 0) return;

        console.log(`[KSER Sync] بدء مزامنة ${pending.length} طلب(ات) معلّقة...`);

        const idMap = {};

        for (const record of pending) {
            try {
                let payload = record.payload;
                try {
                    const parsedPayload = JSON.parse(record.payload);
                    const updatedPayload = ksReplaceMockIds(parsedPayload, idMap);
                    payload = JSON.stringify(updatedPayload);
                } catch (e) {
                    console.warn("[KSER Sync] فشل تحليل أو معالجة حمولة الطلب:", e);
                }

                const response = await fetch(record.url, {
                    method: "POST",
                    headers: record.headers,
                    body: payload,
                });

                if (response.ok) {
                    /** @type {string} */
                    const responseText = await response.text();

                    /** @type {Object} */
                    let respJson;
                    try {
                        respJson = JSON.parse(responseText);
                    } catch (_parseErr) {
                        console.error(
                            `[KSER Sync] ❌ استجابة غير JSON للسجل id=${record.id} — نقل إلى Dead Letter Queue`
                        );
                        await moveToDeadLetterQueue(record, `Non-JSON response: ${responseText.substring(0, 200)}`);
                        continue;
                    }

                    if (respJson.error) {
                        /** @type {string} */
                        const errorMsg =
                            respJson.error.data?.message ||
                            respJson.error.message ||
                            JSON.stringify(respJson.error);

                        const currentRetries = (record.retryCount || 0) + 1;

                        if (currentRetries >= KSER_MAX_RETRIES) {
                            console.error(
                                `[KSER Sync] ☠️ فشل دائم للسجل id=${record.id} بعد ${currentRetries} محاولة — نقل إلى Dead Letter Queue:`,
                                errorMsg
                            );
                            await moveToDeadLetterQueue(record, errorMsg);
                        } else {
                            console.warn(
                                `[KSER Sync] ⚠️ فشل تطبيقي من أودو للسجل id=${record.id} (محاولة ${currentRetries}/${KSER_MAX_RETRIES}):`,
                                errorMsg
                            );
                            await updateRetryCount(record);
                        }
                    } else {
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
                            console.log(`[KSER Sync] 🔗 تم مطابقة المعرف الوهمي ${record.mockId} بالمعرف الحقيقي ${realId}`);
                        }

                        await deleteRequest(record.id);
                        console.log(`[KSER Sync] ✅ تمت مزامنة السجل id=${record.id} بنجاح`);
                    }
                } else {
                    console.warn(
                        `[KSER Sync] استجابة HTTP غير ناجحة للسجل id=${record.id}: ${response.status}`
                    );
                    await updateRetryCount(record);
                }
            } catch (/** @type {Error} */ err) {
                console.warn(`[KSER Sync] 🔌 فشل الاتصال للسجل id=${record.id}:`, err.message);
                break;
            }
        }
    } catch (/** @type {Error} */ e) {
        console.error("[KSER Sync] خطأ عام في عملية المزامنة:", e);
    } finally {
        _isSyncing = false;
    }
}

// ============================================================
// تسجيل المستمعين (Event Listeners)
// ============================================================

// مهم جداً: هذي الآلية "احتياطية" ويجب أن تعمل فقط على المتصفحات التي
// لا تدعم Background Sync API الحقيقي. بدون هذا الشرط، تعمل الآليتان معاً
// على نفس الطلبات في نفس الوقت (من الصفحة نفسها ومن الـ Service Worker)
// مما يسبب إرسال نفس الطلب مرتين وإنشاء سجلات مكررة بالسيرفر
const supportsRealBackgroundSync =
    "serviceWorker" in navigator && "SyncManager" in window;

if (!supportsRealBackgroundSync) {
    console.log("[KSER] Background Sync API غير مدعوم — تفعيل آلية المزامنة الاحتياطية بالصفحة");

    // عند استعادة الاتصال بالإنترنت
    window.addEventListener("online", replayPendingRequestsFallback);

    // محاولة دورية كل 30 ثانية
    setInterval(replayPendingRequestsFallback, 30000);

    // عند تحميل الصفحة
    window.addEventListener("load", replayPendingRequestsFallback);
} else {
    console.log("[KSER] Background Sync API مدعوم — الاعتماد على الـ Service Worker فقط للمزامنة");
}