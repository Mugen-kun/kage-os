"use strict";

const status = document.querySelector("#status");
const time = document.querySelector("#time");
const source = document.querySelector("#source");
const upload = document.querySelector("#upload");
const selection = document.querySelector("#selected");
let limit = 0;
let deadline = 0;

function showSelection() {
    selection.textContent = source.files[0]?.name || "";
    selection.hidden = !selection.textContent;
}

async function showFiles() {
    try {
        const response = await fetch("files", {cache: "no-store"});
        if (!response.ok) throw new Error();
        const settings = await response.json();
        limit = settings.limit;
        const links = document.querySelector("#files");
        settings.files.forEach((name, index) => {
            const row = document.createElement("li");
            const link = document.createElement("a");
            link.href = "download/" + index;
            link.textContent = name;
            link.download = name;
            row.append(link);
            links.append(row);
        });
        document.querySelector("#downloads").hidden = !settings.files.length;
        document.querySelector("#send").hidden = !settings.receive;
        deadline = Date.now() + settings.seconds * 1000;
        function updateTime() {
            const seconds = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
            time.textContent = seconds ? "Kalan süre " + Math.ceil(seconds / 60) + " dk" : "Paylaşım süresi doldu.";
            if (!seconds) upload.disabled = true;
            return seconds;
        }
        updateTime();
        const timer = setInterval(() => { if (!updateTime()) clearInterval(timer); }, 1000);
        status.textContent = "";
    } catch {
        status.textContent = "Bağlantı açılamadı. Kage’de yeni paylaşım başlat.";
    }
}

source.addEventListener("change", showSelection);

upload.addEventListener("click", async () => {
    const file = source.files[0];
    if (!file || file.size > limit) {
        status.textContent = file ? "Bu dosya 128 MiB sınırını aşıyor." : "Önce bir dosya seç.";
        return;
    }
    upload.disabled = true;
    status.textContent = "Dosya gönderiliyor…";
    try {
        const response = await fetch("upload", {
            method: "POST",
            body: file,
            headers: {"X-Kage-Filename": encodeURIComponent(file.name)},
        });
        const result = await response.json();
        status.textContent = response.ok ? result.name + " kaydedildi." : result.error;
        if (response.ok) {
            source.value = "";
            showSelection();
        }
    } catch {
        status.textContent = "Aktarım tamamlanamadı. Bağlantını kontrol edip tekrar dene.";
    } finally {
        upload.disabled = Date.now() >= deadline;
    }
});

showFiles();
