// Stake settled-bets extractor (runs in the DevTools console / Chrome extension JS tool on the user's OWN logged-in page).
// Open https://stake.com/es/sports/home/my-bets/settled , paste, await extractStakeHistory(3).
// Reads only what the page already renders (expands "Mostrar piernas", clicks "Siguiente"); places and changes nothing.
// Output rows: [date, type(single|multi|sgm), legs, odds, stake, payout, result(W|L|adj)] -> scripts/stake_week_retro.py
async function extractStakeHistory(pages = 3) {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const isLeaf = (e) => /^Mostrar piernas$/.test((e.innerText || "").trim()) && ![...e.children].some((c) => /^Mostrar piernas$/.test((c.innerText || "").trim()));
  async function grab() {
    for (let i = 0; i < 3; i++) {
      const all = [...document.querySelectorAll("*")].filter(isLeaf);
      if (!all.length) break;
      all.forEach((e) => e.click());
      await sleep(900);
    }
    const t = document.body.innerText;
    const a = t.indexOf("Finalizadas"), b = t.indexOf("Anterior");
    return t.slice(a, b > 0 ? b : undefined);
  }
  const txt = [await grab()];
  for (let k = 1; k < pages; k++) {
    const nx = [...document.querySelectorAll("a,button")].find((e) => /^Siguiente$/.test((e.innerText || "").trim()));
    if (!nx) break;
    nx.click();
    await sleep(3000);
    txt.push(await grab());
  }
  const all = txt.join("\n");
  const chunks = all.split(/Pago\n[\d.]+\n/);
  const pays = [...all.matchAll(/Pago\n([\d.]+)\n/g)].map((m) => +m[1]);
  const rows = [];
  chunks.slice(0, -1).forEach((body, i) => {
    const m = body.match(/Cuotas\n([\d,]+)\nApuesta\n([\d.]+)\s*$/);
    if (!m) return;
    const d = body.match(/(Lun|Mar|Mié|Jue|Vie|Sáb|Dom), (\d+) (\w+)/) || [];
    const h = body.replace(/^Finalizadas\n/, "").split("\n").map((s) => s.trim()).filter(Boolean);
    const legs = body.match(/(\d+) Multi tramo/);
    const type = /^Multi apuesta del mismo/.test(h[0]) ? "sgm" : legs ? "multi" : "single";
    const head = h.slice(0, 4).join(" ");
    const res = /Perdida/.test(head) ? "L" : /Ganador/.test(head) ? "W" : "adj";
    rows.push([`${d[2]} ${d[3]}`, type, legs ? +legs[1] : 1, +m[1].replace(",", "."), +m[2], +pays[i].toFixed(2), res]);
  });
  return rows;
}
