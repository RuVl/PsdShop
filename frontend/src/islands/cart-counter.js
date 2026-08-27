// Storefront cart island (ADR-0009). The cart lives in localStorage under `cart`; this island is
// its only reader/writer on the server-rendered pages: it binds the `[data-add-to-cart]` buttons
// and paints the item count into #cart-counter. USD-only, no stock - the Verdoc SPA cart model
// (currency conversion, max_quantity) is deliberately not reused here.
const KEY = 'cart';
const CHANGED = 'cart:changed';

function read() {
    try {
        const raw = localStorage.getItem(KEY);
        if (!raw) return {items: []};
        const data = JSON.parse(raw);
        return Array.isArray(data.items) ? data : {items: []};
    } catch {
        // A private window or a malformed value must not break the header.
        return {items: []};
    }
}

function write(cart) {
    try {
        localStorage.setItem(KEY, JSON.stringify(cart));
    } catch {
        // Storage may be full or blocked; the click just does not persist.
    }
    // `storage` does not fire in the tab that wrote it, so nudge our own listeners.
    window.dispatchEvent(new Event(CHANGED));
}

function renderBadge() {
    const el = document.getElementById('cart-counter');
    if (!el) return;

    const count = read().items.length;
    if (count > 0) {
        el.textContent = String(count);
        el.hidden = false;
    } else {
        el.hidden = true;
    }
}

function addToCart(btn) {
    const id = btn.dataset.id;
    if (!id) return;

    const cart = read();
    const existing = cart.items.find((item) => String(item.id) === String(id));
    if (existing) {
        existing.quantity = (existing.quantity || 1) + 1;
    } else {
        cart.items.push({
            id,
            name: btn.dataset.name || '',
            price: btn.dataset.price || '',
            quantity: 1,
        });
    }
    write(cart);
}

document.addEventListener('click', (event) => {
    const btn = event.target.closest('[data-add-to-cart]');
    if (!btn) return;
    event.preventDefault();
    addToCart(btn);
});

renderBadge();
window.addEventListener(CHANGED, renderBadge);
// Another tab changed the cart (key is null on clear()).
window.addEventListener('storage', (event) => {
    if (event.key === KEY || event.key === null) renderBadge();
});
