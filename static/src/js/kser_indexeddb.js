// @odoo-module ignore

const KSER_DB_NAME = "KSER_Offline_DB";
const KSER_DB_VERSION = 1;
const KSER_STORE_NAME = "Pending_Beneficiaries";

function openDatabase() {
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

        request.onsuccess = (event) => {
            resolve(event.target.result);
        };

        request.onerror = (event) => {
            reject(event.target.error);
        };
    });
}

async function savePendingRequest(url, headers, payload) {
    const db = await openDatabase();
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

async function getPendingRequests() {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(KSER_STORE_NAME, "readonly");
        const store = tx.objectStore(KSER_STORE_NAME);

        const request = store.getAll();
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

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
