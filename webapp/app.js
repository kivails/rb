const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();
tg.setHeaderColor("#1a0d2e");
tg.setBackgroundColor("#0e0e1a");

async function fetchMe() {
  const loader = document.getElementById("loader");
  loader.style.display = "block";
  try {
    const r = await fetch(`/api/me`, {
      headers: { "X-Init-Data": tg.initData }
    });
    if (!r.ok) throw new Error("auth");
    const d = await r.json();
    document.getElementById("name").textContent = d.first_name || "Друг";
    document.getElementById("nick").textContent = d.roblox_nick || "Ник не задан";
    document.getElementById("balance").textContent = d.balance;
    const need = Math.max(d.min_withdraw - d.balance, 0);
    document.getElementById("toWithdraw").textContent = need;
    const pct = Math.min((d.balance / d.min_withdraw) * 100, 100);
    document.getElementById("barFill").style.width = pct + "%";
  } catch (e) {
    tg.showAlert("Ошибка загрузки. Открой через бота.");
  } finally {
    loader.style.display = "none";
  }
}

document.querySelectorAll(".tile").forEach(t => {
  t.addEventListener("click", e => {
    e.preventDefault();
    const action = t.dataset.action;
    tg.HapticFeedback.selectionChanged();
    const labels = {
      ref: "Открой в боте: 🎀 Реф-ссылка",
      daily: "Открой в боте: 🎰 Daily",
      promo: "Открой в боте: 🎁 Промокод",
      withdraw: "Открой в боте: 💸 Вывод",
      top: "Открой в боте: 🏆 Топы",
      history: "Открой в боте: 🧾 История"
    };
    tg.showAlert(labels[action]);
  });
});

fetchMe();
